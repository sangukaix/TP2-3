"""Paired diagnostic invariants; no GPU or network calls."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from contextlib import redirect_stdout

from ai_server.app.scripts import candidate_thinking_comparison as comparison
from ai_server.app.llm.errors import LLMProviderError


class ThinkingComparisonTest(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, first_error=False):
        workspace = SimpleNamespace(
            missing_required_reads=lambda: [], events=[], read_case_source_ids=lambda: ['case:a'],
            verify_citations=lambda value: None)
        answer = ({'content': '{"value": 1}', 'thinking': 'private reasoning'}, {'output_tokens': 12})
        responses = [LLMProviderError('OLLAMA_INCOMPLETE_RESPONSE', 'limit', usage={'output_tokens': 5600})
                     if first_error else answer, answer]
        provider = SimpleNamespace(_chat=AsyncMock(side_effect=responses), _call=AsyncMock(),
                                   context_length=40960, timeout_seconds=420)
        request = {'model': 'qwen3:14b', 'messages': [{'role': 'user', 'content': 'same evidence'}],
                   'schema': {'type': 'object'}, 'max_output_tokens': 5600}
        output = io.StringIO()
        with TemporaryDirectory(dir=Path.cwd() / 'storage') as directory, \
             patch.object(comparison.local_agent, 'EvidenceTools', return_value=workspace), \
             patch.object(comparison, 'candidate_delivery_issues', return_value=[]), redirect_stdout(output):
            root = Path(directory)
            (root / 'storage').mkdir()
            with comparison.compare_final_requests(provider, {}, root):
                comparison.local_agent.EvidenceTools({})
                with self.assertRaises(comparison.ComparisonComplete):
                    await provider._call(**request)
            artifact = json.loads(next((root / 'storage').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(artifact['request'], request)
        calls = provider._chat.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs, dict(request, think=False))
        self.assertEqual(calls[1].kwargs, dict(request, think=True))
        self.assertNotIn('private reasoning', output.getvalue())
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        arms = [row for row in rows if row['event'] == 'comparison_arm']
        self.assertEqual(arms[0]['request_sha256'], arms[1]['request_sha256'])
        self.assertTrue(all(row['report_approved'] is False for row in arms))
        if first_error:
            self.assertEqual(arms[0]['code'], 'OLLAMA_INCOMPLETE_RESPONSE')
            self.assertEqual(arms[0]['usage']['output_tokens'], 5600)
            self.assertFalse(arms[0]['candidate_contract_passed'])
        self.assertEqual(arms[1]['decision'], {'value': 1})

    async def test_identical_input_and_no_approval(self):
        await self.exercise()

    async def test_failed_arm_does_not_retry_or_change_other_input(self):
        await self.exercise(first_error=True)

    async def test_capture_only_writes_request_without_final_model_calls(self):
        workspace = SimpleNamespace(
            missing_required_reads=lambda: [], events=[{'tool': 'required'}],
            read_case_source_ids=lambda: ['case:a'])
        provider = SimpleNamespace(_chat=AsyncMock(), _call=AsyncMock(),
                                   context_length=40960, timeout_seconds=420)
        request = {'model': 'qwen3:14b', 'messages': [{'role': 'user', 'content': 'independent'}],
                   'schema': {'type': 'object'}, 'max_output_tokens': 5600}
        with TemporaryDirectory(dir=Path.cwd() / 'storage') as directory, \
             patch.object(comparison.local_agent, 'EvidenceTools', return_value=workspace):
            root = Path(directory)
            (root / 'storage').mkdir()
            with comparison.compare_final_requests(provider, {}, root, capture_only=True):
                comparison.local_agent.EvidenceTools({})
                with self.assertRaises(comparison.ComparisonComplete):
                    await provider._call(**request)
            artifact = json.loads(next((root / 'storage').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(artifact['request'], request)
        provider._chat.assert_not_awaited()
