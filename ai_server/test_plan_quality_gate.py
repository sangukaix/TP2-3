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
        result = build_plan_quality_precheck(self._evidence_pack(), self._valid_report())
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


if __name__ == '__main__':
    unittest.main()
