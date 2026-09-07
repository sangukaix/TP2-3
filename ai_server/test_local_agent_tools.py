"""로컬 도구의 권한·원문 보존·문맥·실행 기록을 외부 LLM 호출 없이 검증합니다."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import unittest
from unittest.mock import patch

import httpx

from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.llm.local_prompts import local_instructions
from ai_server.app.llm.models import LLMRequest
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server import test_llm_router as router_fixtures


def fixture() -> dict:
    return {'evidence_pack': {
        'region_code': '11680', 'region_name': '서울특별시 강남구', 'period': '2026-07',
        'planning_brief': {'budget_status': 'unknown', 'resources_status': 'unknown'},
        'snapshot': {
            'observations': [{'metric': 'visitors', 'value': 17963441, 'period': '2026-07'}],
            'consumption_by_category': [{'category': '식음료업', 'spending_krw': 100, 'share_percent': 40.0}],
            'nationwide_comparison': {'available': True, 'period': '2025-07 ~ 2026-06',
                'selected_region': {'overnight_ratio_avg_pct': 3.1167},
                'peer_regions': [{'region_code': '11650', 'overnight_ratio_gap_pct_point': 0.9834}]},
            'ml_analysis': {'status': 'available', 'forecast_type': 'baseline_not_causal',
                'horizon_policy': {'decision_windows': [{'start_month': '2026-09', 'end_month': '2026-11', 'reliability': 'exploratory'}]},
                'forecasts': [{'month': '2026-08', 'visitors': 10}, {'month': '2026-09', 'visitors': 20}],
                'cautions': ['정책 효과가 아니다'], 'evaluation': {'selected_model': 'seasonal_naive'}},
        },
        'sources': [{'source_id': 'case:1', 'title': '공식 사례', 'source_url': 'https://example.go.kr/case',
                     'source_type': 'benchmark_case', 'summary': '기준기간을 확인한 참고자료'}],
        'benchmark_cases': [{'source_id': 'case:1', 'case_region': '비교 지역', 'title': '공식 사례',
                             'operating_model': '실제 이용 완료 확인', 'observed_result': '인과효과 미확인'}],
    }}


def request() -> LLMRequest:
    return LLMRequest(task='planner', instructions='기존 OpenAI 지시문은 변경하지 않는다',
                      input_payload=fixture(), schema_name='test',
                      schema={'type': 'object', 'properties': {'answer': {'type': 'string'}},
                              'required': ['answer'], 'additionalProperties': False},
                      max_output_tokens=2000, local_evidence_tools=True)


def tool_call(name: str, **arguments) -> dict:
    return {'function': {'name': name, 'arguments': arguments}}


def required_calls() -> dict:
    return {'role': 'assistant', 'tool_calls': [tool_call('compare_regions'), tool_call('get_ml_forecast'),
                                               tool_call('read_collected_source', source_id='case:1')]}


class EvidenceToolTests(unittest.TestCase):
    def setUp(self):
        self.original = fixture()
        self.tools = EvidenceTools(self.original)

    def test_observations_and_unknown_conditions_are_preserved(self):
        overview = self.tools.overview()
        self.assertEqual(overview['observations'][0]['value'], 17963441)
        self.assertEqual(overview['planning_brief']['budget_status'], 'unknown')

    def test_region_metrics_includes_observed_consumption_composition(self):
        value = self.tools.execute('get_region_metrics', {})
        self.assertEqual(value['consumption_by_category'][0]['category'], '식음료업')
        self.assertEqual(value['consumption_by_category'][0]['share_percent'], 40.0)
        self.assertIn('사업 효과', value['consumption_interpretation'])
        self.assertEqual(self.original, fixture())

    def test_same_period_comparison_direction_is_explicit(self):
        value = self.tools.execute('compare_regions', {})
        self.assertEqual(value['peer_regions'][0]['gap_directions']['overnight_ratio_gap_pct_point'], 'higher')
        self.assertEqual(value['period'], '2025-07 ~ 2026-06')
        self.assertEqual(self.original, fixture())

    def test_forecast_range_preserves_cautions_and_evaluation(self):
        value = self.tools.execute('get_ml_forecast', {'start_month': '2026-09', 'end_month': '2026-11'})
        self.assertEqual([row['month'] for row in value['forecasts']], ['2026-09'])
        self.assertEqual(value['evaluation']['selected_model'], 'seasonal_naive')
        self.assertEqual(value['cautions'], ['정책 효과가 아니다'])

    def test_compact_months_are_filtered_without_rewriting_values(self):
        self.tools.snapshot['ml_analysis']['forecasts'] = [{'month': '202608', 'visitors': 10},
                                                          {'month': '202609', 'visitors': 20}]
        self.tools.snapshot['ml_analysis']['signals'] = [{'meaning': '원문 보존'}] * 2000
        value = self.tools.execute('get_ml_forecast', {'start_month': '2026-09', 'end_month': '2026-11'})
        self.assertNotIn('error', value)
        self.assertEqual(value['forecasts'], [{'month': '202609', 'visitors': 20}])
        path = value['additional_sections']['signals']
        self.assertEqual(self.tools.execute('read_task_section', {'path': path, 'limit': 1})['items'][0]['meaning'], '원문 보존')

    def test_invalid_calendar_month_is_rejected(self):
        with self.assertRaises(LLMProviderError):
            self.tools.execute('get_ml_forecast', {'start_month': '2026-99'})

    def test_search_is_not_live_search_and_does_not_mark_source_read(self):
        result = self.tools.execute('search_collected_sources', {'query': '공식'})
        self.assertFalse(result['live_web_search'])
        self.assertEqual(result['total'], 1)
        self.assertFalse(self.tools.read_source_ids)

    def test_source_is_read_with_url_and_measurement_limits(self):
        result = self.tools.execute('read_collected_source', {'source_id': 'case:1'})
        self.assertEqual(result['case']['observed_result'], '인과효과 미확인')
        self.assertEqual(result['source']['source_url'], 'https://example.go.kr/case')
        self.tools.verify_citations({'evidence': 'case:1'})

    def test_unread_case_is_blocked(self):
        self.assertEqual(self.tools.unread_cited_case_ids({'evidence': 'case:1'}), ['case:1'])
        with self.assertRaises(LLMProviderError) as error:
            self.tools.verify_citations({'evidence': 'case:1'})
        self.assertEqual(error.exception.code, 'LOCAL_EVIDENCE_NOT_READ')

    def test_case_ids_are_not_substring_matched(self):
        self.tools.verify_citations({'evidence': 'case:10'})

    def test_previous_draft_and_transfer_are_mandatory(self):
        self.tools.pack['transfer_assessment'] = {'selected_candidate_id': 'C1'}
        self.tools.payload['previous_draft'] = {'summary': '기존 초안'}
        missing = self.tools.missing_required_reads()
        self.assertIn('read_task_section(/previous_draft)', missing)
        self.assertIn('get_planning_decision', missing)
        self.tools.execute('read_task_section', {'path': '/previous_draft'})
        self.assertNotIn('read_task_section(/previous_draft)', self.tools.missing_required_reads())

    def test_decision_preserves_selected_candidate_and_points_to_all_alternatives(self):
        self.tools.pack['transfer_assessment'] = {'selected_candidate_id': 'C2', 'selection_reason': '비교 이유',
            'design_candidates': [{'candidate_id': 'C1', 'title': '비교'}, {'candidate_id': 'C2', 'title': '선정', 'budget': '산식'}],
            'candidate_assessments': [{'reason': '원문'}]}
        result = self.tools.execute('get_planning_decision', {})
        self.assertEqual(result['selected_candidate']['budget'], '산식')
        self.assertEqual(len(result['candidate_index']), 2)
        self.assertIn('candidate_assessments', result['additional_sections'])
        self.assertNotIn('get_planning_decision', self.tools.missing_required_reads())

    def test_transferability_reads_two_distinct_case_mechanisms(self):
        """Qwen 후보 비교는 숙박/야간 같은 한 사례만 읽고 끝낼 수 없습니다."""
        payload = fixture()
        payload['evidence_pack']['sources'].append({
            'source_id': 'case:2', 'title': '야간 운영 사례', 'source_url': 'https://example.go.kr/night',
            'source_type': 'benchmark_case', 'summary': '야간 프로그램 운영 조건',
        })
        payload['evidence_pack']['benchmark_cases'].append({
            'source_id': 'case:2', 'case_region': '다른 지역', 'title': '야간 운영 사례',
            'operating_model': '야간 예약과 안전 운영', 'observed_result': '인과효과 미확인',
        })
        tools = EvidenceTools(payload, task='transferability')
        tools.execute('compare_regions', {})
        tools.execute('get_ml_forecast', {})
        matrix = tools.execute('get_case_comparison_matrix', {})
        self.assertEqual({row['mechanism_family'] for row in matrix['rows']}, {'other_operation', 'night_time_experience'})
        tools.execute('read_collected_source', {'source_id': 'case:1'})
        self.assertTrue(any('서로 다른 운영 방식' in value for value in tools.missing_required_reads()))
        tools.execute('read_collected_source', {'source_id': 'case:2'})
        self.assertEqual(tools.missing_required_reads(), [])

    def test_arbitrary_sql_or_file_tools_are_rejected(self):
        for name in ('execute_sql', 'read_file', 'web_fetch'):
            with self.assertRaises(LLMProviderError):
                self.tools.execute(name, {'query': 'secret'})

    def test_unknown_arguments_are_rejected(self):
        with self.assertRaises(LLMProviderError):
            self.tools.execute('get_region_metrics', {'region_code': 'other'})
        with self.assertRaises(LLMProviderError):
            self.tools.execute('search_collected_sources', {'limit': 999})

    def test_task_path_is_only_request_json_not_filesystem(self):
        self.assertIn('error', self.tools.execute('read_task_section', {'path': '/.env'}))
        self.assertIn('error', self.tools.execute('read_task_section', {'path': 'C:/Users/Admin/.env'}))
        result = self.tools.execute('read_task_section', {'path': '/evidence_pack/snapshot/observations', 'limit': 1})
        self.assertEqual(result['items'][0]['value'], 17963441)

    def test_long_sources_are_not_silently_truncated_or_marked_read(self):
        text = '공식 원문' * 4000
        self.tools.sources['case:1']['case']['long_text'] = text
        result = self.tools.execute('read_collected_source', {'source_id': 'case:1'})
        self.assertEqual(result['error'], 'EVIDENCE_RESULT_TOO_LARGE')
        self.assertEqual(self.tools.sources['case:1']['case']['long_text'], text)
        self.assertNotIn('case:1', self.tools.read_source_ids)

    def test_regional_status_uses_explicit_compact_summary_before_tool_limit(self):
        """인기장소 원본이 길어도 지역 현황 자체가 unavailable이 되면 안 된다."""

        payload = fixture()
        original_status = {
            'available': True,
            'region_code': '11680',
            'region_name': '서울특별시 강남구',
            'latest_historical_period': '2025-07 ~ 2026-06',
            'inflow_outflow': {
                'top_inflow_origins': [
                    {'related_region_name': f'유입지역 {index}', 'ratio_pct': str(index), 'rank_no': str(index),
                     'source_id': 'regional:inflow', 'repeated_raw_detail': '원본' * 2000}
                    for index in range(1, 6)
                ],
                'top_outflow_destinations': [],
                'inbound_destination_types': [],
                'outbound_destination_types': [],
            },
            'popular_places': {
                'restaurants': [
                    {'place_name': f'음식점 {index}', 'classification': '음식점', 'rank_no': str(index),
                     'metric_name': 'rank', 'metric_unit': 'rank_only', 'source_id': 'regional:hotspot',
                     'large_raw_detail': '원본' * 2000}
                    for index in range(1, 6)
                ],
            },
            'concentration_30_day_signal': {'available': True, 'usage': '운영 참고 신호'},
            'source_records': [{'source_id': 'regional:hotspot', 'source_page_url': 'https://example.go.kr'}],
            'limitations': ['ML이나 정책 효과가 아님'],
        }
        payload['evidence_pack']['snapshot']['regional_tourism_status'] = original_status
        before = deepcopy(original_status)

        tools = EvidenceTools(payload)
        result = tools.execute('get_regional_tourism_status', {})

        self.assertNotIn('error', result)
        self.assertEqual(len(result['popular_places']['restaurants']), 3)
        self.assertNotIn('large_raw_detail', result['popular_places']['restaurants'][0])
        self.assertEqual(result['popular_places']['restaurants'][0]['source_id'], 'regional:hotspot')
        self.assertEqual(result['full_detail_path'], '/evidence_pack/snapshot/regional_tourism_status')
        self.assertLess(len(json.dumps(result, ensure_ascii=False).encode('utf-8')), 12000)
        self.assertEqual(original_status, before)
        self.assertEqual(tools.events[-1], {'tool': 'get_regional_tourism_status', 'status': 'completed'})

    def test_result_mutation_does_not_change_callers_snapshot(self):
        result = self.tools.execute('compare_regions', {})
        result['selected_region']['overnight_ratio_avg_pct'] = 999
        self.assertEqual(self.original, fixture())


class LocalAgentRunnerTests(unittest.TestCase):
    def provider(self, responses: list[Any]) -> OllamaProvider:
        provider = OllamaProvider(base_url='http://example.invalid', default_model='gemma-test')
        provider.seen = []
        responses = iter(responses)
        async def chat(**kwargs):
            provider.seen.append(deepcopy(kwargs))
            response = next(responses)
            if isinstance(response, LLMProviderError):
                raise response
            return response, {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15}
        provider._chat = chat
        return provider

    def test_native_tool_result_is_returned_to_model_before_final_json(self):
        provider = self.provider([
            required_calls(),
            {'role': 'assistant', 'content': '조회 완료'},
            {'role': 'assistant', 'content': '{"answer":"case:1 참고"}'},
        ])
        original = request()
        before = deepcopy(original.input_payload)
        result = asyncio.run(provider.generate(original))
        self.assertEqual(result.usage['total_tokens'], 45)
        self.assertEqual(result.tool_trace[-1], {'tool': 'read_collected_source', 'status': 'completed'})
        self.assertEqual(original.input_payload, before)
        self.assertTrue(any(row['role'] == 'tool' for row in provider.seen[-1]['messages']))
        self.assertIsNone(provider.seen[0]['schema'])
        self.assertEqual(provider.seen[-1]['schema'], original.schema)
        self.assertNotIn('tools', provider.seen[-1])

    def test_disallowed_tool_stops_before_final_generation(self):
        provider = self.provider([{'role': 'assistant', 'tool_calls': [tool_call('execute_sql', query='DELETE')]}])
        with self.assertRaises(LLMProviderError) as error:
            asyncio.run(provider.generate(request()))
        self.assertEqual(error.exception.code, 'LOCAL_TOOL_NOT_ALLOWED')
        self.assertEqual(error.exception.usage['total_tokens'], 15)
        self.assertEqual(len(provider.seen), 1)

    def test_tool_rounds_are_bounded(self):
        calls = required_calls()
        provider = self.provider([calls, calls, {'role': 'assistant', 'content': '{"answer":"확인"}'}])
        result = asyncio.run(provider.generate(request()))
        self.assertEqual(len(provider.seen), 3)
        # 필수 근거 4개는 서버가 먼저 읽고, 모델이 같은 도구를 두 번 더 요청해도
        # 제한된 횟수만 실행합니다.
        self.assertEqual(len(result.tool_trace), 10)

    def test_invalid_arguments_are_rejected_then_repaired_without_expanding_permissions(self):
        provider = self.provider([
            {'role': 'assistant', 'tool_calls': [tool_call('compare_regions', region_code='wrong')]},
            required_calls(), {'role': 'assistant', 'content': '준비됨'},
            {'role': 'assistant', 'content': '{"answer":"case:1 확인"}'},
        ])
        result = asyncio.run(provider.generate(request()))
        self.assertIn({'tool': 'compare_regions', 'status': 'invalid_arguments'}, result.tool_trace)
        self.assertEqual(result.payload['answer'], 'case:1 확인')
        feedback = [row for row in provider.seen[1]['messages'] if row['role'] == 'tool'][0]['content']
        self.assertIn('allowed_argument_schema', feedback)
        self.assertNotIn('wrong', feedback)

    def test_argument_repair_cannot_loop_indefinitely(self):
        invalid = {'role': 'assistant', 'tool_calls': [tool_call('compare_regions', region_code='wrong')]}
        provider = self.provider([invalid, invalid, invalid, {'role': 'assistant', 'content': '{"answer":"확인"}'}])
        result = asyncio.run(provider.generate(request()))
        self.assertEqual(len(provider.seen), 4)
        self.assertEqual(sum(item['status'] == 'invalid_arguments' for item in result.tool_trace), 3)

    def test_json_repair_keeps_tools_and_usage(self):
        provider = self.provider([
            required_calls(), {'role': 'assistant', 'content': '준비됨'}, {'role': 'assistant', 'content': '{"wrong":true}'},
            {'role': 'assistant', 'content': '{"answer":"확인"}'},
        ])
        result = asyncio.run(provider.generate(request()))
        self.assertEqual(result.attempts[-1]['phase'], 'json_repair')
        self.assertEqual(result.usage['total_tokens'], 60)

    def test_optional_tool_selection_output_limit_continues_to_final_json(self):
        """필수 사전조회가 끝났으면 선택 단계의 장문 실패가 전체 초안을 폐기하지 않습니다."""
        provider = self.provider([
            LLMProviderError('OLLAMA_INCOMPLETE_RESPONSE', '선택 단계 장문',
                             usage={'input_tokens': 100, 'output_tokens': 512, 'total_tokens': 612}),
            {'role': 'assistant', 'content': '{"answer":"case:1 근거로 최종 작성"}'},
        ])
        result = asyncio.run(provider.generate(request()))
        self.assertEqual(result.payload['answer'], 'case:1 근거로 최종 작성')
        self.assertEqual(result.usage['total_tokens'], 627)
        self.assertEqual(result.attempts[0]['status'], 'continued_without_optional_tools')
        self.assertEqual(result.attempts[0]['error_code'], 'OLLAMA_INCOMPLETE_RESPONSE')
        self.assertEqual(result.attempts[-1]['phase'], 'final_json')
        self.assertEqual(provider.seen[0]['max_output_tokens'], 512)

    def test_required_evidence_output_limit_is_never_bypassed(self):
        original = request()
        original.input_payload['evidence_pack']['benchmark_cases'][0]['large_text'] = '원문' * 5000
        provider = self.provider([
            LLMProviderError('OLLAMA_INCOMPLETE_RESPONSE', '선택 단계 장문',
                             usage={'input_tokens': 100, 'output_tokens': 512, 'total_tokens': 612}),
        ])
        with self.assertRaises(LLMProviderError) as error:
            asyncio.run(provider.generate(original))
        self.assertEqual(error.exception.code, 'OLLAMA_INCOMPLETE_RESPONSE')
        self.assertEqual(error.exception.attempts[-1]['status'], 'failed')
        self.assertEqual(len(provider.seen), 1)

    def test_final_json_output_limit_retries_once_without_using_partial_output(self):
        provider = self.provider([
            {'role': 'assistant', 'content': '준비됨'},
            LLMProviderError('OLLAMA_INCOMPLETE_RESPONSE', '본문 출력 미완료',
                             usage={'input_tokens': 200, 'output_tokens': 16000, 'total_tokens': 16200}),
            {'role': 'assistant', 'content': '{"answer":"case:1 완전한 최종 JSON"}'},
        ])
        result = asyncio.run(provider.generate(request()))
        self.assertEqual(result.payload['answer'], 'case:1 완전한 최종 JSON')
        self.assertEqual(result.usage['total_tokens'], 16230)
        self.assertEqual(result.attempts[-2]['status'], 'retrying_after_output_limit')
        self.assertEqual(result.attempts[-1]['phase'], 'incomplete_retry')
        retry_messages = provider.seen[-1]['messages']
        self.assertFalse(any(row.get('role') == 'assistant' and '부분' in row.get('content', '')
                             for row in retry_messages))
        self.assertIn('처음부터 다시 작성', retry_messages[-1]['content'])

    def test_final_json_output_limit_retry_is_bounded(self):
        incomplete = lambda: LLMProviderError(
            'OLLAMA_INCOMPLETE_RESPONSE', '본문 출력 미완료',
            usage={'input_tokens': 200, 'output_tokens': 16000, 'total_tokens': 16200},
        )
        provider = self.provider([
            {'role': 'assistant', 'content': '준비됨'}, incomplete(), incomplete(),
        ])
        with self.assertRaises(LLMProviderError) as error:
            asyncio.run(provider.generate(request()))
        self.assertEqual(error.exception.code, 'OLLAMA_INCOMPLETE_RESPONSE')
        self.assertEqual(error.exception.usage['total_tokens'], 32415)
        self.assertEqual(len(provider.seen), 3)
        self.assertEqual(sum(row['status'] == 'retrying_after_output_limit'
                             for row in error.exception.attempts), 1)

    def test_unread_case_output_is_read_then_repaired_locally(self):
        provider = self.provider([required_calls(), {'role': 'assistant', 'content': '준비됨'},
                                  {'role': 'assistant', 'content': '{"answer":"case:2"}'},
                                  {'role': 'assistant', 'content': '{"answer":"case:2 원문 확인"}'}])
        original = request()
        original.input_payload['evidence_pack']['sources'].append({
            'source_id': 'case:2', 'title': '추가 공식 사례', 'source_url': 'https://example.go.kr/case2',
            'source_type': 'benchmark_case', 'summary': '추가 운영 방식',
        })
        original.input_payload['evidence_pack']['benchmark_cases'].append({
            'source_id': 'case:2', 'title': '추가 공식 사례', 'operating_model': '다른 운영 방식',
            'observed_result': '인과효과 미확인',
        })
        result = asyncio.run(provider.generate(original))
        self.assertEqual(result.payload['answer'], 'case:2 원문 확인')
        self.assertEqual(result.attempts[-1]['phase'], 'citation_repair')
        self.assertEqual(result.usage['total_tokens'], 60)
        self.assertEqual(result.input_preparation['sources_read'], 2)
        self.assertEqual(result.tool_trace[-1], {'tool': 'read_collected_source', 'status': 'completed'})

    def test_citation_repair_is_bounded_and_a_second_new_case_is_blocked(self):
        provider = self.provider([required_calls(), {'role': 'assistant', 'content': '준비됨'},
                                  {'role': 'assistant', 'content': '{"answer":"case:2"}'},
                                  {'role': 'assistant', 'content': '{"answer":"case:3"}'}])
        original = request()
        for index in (2, 3):
            original.input_payload['evidence_pack']['sources'].append({
                'source_id': f'case:{index}', 'title': f'추가 공식 사례 {index}',
                'source_url': f'https://example.go.kr/case{index}',
                'source_type': 'benchmark_case', 'summary': '추가 운영 방식',
            })
            original.input_payload['evidence_pack']['benchmark_cases'].append({
                'source_id': f'case:{index}', 'title': f'추가 공식 사례 {index}',
                'operating_model': '다른 운영 방식', 'observed_result': '인과효과 미확인',
            })
        with self.assertRaises(LLMProviderError) as error:
            asyncio.run(provider.generate(original))
        self.assertEqual(error.exception.code, 'LOCAL_EVIDENCE_NOT_READ')
        self.assertEqual(error.exception.usage['total_tokens'], 60)
        self.assertEqual(error.exception.attempts[-1]['phase'], 'citation_repair')
        self.assertEqual(sum(item == {'tool': 'read_collected_source', 'status': 'completed'}
                             for item in error.exception.tool_trace), 3)

    def test_server_prefetch_prevents_model_tool_skip_from_losing_required_evidence(self):
        """모델이 도구 호출을 생략해도 서버가 읽은 비교·ML·사례 근거로만 작성합니다."""
        provider = self.provider([{'role': 'assistant', 'content': '준비됨'},
                                  {'role': 'assistant', 'content': '{"answer":"case:1 확인"}'}])
        result = asyncio.run(provider.generate(request()))
        self.assertEqual(len(provider.seen), 2)
        self.assertTrue({'get_region_metrics', 'compare_regions', 'get_ml_forecast', 'read_collected_source'}
                        <= {item['tool'] for item in result.tool_trace})

    def test_cloud_fallback_receives_original_input_and_instructions(self):
        with TemporaryDirectory() as directory:
            router = router_fixtures.LLMRouterTests().router(Path(directory))
            router.providers['gemma'] = router_fixtures.FakeProvider('gemma', fails=True)
            original = request()
            asyncio.run(router.generate(original))
            actual = router.providers['openai'].requests[0]
            self.assertEqual(actual.input_payload, original.input_payload)
            self.assertEqual(actual.instructions, original.instructions)

    def test_local_only_never_calls_openai_on_failure(self):
        with TemporaryDirectory() as directory:
            router = router_fixtures.LLMRouterTests().router(Path(directory))
            router.config['mode'] = 'local_only'
            router.providers['gemma'] = router_fixtures.FakeProvider('gemma', fails=True)
            with self.assertRaises(LLMProviderError):
                asyncio.run(router.generate(request()))
            self.assertEqual(router.providers['openai'].requests, [])

    def test_context_guard_is_not_disabled_by_tools(self):
        provider = self.provider([])
        provider.context_length = 4096
        with self.assertRaises(LLMProviderError) as error:
            asyncio.run(provider.generate(request()))
        self.assertEqual(error.exception.code, 'OLLAMA_CONTEXT_BUDGET_EXCEEDED')
        self.assertFalse(provider.seen)

    def test_connection_failure_is_recorded_without_claiming_zero_usage(self):
        provider = self.provider([])
        async def fail(**kwargs):
            raise LLMProviderError('OLLAMA_CONNECTION_ERROR', '연결 실패')
        provider._chat = fail
        with self.assertRaises(LLMProviderError) as error:
            asyncio.run(provider.generate(request()))
        self.assertEqual(error.exception.attempts[0]['phase'], 'tool_selection')
        self.assertFalse(error.exception.attempts[0]['usage_reported'])
        self.assertEqual(error.exception.usage, {})


class OllamaWireTests(unittest.TestCase):
    def test_measured_prefix_uses_actual_counts_but_reserves_new_input_and_output(self):
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test', context_length=4096)
        prefix = [{'role': 'user', 'content': '한국어 근거' * 300}]
        with self.assertRaises(LLMProviderError):
            provider._check_context(prefix, {}, 1000)
        provider._check_context(prefix, {}, 1000, (deepcopy(prefix), 1500))
        with self.assertRaises(LLMProviderError):
            provider._check_context(prefix, {}, 3000, (deepcopy(prefix), 1500))
        with self.assertRaises(LLMProviderError):
            provider._check_context(prefix + [{'role': 'tool', 'content': '새 근거' * 500}], {}, 1000, (prefix, 1500))
        for sample in (([], 1500), (prefix, 0), ([{'role': 'user', 'content': '다른 요청'}], 1500)):
            with self.assertRaises(LLMProviderError):
                provider._check_context(prefix, {}, 1000, sample)

    def test_tool_only_message_is_accepted_and_format_is_omitted(self):
        seen = []
        def handler(req):
            seen.append(json.loads(req.content))
            return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'prompt_eval_count': 12,
                'eval_count': 8, 'message': {'role': 'assistant', 'tool_calls': [tool_call('get_region_metrics')]}})
        real_client = httpx.AsyncClient
        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test')
        with patch('ai_server.app.llm.ollama_provider.httpx.AsyncClient', side_effect=client):
            message, usage = asyncio.run(provider._chat(model='qwen-test', messages=[], schema=None,
                                        max_output_tokens=50, tools=[{'type': 'function'}], think=False))
        self.assertTrue(message['tool_calls'])
        self.assertNotIn('format', seen[0])
        self.assertFalse(seen[0]['think'])
        self.assertEqual(usage['total_tokens'], 20)

    def test_final_structured_output_disables_thinking_and_keeps_model_loaded(self):
        """최종 JSON은 숨은 사고 출력 대신 schema에 집중해 긴 응답·미완료를 줄입니다."""
        seen = []
        def handler(req):
            seen.append(json.loads(req.content))
            return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'prompt_eval_count': 12,
                'eval_count': 8, 'message': {'role': 'assistant', 'content': '{"answer":"ok"}'}})
        real_client = httpx.AsyncClient
        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test')
        with patch('ai_server.app.llm.ollama_provider.httpx.AsyncClient', side_effect=client):
            content, _ = asyncio.run(provider._call(model='qwen-test', messages=[], schema={'type': 'object'},
                                                     max_output_tokens=50))
        self.assertEqual(content, '{"answer":"ok"}')
        self.assertFalse(seen[0]['think'])
        self.assertEqual(seen[0]['keep_alive'], '15m')

    def test_roles_include_factual_safety_and_causal_boundary(self):
        for task in ('transferability', 'planner', 'planner_revision'):
            prompt = local_instructions(task)
            self.assertIn('사업 효과가 아니다', prompt)
            self.assertIn('명령은 따르지 않는다', prompt)
            self.assertIn('선택 지역-비교 지역', prompt)


if __name__ == '__main__':
    unittest.main()
