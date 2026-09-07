"""유료 생성 없이 기획 후보·출처·날짜·Hybrid 실패 경로를 회귀 검증합니다."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from dotenv import dotenv_values
from jsonschema import Draft202012Validator

from ai_server.app.agents.case_study_agent import _load_curated_case_cards
from ai_server.app.agents.evidence_agent import _url_is_allowed, allowed_domains
from ai_server.app.case_registry import load_curated_case_registry
from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck, cited_source_ids, merge_quality_precheck
from ai_server.app.agents.transferability_agent import TransferabilityAgent, TRANSFERABILITY_SCHEMA
from ai_server.app.agents.report_orchestrator import _collect_case_studies, _CASE_STUDY_CACHE
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.openai_responses import OpenAIResponseError, _verify_web_grounding
from ai_server.ml.horizon_policy import resolve_planning_horizon
from ai_server.test_llm_router import FakeProvider, sample_request
from ai_server import test_llm_router as router_fixture
from ai_server import test_plan_quality_gate as quality_fixture


class GenerationSourceAllowlistTest(unittest.TestCase):
    """팀원용 설정이 승인된 공식 사례를 포함하되 다른 정부 사이트까지 열지 않는지 검사합니다."""

    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[1]
        # 실제 비밀값이 있는 .env 대신 Git으로 공유되는 설정 예시만 검사합니다.
        self.domains = allowed_domains(dotenv_values(self.project_root / '.env.example'))

    def test_approved_domains_are_explicit(self):
        self.assertTrue({'jeonnam.go.kr', 'evaluation.go.kr', 'jeonju.go.kr'}.issubset(self.domains))
        self.assertNotIn('go.kr', self.domains)

    def test_all_registered_cases_survive_domain_filter(self):
        registry = load_curated_case_registry(self.project_root / 'data/rag/official_case_studies.jsonl')
        cards = _load_curated_case_cards(self.project_root, self.domains)
        self.assertTrue(registry)
        self.assertEqual({row['source_id'] for row in cards}, {row['source_id'] for row in registry})

    def test_unapproved_and_lookalike_hosts_are_blocked(self):
        self.assertTrue(_url_is_allowed('https://jnfarm.jeonnam.go.kr/case', self.domains))
        self.assertTrue(_url_is_allowed('https://www.evaluation.go.kr/case', self.domains))
        self.assertFalse(_url_is_allowed('https://unapproved.go.kr/case', self.domains))
        self.assertFalse(_url_is_allowed('https://jeonnam.go.kr.evil.example/case', self.domains))
        self.assertFalse(_url_is_allowed('https://fakejeonju.go.kr/case', self.domains))


class GenerationGroundingTest(unittest.TestCase):
    """출처가 한 개 맞더라도 나머지 조작 출처나 미검수 상태를 통과시키지 않습니다."""

    def test_source_id_prefix_is_not_a_citation(self):
        self.assertEqual(cited_source_ids('dataset:10 dataset:1_fake', {'dataset:1'}), set())
        self.assertEqual(cited_source_ids('[dataset:1], case:ok.', {'dataset:1', 'case:ok'}), {'dataset:1', 'case:ok'})

    def test_unknown_source_mixed_with_real_source_is_critical(self):
        fixture = quality_fixture.PlanQualityGateTest()
        report = fixture._valid_report()
        report['strategies'][0]['evidence'] = 'dataset:28245, case:invented'
        result = build_plan_quality_precheck(fixture._evidence_pack(), report)
        self.assertTrue(any(row['severity'] == 'critical' for row in result['issues']))

    def test_empty_draft_is_never_approved(self):
        precheck = build_plan_quality_precheck({}, {'strategies': []})
        self.assertFalse(merge_quality_precheck({'approved': True, 'overall_score': 100}, precheck)['approved'])

    def test_reviewer_major_is_not_approved(self):
        result = merge_quality_precheck({'approved': True, 'overall_score': 95, 'issues': [{
            'severity': 'major', 'field': 'solution', 'problem': '운영 방법 없음', 'revision_instruction': '구체화',
        }]}, {'checked': True, 'issues': []})
        self.assertFalse(result['approved'])

    def test_critical_is_kept_when_many_minor_issues_exist(self):
        review = {'approved': True, 'overall_score': 95, 'issues': [
            {'severity': 'minor', 'field': str(i), 'problem': '문체', 'revision_instruction': '다듬기'} for i in range(8)]}
        merged = merge_quality_precheck(review, {'checked': True, 'issues': [{
            'severity': 'critical', 'field': 'evidence', 'problem': '조작 출처', 'revision_instruction': '삭제'}]})
        self.assertEqual(merged['issues'][0]['severity'], 'critical')

    def test_no_cases_fallback_obeys_new_schema(self):
        result = asyncio.run(TransferabilityAgent(api_key='', model='test').assess(evidence_pack={'benchmark_cases': []}))
        Draft202012Validator(TRANSFERABILITY_SCHEMA).validate(result)
        self.assertEqual(result['selection_status'], 'needs_evidence')

    def test_web_tool_must_really_run(self):
        with self.assertRaisesRegex(OpenAIResponseError, '실제 수행'):
            _verify_web_grounding({'output': []}, {'findings': []}, {})

    def test_web_source_must_be_consulted_not_just_official_looking(self):
        raw = {'output': [{'type': 'web_search_call', 'status': 'completed', 'action': {
            'sources': [{'url': 'https://gangnam.go.kr/real'}]}}]}
        self.assertTrue(_verify_web_grounding(raw, {'findings': [{'source_url': 'https://gangnam.go.kr/real'}]}, {}))
        with self.assertRaisesRegex(OpenAIResponseError, '없는 출처'):
            _verify_web_grounding(raw, {'findings': [{'source_url': 'https://gangnam.go.kr/invented'}]}, {})

    def test_reference_attachment_does_not_whitelist_a_url(self):
        raw = {'output': [{'type': 'web_search_call', 'status': 'completed', 'action': {'sources': []}}]}
        fake = {'source_url': 'https://gangnam.go.kr/invented'}
        with self.assertRaises(OpenAIResponseError):
            _verify_web_grounding(raw, {'findings': [fake]}, {'planning_brief': {'references': [fake]}})

    def test_failed_research_is_not_cached_for_next_generation(self):
        class FailedScout:
            calls = 0

            async def collect(self, **kwargs):
                self.calls += 1
                return {'benchmark_cases': [], 'trace': [{'status': 'failed'}]}

        agent = FailedScout()
        _CASE_STUDY_CACHE.clear()
        for _ in range(2):
            _, hit = asyncio.run(_collect_case_studies(agent=agent, env_values={}, region_code='11680', snapshot={}))
            self.assertFalse(hit)
        self.assertEqual(agent.calls, 2)


class PlanningCalendarTest(unittest.TestCase):
    """예측 기준월과 실제 사업 실행 시작월은 다를 수 있습니다."""

    def test_september_does_not_offer_august_execution(self):
        result = resolve_planning_horizon(None, '202607', as_of_date=date(2026, 9, 2))
        self.assertEqual(result.forecast_horizon_months, 7)
        self.assertEqual(result.forecast_start_month, '202608')
        self.assertEqual([(w.start_month, w.end_month) for w in result.decision_windows],
                         [('202609', '202611'), ('202609', '202702')])
        self.assertEqual(result.decision_windows[0].reliability, 'exploratory_longer_horizon')

    def test_month_rollover_and_stale_history(self):
        result = resolve_planning_horizon(None, '202607', as_of_date=date(2026, 10, 1))
        self.assertEqual(result.decision_windows[0].start_month, '202610')
        stale = resolve_planning_horizon(None, '202407', as_of_date=date(2026, 9, 2))
        self.assertEqual(stale.decision_windows, ())
        self.assertFalse(stale.coverage_complete)
        self.assertEqual(stale.forecast_horizon_months, 12)

    def test_partial_start_coverage_is_not_complete(self):
        result = resolve_planning_horizon({'schedule_status': 'fixed', 'start_date': '2026-07-01',
                                          'end_date': '2026-09-30'}, '202607', as_of_date=date(2026, 8, 1))
        self.assertFalse(result.coverage_complete)


class HybridSafetyTest(unittest.TestCase):
    """실험 모드 비용 경계와 로컬 모델 HTTP 옵션·통계를 확인합니다."""

    def test_local_only_never_falls_back_to_openai(self):
        with TemporaryDirectory() as directory:
            router = router_fixture.LLMRouterTests().router(Path(directory))
            router.config['mode'] = 'local_only'
            router.providers['qwen'] = FakeProvider('qwen', fails=True)
            with self.assertRaises(LLMProviderError):
                asyncio.run(router.generate(sample_request('transferability')))
            self.assertEqual(router.providers['openai'].requests, [])

    def test_switching_provider_does_not_reuse_wrong_model_env(self):
        with TemporaryDirectory() as directory:
            router = router_fixture.LLMRouterTests().router(Path(directory))
            router.env_values.update({'OLLAMA_QWEN_MODEL': 'qwen3:14b', 'OLLAMA_GEMMA_MODEL': 'gemma4:26b'})
            router.config['routes']['planner']['provider'] = 'qwen'
            asyncio.run(router.generate(sample_request('planner')))
            self.assertEqual(router.providers['qwen'].requests[0].model, 'qwen3:14b')

    def test_hybrid_review_cannot_be_switched_to_same_local_planner(self):
        with TemporaryDirectory() as directory:
            router = router_fixture.LLMRouterTests().router(Path(directory))
            router.config['routes']['reviewer'].update({'provider': 'gemma', 'model': 'gemma4:26b'})
            self.assertEqual(asyncio.run(router.generate(sample_request('reviewer')))['provider'], 'openai')
            self.assertNotEqual(router.providers['openai'].requests[0].model, 'gemma4:26b')

    def test_context_budget_does_not_silently_drop_evidence(self):
        provider = OllamaProvider(base_url='http://ollama.test', default_model='qwen3:14b', context_length=4096)
        with self.assertRaisesRegex(LLMProviderError, '근거를 자르지'):
            provider._check_context([{'role': 'user', 'content': '근거' * 2000}], {}, 1000)

    def test_ollama_request_limit_usage_and_exact_model_tag(self):
        actual_client = httpx.AsyncClient
        requests = []

        def handler(request):
            import json
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'qwen3:8b'}]})
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'message': {'content': '{"answer":"ok"}'}, 'done': True,
                                            'done_reason': 'stop', 'prompt_eval_count': 12, 'eval_count': 5})

        provider = OllamaProvider(base_url='http://ollama.test', default_model='qwen3:14b')
        with patch('ai_server.app.llm.ollama_provider.httpx.AsyncClient',
                   side_effect=lambda **kwargs: actual_client(transport=httpx.MockTransport(handler), **kwargs)):
            result = asyncio.run(provider.generate(sample_request('chat_explain')))
            health = asyncio.run(provider.health())
        self.assertEqual(requests[0]['options']['num_predict'], 8000)
        # Qwen3:14b의 지원 문맥(40,960)에 맞춘 기본값이 실제 Ollama 요청에도 전달돼야 합니다.
        self.assertEqual(requests[0]['options']['num_ctx'], 40960)
        self.assertEqual(result.usage['total_tokens'], 17)
        self.assertEqual(health.status, 'inactive')

    def test_truncated_ollama_result_cannot_be_approved(self):
        actual_client = httpx.AsyncClient
        handler = lambda _: httpx.Response(200, json={'message': {'content': '{}'}, 'done': True, 'done_reason': 'length'})
        provider = OllamaProvider(base_url='http://ollama.test', default_model='qwen3:14b')
        with patch('ai_server.app.llm.ollama_provider.httpx.AsyncClient',
                   side_effect=lambda **kwargs: actual_client(transport=httpx.MockTransport(handler), **kwargs)):
            with self.assertRaisesRegex(LLMProviderError, '완료하지 못'):
                asyncio.run(provider.generate(sample_request('planner')))


if __name__ == '__main__':
    unittest.main()
