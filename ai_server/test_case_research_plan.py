"""Regional search inputs and partial-source recovery, with no paid calls."""
from copy import deepcopy
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from ai_server.app.case_research_plan import build_case_research_plan, comparison_coverage
from ai_server.app.openai_responses import create_structured_response, OpenAIResponseError
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.test_case_scope import snapshot, card
from ai_server.app.agents.planning_requirements import execution_delivery_issues, spending_as_success


class ResearchPlanTests(unittest.TestCase):
    def test_neighborhood_descriptions_do_not_inflate_region_diversity(self):
        cases = [card('one', '인천광역시 전역', '환급 지원'),
                 card('two', '인천광역시 송도·월미도', '체험 해설'),
                 card('three', '인천광역시 연수구', '체험 해설')]
        result = comparison_coverage(cases)
        self.assertEqual(result['concrete_region_count'], 1)
        self.assertFalse(result['sufficient_for_comparison'])
        cases.append(card('four', '전라남도 강진군 (전역)', '환급 지원'))
        self.assertTrue(comparison_coverage(cases)['sufficient_for_comparison'])

    def test_same_city_suffixes_and_districts_are_counted_consistently(self):
        cases = [card('one', '전북 전주시 야간관광 권역', '체험 해설'),
                 card('two', '전북특별자치도 전주시 (한옥마을)', '환급 지원'),
                 card('three', '전북 전주시 완산구', '환급 지원')]
        self.assertEqual(comparison_coverage(cases)['concrete_region_count'], 1)
        cases = [card('one', '서울특별시 성동구', '환급 지원'),
                 card('two', '서울특별시 강남구', '체험 해설')]
        self.assertEqual(comparison_coverage(cases)['concrete_region_count'], 2)

    def test_large_matrix_is_lossless_and_requires_every_page(self):
        from ai_server.app.llm.evidence_tools import compact_json
        from ai_server.app.llm.local_agent import _prefetch_required_evidence
        payload = {'benchmark_cases': [card('one', '전남 강진군', '환급 지원')],
                   'case_research_plan': {'search_tasks': [{'query': '지역 성과와 원문 확인 ' * 450}]}}
        workspace = EvidenceTools(payload, task='transferability')
        original = workspace._case_matrix()
        first = workspace.execute('get_case_comparison_matrix', {})
        self.assertGreater(first['segment_count'], 1)
        self.assertIn('get_case_comparison_matrix', workspace.missing_required_reads())
        parts = [first['serialized_json_segment']]
        page = first
        while page['next_offset'] is not None:
            page = workspace.execute('get_case_comparison_matrix', {'offset': page['next_offset']})
            self.assertLessEqual(len(compact_json(page).encode('utf-8')), 12000)
            parts.append(page['serialized_json_segment'])
        self.assertEqual(json.loads(''.join(parts)), original)
        self.assertNotIn('get_case_comparison_matrix', workspace.missing_required_reads())
        fresh = EvidenceTools(payload, task='transferability')
        prefetched = _prefetch_required_evidence(fresh, 'transferability')
        pages = [p['result'] for p in prefetched if p['tool'] == 'get_case_comparison_matrix']
        self.assertEqual(len(pages), first['segment_count'])
        self.assertEqual(json.loads(''.join(p['serialized_json_segment'] for p in pages)), original)
        self.assertNotIn('get_case_comparison_matrix', fresh.missing_required_reads())

    def test_budget_disbursement_is_not_an_outcome_even_when_called_a_goal(self):
        text = '기획 가정: 환급 지원액 1,000만 원 이상 달성 시 성공'
        self.assertTrue(spending_as_success(text))
        issues = execution_delivery_issues({'kpi': text}, 'strategies[0]')
        self.assertTrue(any(i['field'].endswith('.kpi.outcome') and i['severity'] == 'critical' for i in issues))
        self.assertFalse(spending_as_success('환급 후 재사용률을 지급액으로 나누어 비교한다. 성공 기준은 착수 전 확정한다.'))

    def test_actual_signals_and_peer_gaps_reach_model_matrix(self):
        s = snapshot()
        s['nationwide_comparison']['peer_regions'][0]['visitors_gap_pct'] = -14.5
        s['ml_analysis'] = {'latest_observed_month': '202606', 'signals': [
            {'kind': 'forecast_signal', 'metric': 'spending_krw', 'change_percent': -5,
             'period': '202610~202612', 'source_id': 'ml:1', 'forecast_value': 123},
            {'kind': 'forecast_signal', 'metric': 'visitors', 'change_percent': 3}]}
        original = deepcopy(s)
        plan = build_case_research_plan(s)
        self.assertEqual(s, original)
        self.assertEqual(plan['signal_groups'][0]['id'], 'spend')
        self.assertEqual(plan['signal_groups'][0]['signals'][0]['forecast_value'], 123)
        self.assertEqual(plan['search_tasks'][0]['comparison']['visitors_gap_pct'], -14.5)
        self.assertIn('2023 2024 2025 2026', plan['search_tasks'][0]['query'])
        matrix = EvidenceTools({'snapshot': s, 'case_research_plan': plan}, task='transferability').execute('get_case_comparison_matrix', {})
        self.assertEqual(matrix['research_plan'], plan)

    def test_unavailable_peer_and_ml_do_not_invent_facts(self):
        plan = build_case_research_plan({'region_name': '인천광역시 부평구'})
        self.assertFalse(any(t['region_code'] for t in plan['search_tasks']))
        self.assertTrue(all(not g['signals'] for g in plan['signal_groups']))
        self.assertFalse(any('환급' in t['query'] for t in plan['search_tasks']))

    def test_diversity_does_not_require_an_exact_peer(self):
        cases = [card('one', '전남 강진군', '환급 지원'), card('two', '경기도 수원시', '체험 해설')]
        self.assertTrue(comparison_coverage(cases)['sufficient_for_comparison'])
        cases[1]['case_region'] = '전국 참여지역'
        self.assertFalse(comparison_coverage(cases)['sufficient_for_comparison'])


