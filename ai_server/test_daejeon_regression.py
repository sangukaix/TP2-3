"""Dated launch, festival handoff and growth definition regression cases."""
import copy
import unittest

from ai_server.test_operating_target import report
from ai_server.app.idea_proposal import prepare_idea_report
from ai_server.app.proposal_presentation_v3 import _scenario_rows
from ai_server.app.agents.planning_requirements import candidate_delivery_issues, uses_region_wide_refund_budget
from ai_server.app.measurement_alignment import align_night_growth
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.llm.local_agent import _prefetch_required_evidence
from ai_server.app.llm.local_prompts import local_instructions
from ai_server.app.agents.prompts import FESTIVAL_CASE_RULES


class DaejeonRegression(unittest.TestCase):
    def test_launch_month_controls_capacity_budget_and_export(self):
        data = report(3000000)
        data['strategies'][0]['implementation_steps'] = [
            {'task':'관광팀이 운영 계획을 수립', 'schedule':'2026-10'},
            {'task':'홍보팀이 축제 실행에 맞춰 홍보물을 배포하고 시범 운영', 'schedule':'2026-11'},
            {'task':'운영팀이 성과를 집계', 'schedule':'2026-12'}]
        original = copy.deepcopy(data)
        result = prepare_idea_report(data)
        plan = result['target_proposal_basis']['capacity_plan']
        scenario = _scenario_rows(result)
        self.assertEqual(plan['months'], 2)
        self.assertEqual(plan['monthly_weights'], [0, .5, 1])
        self.assertEqual(plan['capacity'], plan['sites'] * 8 * 2 * 2 * 40)
        self.assertEqual(scenario['target_visitors'][0], scenario['baseline_visitors'][0])
        self.assertEqual(scenario['target_spending'][0], scenario['baseline_spending'][0])
        self.assertAlmostEqual(scenario['visitor_gap'], plan['central']['additional_visitors'], places=5)
        self.assertAlmostEqual(scenario['spending_gap'], plan['central']['additional_spending_krw'], places=3)
        self.assertEqual(sum(i['amount'] for i in plan['estimate']['items']), plan['estimate']['total_krw'])
        self.assertEqual(original, data)
        self.assertEqual(result, prepare_idea_report(result))

    def test_unstated_schedule_and_user_targets_retained(self):
        data = report()
        self.assertEqual(prepare_idea_report(data)['target_proposal_basis']['capacity_plan']['months'], 3)
        data['execution_scenario'] = {'visitor_target_pct': 5, 'spending_target_pct': 6, 'target_origin':'user'}
        data['strategies'][0]['implementation_steps'] = [{'task':'시범 운영', 'schedule':'2026-11'}]
        n = prepare_idea_report(data)
        self.assertGreater(_scenario_rows(n)['target_visitors'][0], _scenario_rows(n)['baseline_visitors'][0])
        self.assertEqual(n['execution_scenario'], data['execution_scenario'])

    def test_share_growth_mixup_repaired_without_touching_share(self):
        text = '야간 방문자 수 증가율 (분자: 야간 시간대 방문자 수, 분모: 전체 방문자 수, 산식: 전년 같은 기간 야간 방문자 수 대비, 원자료: 한국관광 데이터랩)'
        result = align_night_growth(text)
        self.assertIn('분모: 전년 같은 기간 야간 방문자 수', result)
        self.assertIn('확보할 자료', result)
        self.assertEqual(result, align_night_growth(result))
        share = '야간 방문 비중: 분자: 야간 방문자 수, 분모: 전체 방문자 수'
        self.assertEqual(align_night_growth(share), share)

    def test_festival_is_read_and_assessed_but_not_forced_to_win(self):
        festival = {'source_id':'case:f', 'case_region':'경상북도 문경시', 'intervention':'공예 축제',
                    'operating_model':'문화 체험 축제', 'festival_statistics':{'annual':[]},
                    'evidence_kind':'festival_statistics', 'retrieval_basis':{'kind':'external_benchmark'}}
        old = {'source_id':'case:n', 'intervention':'야간 문화 개방', 'operating_model':'야간 체험 운영'}
        pack = {'benchmark_cases':[old, festival], 'sources':[], 'planning_brief':{'input_profile':'guided_v2','business_direction':'auto'}}
        workspace = EvidenceTools(pack, task='transferability')
        _prefetch_required_evidence(workspace, 'transferability')
        self.assertIn('case:f', workspace.read_source_ids)
        decision = {'selection_status':'ready','recommended_case_ids':['case:n'], 'design_candidates':[], 'candidate_assessments':[]}
        check = lambda: [i for i in candidate_delivery_issues(pack,decision) if i['field'].endswith('festival_comparison')]
        self.assertTrue(check())
        decision['candidate_assessments'] = [{'case_source_id':'case:f', 'similarity_reason':'공예 자원 비교',
                                           'adaptation':'체험 운영 제안', 'rejection_risks':['야간 이용 조건 미확인']}]
        self.assertFalse(check())
        self.assertEqual(decision['recommended_case_ids'], ['case:n'])
        decision['candidate_assessments'] = []
        pack['planning_brief']['business_direction'] = 'night_time_experience'
        self.assertFalse(check())

    def test_local_instructions_and_invalid_regional_budget(self):
        for task in ('transferability', 'planner', 'planner_revision', 'reviewer'):
            self.assertIn(FESTIVAL_CASE_RULES, local_instructions(task))
        self.assertTrue(uses_region_wide_refund_budget('지역환급 비율(예: 10%) × 관광소비액(76,758,413,000원)'))
        self.assertFalse(uses_region_wide_refund_budget('적격 신청별 인정 지출액 × 환급률'))


if __name__ == '__main__':
    unittest.main()
