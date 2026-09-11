"""Diagnostic mode keeps production reports and evidence intact; no network/GPU."""
import io
import json
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ai_server.app.scripts import replay_candidate_repair as replay
from ai_server.test_planning_requirements import pack, transfer


class CandidateReplayTest(unittest.IsolatedAsyncioTestCase):
    async def check_mode(self, fresh):
        evidence = pack(False)
        report = {'region_name': evidence['region_name'], 'period': '2026-06',
                  'planning_brief': {'region_code': '51130'}, 'ml_analysis': {'status': 'saved'},
                  'planning_decision': evidence['transfer_assessment'],
                  'evidence_sources': evidence['sources']}
        before = deepcopy(report)
        agent = SimpleNamespace(assess=AsyncMock(return_value=transfer()))
        paid = SimpleNamespace(generate=AsyncMock())
        router = SimpleNamespace(config={}, providers={'openai': paid}, consume_trace=lambda: [])
        output = io.StringIO()
        with patch.object(replay, 'load_project_env', return_value={}), \
             patch.object(replay, 'allowed_domains', return_value=[]), \
             patch.object(replay, '_load_curated_case_cards', return_value=evidence['benchmark_cases']), \
             patch.object(replay, 'LLMRouter', return_value=router), \
             patch.object(replay, 'TransferabilityAgent', return_value=agent), \
             patch.object(replay.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(report).encode())), \
             patch('ai_server.app.main.build_region_snapshot', return_value={'region_code': '51130'}), \
             redirect_stdout(output):
            await replay.run('report123', fresh=fresh)
        sent = agent.assess.call_args.kwargs
        self.assertEqual(sent['evidence_pack']['sources'], evidence['sources'])
        self.assertEqual(sent['evidence_pack']['benchmark_cases'], evidence['benchmark_cases'])
        self.assertEqual(sent['evidence_pack']['snapshot']['ml_analysis'], report['ml_analysis'])
        if fresh:
            self.assertNotIn('transfer_assessment', sent['evidence_pack'])
            self.assertIsNone(sent['revision_feedback'])
        else:
            self.assertEqual(sent['evidence_pack']['transfer_assessment'], report['planning_decision'])
            self.assertTrue(sent['revision_feedback'])
        self.assertEqual(report, before)
        paid.generate.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'Paid calls forbidden'):
            await paid.generate(None)
        result = json.loads(output.getvalue().splitlines()[-1])
        self.assertFalse(result['report_approved'])
        self.assertIn('candidate_contract_passed', result)
        self.assertIn('stabilized_candidate_contract_passed', result)
        self.assertIn('stabilized_issues', result)
        self.assertIn('automatic_corrections', result)
        self.assertIn('stabilized_decision', result)

    async def test_fresh_is_diagnostic_and_preserves_evidence(self):
        await self.check_mode(True)

    async def test_default_keeps_existing_repair_input(self):
        await self.check_mode(False)