class GroundedCaseRecoveryTests(unittest.TestCase):
    schema = {'type': 'object', 'properties': {'summary': {'type': 'string'},
        'cases': {'type': 'array', 'items': {'type': 'object'}},
        'gaps': {'type': 'array'}}, 'required': ['summary', 'cases', 'gaps']}

    def call(self, cases, *, searched=True, name='official_tourism_case_studies'):
        data = {'summary': 'discarded source says guaranteed 100%', 'cases': cases, 'gaps': []}
        response = {'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(data)}]}],
            'usage': {'input_tokens': 20, 'output_tokens': 10, 'total_tokens': 30}}
        if searched:
            response['output'].insert(0, {'type': 'web_search_call', 'status': 'completed',
                'action': {'sources': [{'url': 'https://example.go.kr/verified'}]}})
        with patch('ai_server.app.openai_responses._post_response', new=AsyncMock(return_value=response)) as http:
            try:
                return asyncio.run(create_structured_response(api_key='test', model='test', instructions='test',
                    input_payload={}, schema_name=name, schema=self.schema, require_web_search=True,
                    return_metadata=True))
            finally:
                self.assertEqual(http.await_count, 1)

    def test_bad_card_does_not_discard_other_verified_case(self):
        good = {'source_url': 'https://example.go.kr/verified', 'observed_result': '12 people'}
        result = self.call([good, {'source_url': 'https://example.go.kr/unread'}])
        self.assertEqual(result['data']['cases'], [good])
        self.assertNotIn('100%', result['data']['summary'])
        self.assertTrue(result['web_search_used'])
        self.assertEqual(result['usage']['total_tokens'], 30)
        self.assertEqual(result['attempts'][0]['web_grounding']['rejected_cases'][0]['unverified_urls'], ['https://example.go.kr/unread'])

    def test_all_unverified_records_failure_diagnostics(self):
        with self.assertRaises(OpenAIResponseError) as c:
            self.call([{'source_url': 'https://example.go.kr/unread'}])
        self.assertEqual(c.exception.code, 'OPENAI_UNVERIFIED_WEB_SOURCE')
        self.assertEqual(c.exception.attempts[0]['web_grounding']['accepted_cases'], 0)
        self.assertEqual(c.exception.usage['total_tokens'], 30)

    def test_search_execution_is_still_mandatory(self):
        with self.assertRaises(OpenAIResponseError) as c:
            self.call([{'source_url': 'https://example.go.kr/verified'}], searched=False)
        self.assertEqual(c.exception.code, 'OPENAI_WEB_SEARCH_NOT_EXECUTED')

    def test_other_schemas_keep_strict_whole_response_validation(self):
        with self.assertRaises(OpenAIResponseError):
            self.call([{'source_url': 'https://example.go.kr/unread'}], name='evidence')


class ResearchFailureFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_insufficient_case_pack_is_never_cached(self):
        from pathlib import Path
        from ai_server.app.agents.report_orchestrator import _collect_case_studies, _CASE_STUDY_CACHE
        from types import SimpleNamespace
        _CASE_STUDY_CACHE.clear()
        agent = SimpleNamespace(project_root=Path.cwd(), collect=AsyncMock(return_value={
            'trace': [], 'case_search_coverage': {'sufficient_for_comparison': False}}))
        args = dict(agent=agent, env_values={}, region_code='test', snapshot={})
        self.assertFalse((await _collect_case_studies(**args))[1])
        self.assertFalse((await _collect_case_studies(**args))[1])
        self.assertEqual(agent.collect.await_count, 2)

    async def test_research_failure_does_not_reach_planner(self):
        from pathlib import Path
        from ai_server.app.agents.report_orchestrator import orchestrate_strategy_report
        pack = {'benchmark_cases': [card('one', '전남 강진군', '환급 지원')],
                'sources': [], 'trace': [], 'case_search_coverage': {'sufficient_for_comparison': False}}
        evidence = {'sources': [], 'trace': []}
        with patch('ai_server.app.llm.router.LLMRouter.preflight_local_models', new=AsyncMock()), \
             patch('ai_server.app.agents.report_orchestrator._collect_evidence', new=AsyncMock(return_value=(evidence,False))), \
             patch('ai_server.app.agents.report_orchestrator._collect_case_studies', new=AsyncMock(return_value=(pack,False))), \
             patch('ai_server.app.agents.report_orchestrator.TransferabilityAgent.assess', new=AsyncMock()) as compare:
            with self.assertRaises(OpenAIResponseError) as error:
                await orchestrate_strategy_report(project_root=Path.cwd(), env_values={'OPENAI_API_KEY':'test'},
                    region_code='28237', snapshot={'region_name':'인천광역시 부평구'}, report_schema={})
            self.assertEqual(error.exception.code, 'CASE_RESEARCH_INCOMPLETE')
            compare.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
