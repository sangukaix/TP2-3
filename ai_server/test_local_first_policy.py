"""실제 OpenAI·개인 GPU 호출 없이 로컬 우선 비용 정책과 품질 차단을 검증합니다."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from ai_server.app.agents.decision_facts import build_decision_facts, comparison_direction_issues, past_execution_month_issues
from ai_server.app.agents.evidence_agent import _reusable_policy_sources
from ai_server.app.agents.report_orchestrator import orchestrate_strategy_report, _evidence_cache_key, _case_study_cache_key
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.evidence_tools import EvidenceTools, compact_json
from ai_server.app.llm.models import ProviderHealth
from ai_server.app.rag_store import OfficialTourismRagStore
from ai_server.test_llm_router import FakeProvider, sample_request
from ai_server import test_llm_router as router_fixtures
from ai_server.test_report_orchestrator import FakeEvidenceAgent, FakeCaseStudyAgent, FakeTransferabilityAgent, FakePlannerAgent


class LocalFirstRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.router = router_fixtures.LLMRouterTests().router(Path(self.directory.name))
        self.router.config['mode'] = 'local_first'

    async def test_routes_and_status_reflect_actual_local_first_providers(self):
        for task, expected in [('transferability', 'qwen'), ('reviewer', 'qwen'), ('planner', 'gemma'),
                               ('planner_revision', 'gemma'), ('chat_explain', 'qwen'), ('final_reviewer', 'openai')]:
            self.assertEqual((await self.router.generate(sample_request(task)))['provider'], expected)
        status = await self.router.status()
        self.assertEqual(status['effective_routes']['reviewer']['provider'], 'qwen')
        self.assertEqual(status['effective_routes']['planner']['fallback'], 'none')
        self.assertFalse(status['cost_policy']['automatic_paid_fallback'])

    async def test_local_failure_does_not_fallback_even_with_old_saved_setting(self):
        self.router.providers['gemma'] = FakeProvider('gemma', fails=True)
        self.router.config['routes']['planner']['fallback'] = 'openai'
        with self.assertRaises(LLMProviderError):
            await self.router.generate(sample_request('planner'))
        self.assertEqual(self.router.providers['openai'].requests, [])

    async def test_failed_preflight_does_not_start_paid_request(self):
        self.router.providers['qwen'].health = AsyncMock(return_value=ProviderHealth('ollama', 'inactive', 'offline', []))
        with self.assertRaises(LLMProviderError) as error:
            await self.router.preflight_local_models()
        self.assertEqual(error.exception.code, 'LOCAL_FIRST_MODELS_UNAVAILABLE')
        self.assertEqual(self.router.providers['openai'].requests, [])

    async def test_preflight_recovers_after_one_temporary_connection_failure(self):
        model = self.router.effective_routes()['transferability']['model']
        self.router.providers['qwen'].health = AsyncMock(side_effect=[
            ProviderHealth('ollama', 'inactive', 'temporary'),
            ProviderHealth('ollama', 'active', 'connected', [model]),
        ])
        await self.router.preflight_local_models()
        self.assertEqual(self.router.providers['qwen'].health.await_count, 2)
        self.assertEqual(self.router.providers['openai'].requests, [])

    async def test_parallel_requests_cannot_exceed_three_or_retry_automatically(self):
        requests = [replace(sample_request('evidence', web=True), retry_max_output_tokens=24000) for _ in range(4)]
        results = await asyncio.gather(*(self.router.generate(request) for request in requests), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, LLMProviderError) for result in results), 1)
        actual = self.router.providers['openai'].requests
        self.assertEqual(len(actual), 3)
        self.assertTrue(all(request.retry_max_output_tokens is None for request in actual))
        self.assertTrue(all(request.retry_max_output_tokens == 24000 for request in requests))
        self.assertFalse(self.router.trace[-1]['provider_called'])

    async def test_failures_consume_budget_and_unapproved_cloud_tasks_are_blocked(self):
        self.router.providers['openai'].fails = True
        for _ in range(4):
            with self.assertRaises(LLMProviderError):
                await self.router.generate(sample_request('evidence', web=True))
        self.assertEqual(len(self.router.providers['openai'].requests), 3)
        with self.assertRaises(LLMProviderError):
            await self.router.generate(sample_request('planner', web=True))
        self.assertEqual(len(self.router.providers['openai'].requests), 3)

    async def test_runtime_configuration_accepts_local_first(self):
        result = self.router.update_config({'mode': 'local_first', 'routes': {}})
        self.assertEqual(result['mode'], 'local_first')
        self.assertTrue(router_fixtures.LLMRouterTests().router(Path(self.directory.name)).local_first)

    async def test_student_budget_uses_local_agents_and_only_one_final_audit(self):
        """학생 절약 모드는 조사 웹 호출을 숨기지 않고 최종 독립 검수 한 번만 허용합니다."""
        self.router.config['mode'] = 'student_budget'
        for task, expected in [('transferability', 'qwen'), ('reviewer', 'qwen'), ('planner', 'gemma')]:
            self.assertEqual((await self.router.generate(sample_request(task)))['provider'], expected)

        status = await self.router.status()
        self.assertTrue(status['cost_policy']['student_budget'])
        self.assertEqual(status['cost_policy']['max_cloud_calls_per_generation'], 1)
        self.assertEqual(status['effective_routes']['evidence']['provider'], 'local_sources')
        self.assertEqual(status['effective_routes']['case_study']['provider'], 'local_sources')
        self.assertEqual((await self.router.generate(sample_request('local_web_query_planner')))['provider'], 'qwen')

        self.assertEqual((await self.router.generate(sample_request('final_reviewer')))['provider'], 'openai')
        with self.assertRaisesRegex(LLMProviderError, '유료 호출 제한'):
            await self.router.generate(sample_request('final_reviewer'))
        self.assertEqual(len(self.router.providers['openai'].requests), 1)

    async def test_student_budget_blocks_unexpected_web_search_without_openai(self):
        self.router.config['mode'] = 'student_budget'
        with self.assertRaisesRegex(LLMProviderError, '학생 절약 모드'):
            await self.router.generate(sample_request('evidence', web=True))
        self.assertEqual(self.router.providers['openai'].requests, [])

    async def test_runtime_configuration_accepts_student_budget(self):
        result = self.router.update_config({'mode': 'student_budget', 'routes': {}})
        self.assertEqual(result['mode'], 'student_budget')
        persisted = router_fixtures.LLMRouterTests().router(Path(self.directory.name))
        self.assertTrue(persisted.student_budget)


class EvidenceReuseTests(unittest.IsolatedAsyncioTestCase):
    def test_policy_reuse_excludes_duplicates_other_regions_and_future_dates(self):
        base = {'region_code': '11680', 'document_type': 'policy', 'source_url': 'https://gangnam.go.kr/policy',
                'published_or_updated_at': '2026-09-01'}
        rows = [base, deepcopy(base), {**base, 'source_url': 'https://gangnam.go.kr/2', 'region_code': 'ALL'},
                {**base, 'source_url': 'https://gangnam.go.kr/3', 'published_or_updated_at': '2026-12-01'},
                {**base, 'source_url': 'https://gangnam.go.kr/4', 'published_or_updated_at': '확인 필요'},
                {**base, 'source_url': 'https://gangnam.go.kr/5', 'published_or_updated_at': '2025-12-01'}]
        self.assertEqual(_reusable_policy_sources(rows, '11680', today=date(2026, 9, 2)), [base])

    async def test_local_rag_never_calls_embedding_api_and_filters_sources(self):
        base = {'region_code': '11680', 'source_url': 'https://gangnam.go.kr/policy', 'source_id': 'a'}
        metadata = [base, {**base, 'source_url': 'https://evil.invalid'},
                    {**base, 'region_code': '99999'}, {**base, 'source_url': 'http://gangnam.go.kr/policy'},
                    {**base, 'source_id': ''}]
        collection = SimpleNamespace(count=lambda: len(metadata), get=lambda **_: {'documents': ['관광 소비 정책'] * 5, 'metadatas': metadata})
        store = OfficialTourismRagStore(persist_directory=Path('.'), api_key='unused', embedding_model='unused', allowed_domains=['gangnam.go.kr'])
        store._collection = lambda: collection
        store._embeddings = AsyncMock(side_effect=AssertionError('유료 임베딩 금지'))
        result = await store.search(query='관광 소비', region_code='11680', region_name='강남구', local_only=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['retrieval_method'], 'local_keyword')
        self.assertNotIn('relevance_score', result[0])
        store._embeddings.assert_not_called()

    async def test_curated_pdf_reference_is_searchable_without_chroma_or_embedding(self):
        """사람이 검수한 공식 PDF 요약은 Chroma 색인 전에도 local_first 근거가 됩니다."""
        with TemporaryDirectory() as directory:
            registry = Path(directory) / 'official_reference_documents.jsonl'
            registry.write_text(
                '{"source_id":"reference:kto:test","region_code":"ALL","region_name":"전국 공통",'
                '"document_type":"policy","title":"공식 지방관광 참고문서",'
                '"source_url":"https://visitkorea.or.kr/reference","published_or_updated_at":"2026-08",'
                '"content":"지역 체류와 소비 전환은 이동 편의와 참여 사업자 운영 조건을 함께 측정해야 한다.",'
                '"keywords":["체류","소비","이동"]}\n', encoding='utf-8'
            )
            collection = SimpleNamespace(count=lambda: 0)
            store = OfficialTourismRagStore(
                persist_directory=Path(directory) / 'chroma', api_key='unused', embedding_model='unused',
                allowed_domains=['visitkorea.or.kr'], local_reference_path=registry,
            )
            store._collection = lambda: collection
            store._embeddings = AsyncMock(side_effect=AssertionError('유료 임베딩 금지'))
            result = await store.search(
                query='관광 체류 소비 이동', region_code='11680', region_name='서울특별시 강남구', local_only=True,
            )
        self.assertEqual(result[0]['source_id'], 'reference:kto:test')
        self.assertEqual(result[0]['retrieval_method'], 'local_curated_reference')
        store._embeddings.assert_not_called()

    async def test_curated_pdf_page_chunk_is_searchable_without_chroma_or_embedding(self):
        """페이지 청크는 local_first에서도 원문 쪽수까지 포함해 무료 검색합니다."""
        with TemporaryDirectory() as directory:
            registry = Path(directory) / 'official_reference_documents.jsonl'
            chunk_registry = Path(directory) / 'official_reference_chunks.jsonl'
            registry.write_text('', encoding='utf-8')
            chunk_registry.write_text(
                '{"source_id":"reference:kto:test","parent_source_id":"reference:kto:test",'
                '"chunk_id":"reference:kto:test:page:034:chunk:01","region_code":"ALL",'
                '"region_name":"전국 공통","document_type":"policy","title":"공식 관광 운영문서",'
                '"source_url":"https://visitkorea.or.kr/reference","published_or_updated_at":"2026-08",'
                '"page_references":"PDF 34쪽","approved_for_rag":true,'
                '"content":"지역 체류와 소비 전환은 이동 편의와 참여 사업자 운영 조건을 함께 측정해야 한다.",'
                '"keywords":["체류","소비","이동"]}\n', encoding='utf-8'
            )
            collection = SimpleNamespace(count=lambda: 0)
            store = OfficialTourismRagStore(
                persist_directory=Path(directory) / 'chroma', api_key='unused', embedding_model='unused',
                allowed_domains=['visitkorea.or.kr'], local_reference_path=registry,
            )
            store._collection = lambda: collection
            store._embeddings = AsyncMock(side_effect=AssertionError('유료 임베딩 금지'))
            result = await store.search(
                query='관광 체류 소비 이동', region_code='11680', region_name='서울특별시 강남구', local_only=True,
            )
        self.assertEqual(result[0]['source_id'], 'reference:kto:test')
        self.assertEqual(result[0]['chunk_id'], 'reference:kto:test:page:034:chunk:01')
        self.assertEqual(result[0]['page_references'], 'PDF 34쪽')
        self.assertEqual(result[0]['retrieval_method'], 'local_curated_chunk')
        store._embeddings.assert_not_called()

    def test_case_registry_content_changes_invalidate_both_research_caches(self):
        agent = SimpleNamespace(project_root=Path('unread-test-root'))
        for key_function in (_evidence_cache_key, _case_study_cache_key):
            with patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_bytes', return_value=b'old'):
                old = key_function(agent=agent, env_values={}, region_code='11680', snapshot={})
            with patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_bytes', return_value=b'new'):
                new = key_function(agent=agent, env_values={}, region_code='11680', snapshot={})
            self.assertNotEqual(old, new)


class DecisionFactsTests(unittest.TestCase):
    def snapshot(self):
        return {'nationwide_comparison': {'available': True, 'period': '2025.07~2026.06',
                'peer_regions': [{'region_name': '서울특별시 서초구', 'overnight_ratio_gap_pct_point': 0.9834}],
                'source_records': [{'source_id': 'comparison:1'}]},
                'ml_analysis': {'signals': [{'kind': 'forecast_signal', 'metric': 'visitors', 'forecast_value': 100,
                                            'aggregation': 'sum', 'source_id': 'ml:1'}]}}

    def test_facts_preserve_direction_aggregation_and_causal_boundary(self):
        facts = build_decision_facts(self.snapshot())
        self.assertEqual(facts['peer_comparisons'][0]['direction'], 'higher')
        self.assertEqual(facts['forecast_windows'][0]['forecast_value'], 100)
        self.assertEqual(facts['forecast_windows'][0]['aggregation'], 'sum')
        self.assertEqual(facts['intervention_effect'], 'not_estimated')

    def test_wrong_gap_direction_blocks_but_correct_statement_is_preserved(self):
        wrong = comparison_direction_issues(self.snapshot(), {'summary': '강남 숙박비율은 서초보다 0.9834%p 낮다.'})
        self.assertEqual(wrong[0]['severity'], 'critical')
        self.assertEqual(comparison_direction_issues(self.snapshot(), {'summary': '숙박비율은 서초구보다 0.9834%p 높다.'}), [])
        self.assertEqual(comparison_direction_issues({}, {'summary': '숙박비율은 서초보다 0.9834%p 낮다.'}), [])

    def test_long_draft_requires_every_segment_without_truncation(self):
        draft = {'summary': '관측값과 예측은 구분한다. ' * 900, 'strategies': [{'budget': '견적 × 수량'}]}
        workspace = EvidenceTools({'evidence_pack': {}, 'draft_report': draft})
        parts = []
        for offset in range(len(workspace.draft_segments('/draft_report'))):
            self.assertTrue(workspace.missing_required_reads())
            part = workspace.execute('read_task_section', {'path': '/draft_report', 'offset': offset, 'limit': 1})
            self.assertNotIn('error', part)
            parts.append(part['serialized_json_segment'])
        self.assertEqual(''.join(parts), compact_json(draft))
        self.assertEqual(workspace.missing_required_reads(), [])

    def test_repeating_one_page_cannot_satisfy_draft_read_requirement(self):
        workspace = EvidenceTools({'draft_report': {'summary': '근거 ' * 6000}})
        for _ in range(5):
            workspace.execute('read_task_section', {'path': '/draft_report', 'offset': 0, 'limit': 1})
        self.assertNotIn('/draft_report', workspace.read_paths)
        self.assertTrue(any('offset=1' in missing for missing in workspace.missing_required_reads()))

    def test_past_execution_month_is_blocked_but_historical_evidence_is_not(self):
        snapshot = {'ml_analysis': {'horizon_policy': {'as_of_date': '2026-09-02'}}}
        report = {'summary': '2026년 7월 관측값', 'strategies': [{'implementation_steps': [{'schedule': '2026-08 준비'}]}]}
        self.assertEqual(past_execution_month_issues(snapshot, report)[0]['severity'], 'major')
        report['strategies'][0]['implementation_steps'][0]['schedule'] = '2026-09 ~ 2027-02'
        self.assertEqual(past_execution_month_issues(snapshot, report), [])


class LocalFirstOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def run_report(self, *, local_approved=True, first_fails=False, audit_fails=False, gate_blocks=False, revise_then_pass=False):
        calls = []
        async def review(**kwargs):
            calls.append(kwargs.get('final_pass', False))
            if first_fails or (audit_fails and kwargs.get('final_pass')):
                raise LLMProviderError('TEST_OFFLINE', '연결 중단')
            approved = local_approved or kwargs.get('final_pass') or (revise_then_pass and len(calls) > 1)
            return {'approved': approved, 'overall_score': 90 if approved else 70, 'dimension_scores': {},
                    'strengths': [], 'issues': [], 'summary': '테스트 검수'}
        with TemporaryDirectory() as directory:
            router = router_fixtures.LLMRouterTests().router(Path(directory))
            router.config['mode'] = 'local_first'
            with (patch('ai_server.app.agents.report_orchestrator.LLMRouter', return_value=router),
                  patch('ai_server.app.agents.report_orchestrator.EvidenceAgent', FakeEvidenceAgent),
                  patch('ai_server.app.agents.report_orchestrator.CaseStudyAgent', FakeCaseStudyAgent),
                  patch('ai_server.app.agents.report_orchestrator.TransferabilityAgent', FakeTransferabilityAgent),
                  patch('ai_server.app.agents.report_orchestrator.PlannerAgent', FakePlannerAgent),
                  patch('ai_server.app.agents.report_orchestrator.ReviewerAgent', return_value=SimpleNamespace(review=review)),
                  patch('ai_server.app.agents.report_orchestrator.build_planning_ml_evidence', return_value=SimpleNamespace(
                      model_dump=lambda **_: {}, status='available', reason_code=None, horizon_policy={})),
                  patch('ai_server.app.agents.report_orchestrator.build_plan_quality_precheck', return_value={
                      'checked': True, 'issues': [{'severity': 'critical', 'field': 'test', 'problem': '검증 오류',
                                                 'revision_instruction': '수정 필요'}] if gate_blocks else []})):
                result = await orchestrate_strategy_report(project_root=Path(directory), env_values={}, region_code='11680',
                    snapshot={'region_name': '서울특별시 강남구'}, report_schema={})
        return result, calls

    async def test_approved_local_report_gets_exactly_one_cloud_final_audit(self):
        result, calls = await self.run_report()
        self.assertEqual(calls, [False, True])
        self.assertTrue(result['quality_review']['final_audit_completed'])
        self.assertTrue(result['quality_review']['approved'])

    async def test_local_revision_is_rechecked_locally_before_cloud_audit(self):
        result, calls = await self.run_report(local_approved=False, revise_then_pass=True)
        self.assertEqual(calls, [False, False, True])
        self.assertTrue(result['quality_review']['approved'])

    async def test_low_local_quality_skips_paid_final_audit(self):
        result, calls = await self.run_report(local_approved=False)
        self.assertEqual(calls, [False, False])
        self.assertFalse(result['quality_review']['final_audit_completed'])
        self.assertFalse(result['quality_review']['approved'])

    async def test_code_gate_cannot_be_overridden_by_local_model(self):
        result, calls = await self.run_report(gate_blocks=True)
        self.assertEqual(calls, [False, False])
        self.assertFalse(result['quality_review']['approved'])

    async def test_local_connection_failure_preserves_draft_without_cloud_fallback(self):
        result, calls = await self.run_report(first_fails=True)
        self.assertEqual(calls, [False])
        self.assertEqual(result['report']['summary'], '초안')
        self.assertFalse(result['quality_review']['approved'])

    async def test_failed_final_audit_never_leaves_report_approved(self):
        result, calls = await self.run_report(audit_fails=True)
        self.assertEqual(calls, [False, True])
        self.assertFalse(result['quality_review']['approved'])
        self.assertFalse(result['quality_review']['final_audit_completed'])


if __name__ == '__main__':
    unittest.main()
