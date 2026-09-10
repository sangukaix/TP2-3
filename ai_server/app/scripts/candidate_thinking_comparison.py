"""Diagnostic-only paired final requests; never return a candidate to production."""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
from time import perf_counter
from uuid import uuid4
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from ..llm import local_agent
from ..llm.errors import LLMProviderError
from ..agents.planning_requirements import candidate_delivery_issues


class ComparisonComplete(Exception):
    """Stops the diagnostic before automatic repairs or report generation."""


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


@contextmanager
def compare_final_requests(provider, pack, root, *, capture_only=False):
    """Share the actual evidence workspace and first final prompt between two arms."""
    workspace_holder = []
    original_workspace = local_agent.EvidenceTools
    original_chat = provider._chat

    async def preparation_chat(**kwargs):
        started = perf_counter()
        row = {'event': 'comparison_preparation_call', 'phase': 'tool_selection'}
        try:
            message, usage = await original_chat(**kwargs)
            row.update(status='completed', usage=usage)
            return message, usage
        except LLMProviderError as exc:
            row.update(status='failed', code=exc.code, usage=exc.usage)
            raise
        finally:
            row['duration_ms'] = round((perf_counter() - started) * 1000)
            emit(row)

    def capture_workspace(*args, **kwargs):
        workspace = original_workspace(*args, **kwargs)
        workspace_holder.append(workspace)
        return workspace

    async def paired_call(**kwargs):
        workspace = workspace_holder[-1]
        if workspace.missing_required_reads():
            raise RuntimeError('Comparison requires all mandatory evidence reads')
        frozen = deepcopy(kwargs)
        serialized = json.dumps(frozen, ensure_ascii=False, sort_keys=True)
        fingerprint = sha256(serialized.encode('utf-8')).hexdigest()
        path = root / 'storage' / f'candidate_comparison_input_{uuid4().hex}.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump({'request': frozen, 'evidence_pack': pack,
                       'tool_trace': workspace.events,
                       'read_case_ids': workspace.read_case_source_ids(),
                       'request_sha256': fingerprint}, stream, ensure_ascii=False, indent=2)
        emit({'event': 'comparison_input', 'request_sha256': fingerprint,
              'input_file': path.relative_to(root).as_posix(),
              'context_length': provider.context_length,
              'timeout_seconds': provider.timeout_seconds,
              'temperature': 0.15, 'max_output_tokens': frozen['max_output_tokens'],
              'tool_trace': workspace.events, 'report_approved': False})
        if capture_only:
            raise ComparisonComplete()
        for thinking in (False, True):
            emit({'event': 'arm_start', 'think': thinking, 'request_sha256': fingerprint})
            started = perf_counter()
            row = {'event': 'comparison_arm', 'think': thinking,
                   'request_sha256': fingerprint, 'report_approved': False,
                   'candidate_contract_passed': False}
            try:
                message, usage = await original_chat(**deepcopy(frozen), think=thinking)
                # Retain the answer, never the model's internal thinking text.
                content = str(message.get('content') or '')
                row.update(content=content, usage=usage,
                           thinking_present=bool(message.get('thinking')))
                decision = json.loads(content)
                Draft202012Validator(frozen['schema']).validate(decision)
                row['schema_valid'] = True
                row['decision'] = decision
                issues = candidate_delivery_issues(pack, decision)
                row['issues_after'] = issues
                workspace.verify_citations(decision)
                row['citations_read'] = True
                row['candidate_contract_passed'] = not issues
                row['status'] = 'completed'
            except LLMProviderError as exc:
                row.update(status='failed', code=exc.code)
                if exc.usage:
                    row['usage'] = exc.usage
            except (ValueError, ValidationError) as exc:
                # No repair/retry: preserve the first response, including schema failures.
                row.update(status='failed', code=type(exc).__name__)
            row['duration_ms'] = round((perf_counter() - started) * 1000)
            emit(row)
        raise ComparisonComplete()

    with patch.object(local_agent, 'EvidenceTools', side_effect=capture_workspace), \
         patch.object(provider, '_chat', side_effect=preparation_chat), \
         patch.object(provider, '_call', side_effect=paired_call):
        yield
