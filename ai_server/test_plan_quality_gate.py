"""OpenAI 키 없이 기획안의 결정적 품질 규칙을 확인합니다."""

from __future__ import annotations

import unittest

from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck, merge_quality_precheck


class PlanQualityGateTest(unittest.TestCase):
    """근거·집행·예산·KPI 누락이 승인 상태를 통과하지 못하는지 확인합니다."""

    def _evidence_pack(self) -> dict:
        return {
            'sources': [{'source_id': 'case:official'}, {'source_id': 'dataset:28245'}],
            'snapshot': {'ml_analysis': {'source_id': 'ml:28245:test:202606'}},
        }

    def _valid_report(self) -> dict:
        return {
            'strategies': [{
                'solution': '외지인 참여자는 QR 인증 뒤 참여 업소에서 사용할 지역쿠폰을 받습니다.',
                'budget': '홍보물 수량 × 비교견적 단가와 쿠폰 지급 수량 × 공식 단가로 산정합니다.',
                'kpi': '2026년 6월 기준월 원자료와 운영 후 월별 결제·방문 수치를 비교합니다.',
                'evidence': 'dataset:28245, case:official, ml:28245:test:202606 (2026년 7~9월)',
                'implementation_steps': [
                    {'schedule': '1주', 'task': '참여 기준을 확정', 'deliverable': '참여 기준표'},
                    {'schedule': '2주', 'task': '업소를 모집', 'deliverable': '참여 업소 명단'},
                    {'schedule': '3주', 'task': '쿠폰을 준비', 'deliverable': 'QR 쿠폰'},
                    {'schedule': '4~8주', 'task': '시범 운영', 'deliverable': '운영 기록'},
                    {'schedule': '9주', 'task': '성과를 비교', 'deliverable': '성과표'},
                ],
            }],
        }

    def test_complete_report_has_no_deterministic_issue(self) -> None:
        report = self._valid_report()
        for number, step in enumerate(report['strategies'][0]['implementation_steps'], 1):
            step['step'] = number
        result = build_plan_quality_precheck(self._evidence_pack(), report)
        self.assertTrue(result['checked'])
        self.assertEqual(result['issues'], [])

    def test_missing_evidence_and_steps_blocks_approval(self) -> None:
        report = self._valid_report()
        strategy = report['strategies'][0]
        strategy['evidence'] = ''
        strategy['implementation_steps'] = strategy['implementation_steps'][:2]
        precheck = build_plan_quality_precheck(self._evidence_pack(), report)
        review = merge_quality_precheck({
            'approved': True, 'overall_score': 92, 'issues': [], 'summary': '통과',
        }, precheck)
        self.assertFalse(review['approved'])
        self.assertLessEqual(review['overall_score'], 81)
        self.assertTrue(any(issue['severity'] == 'critical' for issue in review['issues']))

    def test_score_below_82_cannot_be_approved_even_without_precheck_issue(self) -> None:
        """Reviewer가 approved=true를 잘못 반환해도 점수 기준은 Python 코드가 강제합니다."""
        review = merge_quality_precheck({
            'approved': True, 'overall_score': 81, 'issues': [], 'summary': '모델은 통과라고 응답',
        }, {'checked': True, 'issues': []})

        self.assertFalse(review['approved'])
        self.assertTrue(any(issue['field'] == 'quality_review.overall_score' for issue in review['issues']))

    def test_critical_reviewer_issue_cannot_be_approved(self) -> None:
        """점수가 높아도 출처 조작 같은 critical 이슈가 있으면 승인을 차단합니다."""
        review = merge_quality_precheck({
            'approved': True,
            'overall_score': 95,
            'issues': [{
                'severity': 'critical', 'field': 'evidence', 'problem': '근거 없는 수치',
                'revision_instruction': '공식 근거가 없는 수치를 삭제하세요.',
            }],
            'summary': '점수만 높은 응답',
        }, {'checked': True, 'issues': []})

        self.assertFalse(review['approved'])

    def test_same_candidate_type_is_flagged_before_planner_can_copy_one_idea(self) -> None:
        """이름만 다른 숙박/야간 패스 후보가 선정 근거처럼 통과하지 않게 합니다."""
        evidence_pack = self._evidence_pack()
        evidence_pack['benchmark_cases'] = [{'source_id': 'case:official'}]
        evidence_pack['transfer_assessment'] = {
            'selection_status': 'ready',
            'selected_candidate_id': 'C1',
            'selection_reason': '비교',
            'recommended_case_ids': ['case:official'],
            'candidate_assessments': [],
            'strategy_brief': {'supporting_case_ids': ['case:official']},
            'design_candidates': [
                {'candidate_id': 'C1', 'candidate_type': 'stay_conversion', 'evidence_source_ids': ['dataset:28245'],
                 'case_source_ids': ['case:official']},
                {'candidate_id': 'C2', 'candidate_type': 'stay_conversion', 'evidence_source_ids': ['dataset:28245'],
                 'case_source_ids': ['case:official']},
            ],
        }
        report = self._valid_report()
        for number, step in enumerate(report['strategies'][0]['implementation_steps'], 1):
            step['step'] = number
        result = build_plan_quality_precheck(evidence_pack, report)
        self.assertTrue(any(issue['field'] == 'planning_decision.candidate_type' for issue in result['issues']))

    def test_budget_only_title_and_out_of_range_steps_are_blocked(self) -> None:
        report = self._valid_report()
        strategy = report['strategies'][0]
        strategy.update({
            'title': '야간관광 특화도시 예산 편성',
            'timeframe': '2026-09 ~ 2026-11, 3개월',
            'budget': '총 1,000,000,000원 (사무관리·행사운영 등)',
        })
        strategy['implementation_steps'][3]['schedule'] = '2026-12'
        for number, step in enumerate(strategy['implementation_steps'], 1):
            step['step'] = number
        evidence_pack = self._evidence_pack()
        evidence_pack['quality_contract_version'] = 'execution-evidence-v1'
        result = build_plan_quality_precheck(evidence_pack, report, limit=None)
        fields = {issue['field'] for issue in result['issues']}
        self.assertIn('strategies[1].title', fields)
        self.assertIn('strategies[1].budget.fixed_total', fields)
        self.assertIn('strategies[1].implementation_steps[4].schedule', fields)

    def test_weak_ml_percentage_cannot_be_used_as_effect_claim_without_caution(self) -> None:
        report = self._valid_report()
        strategy = report['strategies'][0]
        strategy['expected_effect'] = 'ML 자연추세에 따라 2026년 11월 소비액이 41.26% 증가 전망이므로 사업 효과를 기대한다.'
        for number, step in enumerate(strategy['implementation_steps'], 1):
            step['step'] = number
        evidence_pack = self._evidence_pack()
        evidence_pack['quality_contract_version'] = 'execution-evidence-v1'
        evidence_pack['snapshot']['ml_analysis']['evaluation'] = {
            'metrics': {'spending_krw': {'model_reliability': 'below_baseline_on_test'}},
        }
        result = build_plan_quality_precheck(evidence_pack, report, limit=None)
        self.assertTrue(any(issue['field'].endswith('expected_effect.ml_reliability') for issue in result['issues']))


if __name__ == '__main__':
    unittest.main()
