"""Read-only actual Wonju evidence/context audit. Never invokes an LLM or app lifespan."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

from ai_server.app.main import build_region_snapshot, ReportResponse, REPORT_SCHEMA
from ai_server.app.agents.case_study_agent import _load_curated_case_cards
from ai_server.app.agents.evidence_agent import allowed_domains
from ai_server.app.agents.planner_agent import _build_revision_evidence_pack
from ai_server.app.agents.planning_requirements import QUALITY_CONTRACT_VERSION, build_completion_checklist
from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck
from ai_server.app.agents.reviewer_agent import REVIEW_SCHEMA
from ai_server.app.agents.transferability_agent import TRANSFERABILITY_SCHEMA
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.models import LLMRequest
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.llm.context_tables import decode_tables, encode_tables
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.llm.local_agent import _prefetch_required_evidence

ROOT = Path(__file__).resolve().parents[1]


class ContextChecked(Exception):
    pass


class OfflineProvider(OllamaProvider):
    def _check_context(self, messages, schema, output_limit, measured_prefix=None):
        try:
            return super()._check_context(messages, schema, output_limit, measured_prefix)
        except LLMProviderError:
            details = []
            for message in messages:
                content = message.get('content', '')
                if content.startswith('서버가 사전 조회한 필수 읽기 전용 근거:'):
                    details = [{'tool': row['tool'], 'estimated_tokens': self._estimated_context_tokens(row) - 1024}
                               for row in decode_tables(json.loads(content.split('\n', 1)[1]))]
            print(json.dumps({'task': self.audit_task,
                              'estimated_total': self._estimated_context_tokens({'messages': messages, 'schema': schema}) + output_limit,
                              'prefetch_sizes': details}, ensure_ascii=False))
            raise

    async def _chat(self, **kwargs):
        # No model reply or token measurement is fabricated. Only skip optional calls.
        return {'content': 'offline: no optional tool calls'}, {}

    async def _call(self, **kwargs):
        estimated = self._estimated_context_tokens({'messages': kwargs['messages'], 'schema': kwargs['schema']})
        print(json.dumps({'task': self.audit_task, 'status': 'prefetch_context_check_passed',
                          'estimated_input_tokens': estimated, 'output_reserve': kwargs['max_output_tokens'],
                          'context_limit': self.context_length, 'actual_inference': False}))
        raise ContextChecked


async def main():
    report = json.loads((ROOT / 'storage/ppt_audit_20260905/report.json').read_text(encoding='utf-8'))
    draft = {key: report[key] for key in REPORT_SCHEMA['properties'] if key in report}
    snapshot = build_region_snapshot(report['region_name'])
    snapshot['ml_analysis'] = report['ml_analysis']
    cards = _load_curated_case_cards(ROOT, allowed_domains({}))
    # Retain the actual source inventory, but use the current corrected case content.
    sources = deepcopy(report['evidence_sources'])
    card_map = {row['source_id']: row for row in cards}
    for source in sources:
        if source.get('source_id') in card_map:
            card = card_map[source['source_id']]
            source.update(summary=card['observed_result'], quantitative_result_approved=card.get('quantitative_result_approved'))
    pack = {'region_code': '51130', 'region_name': report['region_name'], 'period': report['period'],
            'snapshot': snapshot, 'sources': sources, 'benchmark_cases': cards,
            'planning_brief': report.get('planning_brief'), 'transfer_assessment': report['planning_decision'],
            'research_gaps': report.get('research_gaps', []), 'quality_contract_version': QUALITY_CONTRACT_VERSION}
    precheck = build_plan_quality_precheck(pack, draft, limit=None)
    review = deepcopy(report['quality_review'])
    review.update(validation_findings=precheck['issues'], quality_contract_version=QUALITY_CONTRACT_VERSION)
    review['completion_checklist'] = build_completion_checklist(review, pack, draft)
    response = ReportResponse.model_validate({**report, 'quality_review': review}).model_dump(mode='json')
    assert response['quality_review']['completion_checklist'] == review['completion_checklist']
    print(json.dumps({'read_only': True, 'saved_report_modified': False, 'original_source_count': len(sources),
                      'validation_findings': precheck['issue_count'], 'response_roundtrip': 'passed',
                      'nationwide_comparison': snapshot.get('nationwide_comparison', {}).get('available'),
                      'nationwide_bigdata': snapshot.get('nationwide_bigdata_context', {}).get('available')}, ensure_ascii=False))
    for task, schema, limit in [('transferability', TRANSFERABILITY_SCHEMA, 5600),
                                 ('planner', REPORT_SCHEMA, 16000),
                                 ('planner_revision', REPORT_SCHEMA, 14000),
                                 ('reviewer', REVIEW_SCHEMA, 5500)]:
        payload = {'evidence_pack': pack}
        if task == 'planner_revision':
            payload = {'evidence_pack': _build_revision_evidence_pack(pack, draft), 'previous_draft': draft,
                       'quality_review_feedback': {'overall_score': report['quality_review'].get('overall_score'),
                           'issues': [{key: row.get(key) for key in ('severity', 'field', 'revision_instruction')}
                                      for row in report['quality_review'].get('issues', [])]}}
        elif task == 'reviewer':
            payload['draft_report'] = draft
        raw = _prefetch_required_evidence(EvidenceTools(payload, task=task), task)
        assert decode_tables(encode_tables(raw)) == raw, 'Evidence values changed'
        provider = OfflineProvider(base_url='', default_model='offline', context_length=40960)
        provider.audit_task = task
        try:
            await provider.generate(LLMRequest(task=task, instructions='', input_payload=payload,
                                              schema_name='audit', schema=schema, max_output_tokens=limit,
                                              local_evidence_tools=True))
        except ContextChecked:
            pass
        except LLMProviderError as exc:
            print(json.dumps({'task': task, 'status': 'blocked', 'code': exc.code}))


if __name__ == '__main__':
    asyncio.run(main())
