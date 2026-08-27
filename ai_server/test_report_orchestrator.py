"""외부 API 호출 없이 Multi-Agent 재검토 흐름을 검증합니다."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

from ai_server.app.agents.case_study_agent import _load_curated_case_cards
from ai_server.app.agents.report_orchestrator import (
    _CASE_STUDY_CACHE,
    _EVIDENCE_CACHE,
    orchestrate_strategy_report,
)
from ai_server.app.agents.transferability_agent import TransferabilityAgent
from ai_server.app.openai_responses import OpenAIResponseError
from ai_server.app.proposal_document import create_strategy_proposal_document


def _draft(title: str) -> dict:
    return {
        'summary': title,
        'observed_findings': [],
        'strategies': [],
        'limitations': [],
    }


class FakeEvidenceAgent:
    calls = 0

    def __init__(self, **_: object) -> None:
        pass

    async def collect(self, **_: object) -> dict:
        FakeEvidenceAgent.calls += 1
        return {
            'sources': [{'source_id': 'dataset:1'}],
            'research_gaps': [],
            'trace': [{'agent': 'evidence', 'stage': 'dataset', 'status': 'completed', 'items': 1}],
        }


class FakeCaseStudyAgent:
    calls = 0

    def __init__(self, **_: object) -> None:
        pass

    async def collect(self, **_: object) -> dict:
        FakeCaseStudyAgent.calls += 1
        return {
            'benchmark_cases': [{
                'source_id': 'case:1',
                'source_url': 'https://example.go.kr/case',
                'intervention': '숙박 연계 지역환급',
            }],
            'sources': [{'source_id': 'case:1', 'source_type': 'benchmark_case'}],
            'research_gaps': [],
            'trace': [{'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'completed', 'items': 1}],
        }


class FakeTransferabilityAgent:
    calls = 0

    def __init__(self, **_: object) -> None:
        pass

    async def assess(self, *, evidence_pack: dict) -> dict:
        FakeTransferabilityAgent.calls += 1
        assert evidence_pack['benchmark_cases'][0]['source_id'] == 'case:1'
        return {
            'diagnosis_summary': '숙박 전환 필요',
            'candidate_assessments': [],
            'recommended_case_ids': ['case:1'],
            'strategy_brief': {'working_title': '숙박 연계 지역환급'},
        }


class FakePlannerAgent:
    calls = 0
    last_evidence_pack: dict | None = None

    def __init__(self, **_: object) -> None:
        pass

    async def write(self, evidence_pack: dict, revision_feedback: dict | None = None) -> dict:
        FakePlannerAgent.last_evidence_pack = evidence_pack
        FakePlannerAgent.calls += 1
        return _draft('수정본' if revision_feedback else '초안')


class FakeReviewerAgent:
    calls = 0

    def __init__(self, **_: object) -> None:
        pass

    async def review(self, **_: object) -> dict:
        FakeReviewerAgent.calls += 1
        approved = FakeReviewerAgent.calls > 1
        return {
            'approved': approved,
            'overall_score': 90 if approved else 70,
            'dimension_scores': {},
            'strengths': ['근거 분리'],
            'issues': [] if approved else [{
                'severity': 'major',
                'field': 'solution',
                'problem': '실행 방법 부족',
                'revision_instruction': '작업과 산출물을 구체화',
            }],
            'summary': '통과' if approved else '수정 필요',
        }


class FailingRevisionPlanner(FakePlannerAgent):
    async def write(self, evidence_pack: dict, revision_feedback: dict | None = None) -> dict:
        del evidence_pack
        if revision_feedback:
            raise OpenAIResponseError('OPENAI_MODEL_OR_REQUEST_ERROR', '수정 요청 거절')
        return _draft('보존할 초안')


class ReportOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _EVIDENCE_CACHE.clear()
        _CASE_STUDY_CACHE.clear()
        FakeEvidenceAgent.calls = 0
        FakeCaseStudyAgent.calls = 0
        FakeTransferabilityAgent.calls = 0
        FakePlannerAgent.last_evidence_pack = None

    async def test_same_snapshot_reuses_only_evidence_collection(self) -> None:
        FakeReviewerAgent.calls = 1  # 두 호출 모두 첫 검수에서 바로 통과시킵니다.
        with (
            patch('ai_server.app.agents.report_orchestrator.EvidenceAgent', FakeEvidenceAgent),
            patch('ai_server.app.agents.report_orchestrator.CaseStudyAgent', FakeCaseStudyAgent),
            patch('ai_server.app.agents.report_orchestrator.TransferabilityAgent', FakeTransferabilityAgent),
            patch('ai_server.app.agents.report_orchestrator.PlannerAgent', FakePlannerAgent),
            patch('ai_server.app.agents.report_orchestrator.ReviewerAgent', FakeReviewerAgent),
        ):
            arguments = {
                'project_root': Path('.'),
                'env_values': {
                    'OPENAI_API_KEY': 'test',
                    'OPENAI_REPORT_MODEL': 'test-model',
                    'EVIDENCE_CACHE_TTL_SECONDS': '3600',
                },
                'region_code': '11680',
                'snapshot': {'region_name': '서울특별시 강남구'},
                'report_schema': {},
            }
            first = await orchestrate_strategy_report(**arguments)
            second = await orchestrate_strategy_report(**arguments)

        self.assertEqual(FakeEvidenceAgent.calls, 1)
        self.assertEqual(FakeCaseStudyAgent.calls, 1)
        self.assertTrue(any(item['agent'] == 'evidence' and item['stage'] == 'complete' for item in first['agent_trace']))
        self.assertTrue(any(item['agent'] == 'evidence' and item['stage'] == 'cache' for item in second['agent_trace']))
        self.assertTrue(any(item['agent'] == 'case_scout' and item['stage'] == 'cache' for item in second['agent_trace']))
        self.assertEqual(FakeTransferabilityAgent.calls, 2)
        self.assertEqual(FakePlannerAgent.last_evidence_pack['transfer_assessment']['recommended_case_ids'], ['case:1'])

    async def test_failed_review_triggers_one_revision_and_final_review(self) -> None:
        FakePlannerAgent.calls = 0
        FakeReviewerAgent.calls = 0
        with (
            patch('ai_server.app.agents.report_orchestrator.EvidenceAgent', FakeEvidenceAgent),
            patch('ai_server.app.agents.report_orchestrator.CaseStudyAgent', FakeCaseStudyAgent),
            patch('ai_server.app.agents.report_orchestrator.TransferabilityAgent', FakeTransferabilityAgent),
            patch('ai_server.app.agents.report_orchestrator.PlannerAgent', FakePlannerAgent),
            patch('ai_server.app.agents.report_orchestrator.ReviewerAgent', FakeReviewerAgent),
        ):
            result = await orchestrate_strategy_report(
                project_root=Path('.'),
                env_values={'OPENAI_API_KEY': 'test', 'OPENAI_REPORT_MODEL': 'test-model'},
                region_code='11680',
                snapshot={'region_name': '서울특별시 강남구'},
                report_schema={},
            )

        self.assertEqual(result['report']['summary'], '수정본')
        self.assertTrue(result['quality_review']['approved'])
        self.assertTrue(result['quality_review']['revised_once'])
        self.assertEqual(FakePlannerAgent.calls, 2)
        self.assertEqual(FakeReviewerAgent.calls, 2)

    async def test_revision_failure_preserves_reviewed_initial_draft(self) -> None:
        FakeReviewerAgent.calls = 0
        with (
            patch('ai_server.app.agents.report_orchestrator.EvidenceAgent', FakeEvidenceAgent),
            patch('ai_server.app.agents.report_orchestrator.CaseStudyAgent', FakeCaseStudyAgent),
            patch('ai_server.app.agents.report_orchestrator.TransferabilityAgent', FakeTransferabilityAgent),
            patch('ai_server.app.agents.report_orchestrator.PlannerAgent', FailingRevisionPlanner),
            patch('ai_server.app.agents.report_orchestrator.ReviewerAgent', FakeReviewerAgent),
        ):
            result = await orchestrate_strategy_report(
                project_root=Path('.'),
                env_values={'OPENAI_API_KEY': 'test', 'OPENAI_REPORT_MODEL': 'test-model'},
                region_code='11680',
                snapshot={'region_name': '서울특별시 강남구'},
                report_schema={},
            )

        self.assertEqual(result['report']['summary'], '보존할 초안')
        self.assertFalse(result['quality_review']['approved'])
        self.assertEqual(result['quality_review']['revision_error_code'], 'OPENAI_MODEL_OR_REQUEST_ERROR')
        self.assertEqual(result['agent_trace'][-1]['status'], 'failed')

    async def test_transferability_without_cases_returns_safe_fallback(self) -> None:
        result = await TransferabilityAgent(api_key='', model='test').assess(
            evidence_pack={'benchmark_cases': []},
        )

        self.assertEqual(result['recommended_case_ids'], [])
        self.assertIn('집행하지 않음', result['strategy_brief']['stop_or_scale_rule'])

    def test_curated_case_registry_uses_only_allowed_official_sources(self) -> None:
        cases = _load_curated_case_cards(
            Path(__file__).resolve().parents[1],
            ['go.kr', 'mcst.go.kr', 'evaluation.go.kr'],
        )

        self.assertGreaterEqual(len(cases), 4)
        self.assertTrue(all(case['source_url'].startswith('https://') for case in cases))
        self.assertTrue(all(case['evidence_strength'] in {'high', 'medium', 'low'} for case in cases))

    def test_word_proposal_lists_benchmark_case_separately(self) -> None:
        trend = [
            {'month': f'2026-{month:02d}', 'visitors': 1000 + month * 10, 'spending_krw': 10_000_000 + month * 100_000}
            for month in range(1, 7)
        ]
        steps = [
            {'step': index, 'schedule': f'{index}주차', 'task': f'{index}단계 실행', 'deliverable': f'{index}단계 결과물'}
            for index in range(1, 6)
        ]
        report = {
            'region_name': '서울특별시 강남구',
            'period': '2026-01~2026-06',
            'summary': '공식 사례의 운영 방식을 지역 조건에 맞게 축소 실험합니다.',
            'observed_findings': [{'metric': '월간 방문자', 'value': '1,060명', 'interpretation': '최신 관측값'}],
            'monthly_trend': trend,
            'strategies': [{
                'priority': 1,
                'title': '지역환급 시범사업',
                'timeframe': '3개월',
                'problem_to_solve': '방문이 지역소비로 이어지지 않습니다.',
                'comparison_analysis': '동일 기간 공식 원자료와 타 지역 사례를 비교했습니다.',
                'solution': '증빙 결제액의 일부를 지역상품권으로 환급합니다.',
                'implementation_steps': steps,
                'expected_effect': '시범운영 후 유지·수정·중단을 결정할 수 있습니다.',
                'budget': '참여 인원×인당 최대 환급액+운영비',
                'kpi': '참여자 결제액·환급사용률',
                'visual_asset_source_ids': [],
            }],
            'evidence_sources': [{
                'source_id': 'case:gangjin',
                'source_type': 'benchmark_case',
                'title': '강진 반값여행 지역경제 효과 소개',
                'summary': '강진군 · 반값여행 지역환급 · 공식 운영 결과',
                'source_url': 'https://example.go.kr/case',
                'evidence_strength': 'medium',
            }],
        }

        proposal = Document(create_strategy_proposal_document(report))
        table_text = '\n'.join(cell.text for table in proposal.tables for row in table.rows for cell in row.cells)

        self.assertIn('공식 사례', table_text)
        self.assertIn('강진 반값여행', table_text)


if __name__ == '__main__':
    unittest.main()
