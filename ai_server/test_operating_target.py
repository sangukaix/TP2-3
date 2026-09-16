import copy
import json
import unittest
from pathlib import Path

from ai_server.app.idea_proposal import prepare_idea_report
from ai_server.app.operating_target import build_operating_target
from ai_server.app.proposal_presentation_v3 import _scenario_rows


def report(visitors=100000, title='야간 문화 체험 프로그램'):
    return {'region_name': '테스트 지역', 'summary': '운영 제안',
            'strategies': [{'title': title, 'solution': title, 'timeframe': '2026-10 ~ 2026-12, 3개월'}],
            'ml_analysis': {'status': 'available', 'forecasts': [
                {'month': m, 'visitors': visitors*(i+1), 'spending_krw': visitors*(i+1)*30000}
                for i,m in enumerate(['202610','202611','202612'])]}, 'evidence_sources': []}


class OperatingTargetTest(unittest.TestCase):
    def test_sizes_programs_and_no_fixed_uplift(self):
        small=build_operating_target(report(10000));big=build_operating_target(report(3000000))
        refund=build_operating_target(report(10000,'반값여행 지역상품권 환급'))
        self.assertLess(small['sites'],big['sites'])
        self.assertNotEqual(small['capacity'],refund['capacity'])
        self.assertNotIn(small['central']['visitor_target_pct'],[5,20])

    def test_estimate_sum_and_monotonic_bounded_scenarios(self):
        for v in (1,1000,100000,3000000):
            plan=build_operating_target(report(v));e=plan['estimate']
            self.assertEqual(sum(i['amount'] for i in e['items']),e['total_krw'])
            self.assertEqual(sorted(s['additional_visitors'] for s in plan['scenarios']),
                             [s['additional_visitors'] for s in plan['scenarios']])
            for s in plan['scenarios']:
                self.assertLessEqual(s['additional_visitors'],s['participants'])
                self.assertLessEqual(s['participants'],plan['funded_capacity'])
                self.assertGreaterEqual(s['utilization_pct'],75)
                self.assertLessEqual(s['visitor_target_pct'],20)
                self.assertLessEqual(s['spending_target_pct'],30)

    def test_no_forecast_zero_and_partial(self):
        for v in (0,):self.assertFalse(build_operating_target(report(v))['scenarios'])
        data=report();data['ml_analysis']['forecasts'].pop()
        self.assertFalse(build_operating_target(data)['scenarios'])
        data=report();data['ml_analysis']['forecasts'][0]['visitors']=float('nan')
        self.assertFalse(build_operating_target(data)['scenarios'])

    def test_read_only_idempotent_and_exact_shared_totals(self):
        data=report();before=copy.deepcopy(data);prepared=prepare_idea_report(data)
        self.assertEqual(data,before)
        self.assertEqual(prepare_idea_report(prepared),prepared)
        plan=prepared['target_proposal_basis']['capacity_plan'];scenario=_scenario_rows(prepared)
        self.assertAlmostEqual(scenario['visitor_gap'],plan['central']['additional_visitors'],places=5)
        self.assertAlmostEqual(scenario['spending_gap'],plan['central']['additional_spending_krw'],places=3)

    def test_user_goal_preserved_and_old_default_migrated(self):
        data=report();data['execution_scenario']={'visitor_target_pct':5,'spending_target_pct':5}
        data['target_proposal_basis']={'kind':'planning_assumption','explanation':'초기 계획 목표'}
        self.assertNotEqual(prepare_idea_report(data)['execution_scenario']['visitor_target_pct'],5)
        data['execution_scenario']['target_origin']='user'
        prepared=prepare_idea_report(data)
        self.assertEqual(prepared['execution_scenario']['visitor_target_pct'],5)
        self.assertEqual(prepared['target_proposal_basis']['target_mode'],'user')

    def test_budget_caps_capacity(self):
        data=report(3000000);original=build_operating_target(data)
        data['planning_brief']={'budget_max_krw':100000000}
        limited=build_operating_target(data)
        self.assertLess(limited['funded_capacity'],original['funded_capacity'])
        self.assertLessEqual(limited['estimate']['total_krw'],100000000)

    def test_refund_uses_expected_payment_not_claim_ceiling(self):
        plan=build_operating_target(report(100000, '반값여행 지역상품권 환급'))
        e=plan['estimate']; c=plan['central']
        # 30,000 won planned purchase, 10% refund; 50,000 is only a ceiling.
        self.assertEqual(e['unit_krw'], 3000)
        self.assertEqual(e['per_claim_cap_krw'], 50000)
        self.assertEqual(e['qualifying_spend_krw'], c['participant_purchases_krw'])
        self.assertEqual(e['items'][0]['amount'], c['participants']*3000)
        self.assertEqual(e['total_krw'], c['expected_budget_krw'])
        self.assertGreater(e['full_participation_budget_krw'], e['total_krw'])
        self.assertLess(c['additional_spending_krw'], c['participant_purchases_krw'])
        for scenario in plan['scenarios']:
            self.assertEqual(scenario['participant_purchases_krw'], scenario['participants']*30000)
            self.assertEqual(scenario['expected_support_krw'], scenario['participants']*3000)

    def test_linked_refund_budget_limits_and_manual_override(self):
        from ai_server.app.idea_proposal import scale_estimate
        for cap in (0, 1000000, 20000000, 50000000, 100000000):
            data=report(3000000, '반값여행 지역상품권 환급')
            data['planning_brief']={'budget_max_krw': cap}
            plan=build_operating_target(data); e=plan['estimate']
            self.assertLessEqual(e['total_krw'], cap)
            self.assertLessEqual(e['full_participation_budget_krw'], cap)
            self.assertTrue(all(s['expected_budget_krw']<=cap for s in plan['scenarios']))
            prepared=prepare_idea_report(data)
            scale_estimate(prepared['reference_estimate'], 12345678)
            updated=prepare_idea_report(prepared)
            self.assertEqual(updated['reference_estimate']['total_krw'],12345678)
            self.assertNotIn('scenario_note', updated['reference_estimate'])
            self.assertNotIn('full_participation_budget_krw', updated['reference_estimate'])

    def test_explicit_local_refund_terms_are_used_without_copying_case_rates(self):
        data=report(100000,'지역상품권 환급')
        data['planning_decision']={'selected_candidate_id':'local', 'design_candidates':[
            {'candidate_id':'local','budget_formula':'min(인정 지출액 × 50%, 건별 상한 1만원)'}]}
        estimate=build_operating_target(data)['estimate']
        self.assertEqual(estimate['refund_rate_pct'],50)
        self.assertEqual(estimate['unit_krw'],10000)
        data['planning_decision']={}
        data['evidence_sources']=[{'operating_model':'환급률 50%, 건별 상한 1만원'}]
        self.assertEqual(build_operating_target(data)['estimate']['refund_rate_pct'],10)

    def test_case_rate_requires_scope_source_and_review(self):
        data=report();data['planning_decision']={'recommended_case_ids':['case:a']}
        statistic={'metric':'utilization_rate','value':80,'unit':'percent','period':'2025-10',
                   'scope':'program_participants','quote':'정원 1000명, 실제 참여 800명, 이용률 80%',
                   'capacity_count':1000,'participant_count':800,'program_name':'테스트 야간 프로그램'}
        source={'source_id':'case:a','source_url':'https://example.go.kr/case','case_region':'테스트 시',
                'operating_statistics':[statistic]}
        data['evidence_sources']=[source]
        self.assertEqual(build_operating_target(data)['central']['utilization_pct'],75)
        statistic['review_status']='reviewed'
        self.assertEqual(build_operating_target(data)['central']['utilization_pct'],80)
        statistic['scope']='citywide_yoy'
        self.assertEqual(build_operating_target(data)['central']['utilization_pct'],75)

    def test_floor_preserves_actual_case_and_rejects_missing_or_inconsistent_counts(self):
        data=report();data['planning_decision']={'recommended_case_ids':['case:test']}
        item={'metric':'utilization_rate','review_status':'reviewed','value':60,'unit':'percent',
              'period':'2025-10','scope':'program_participants','quote':'정원 1000명 중 600명 참여',
              'capacity_count':1000,'participant_count':600,'program_name':'테스트 문화 체험'}
        data['evidence_sources']=[{'source_id':'case:test','source_url':'https://example.go.kr/test',
                                  'case_region':'테스트 군','operating_statistics':[item]}]
        result=build_operating_target(data)
        self.assertEqual(result['central']['utilization_pct'],75)
        self.assertEqual(result['rate_basis'][0]['observed_value'],60)
        self.assertIn('600 ÷ 1,000',result['participation_basis'])
        self.assertIn('최소 기준 75%',result['participation_basis'])
        item['participant_count']=900 # Stated 60% now disagrees with the counts.
        self.assertEqual(build_operating_target(data)['rate_basis'][0]['kind'],'planning_policy')
        item['value']=90
        self.assertEqual(build_operating_target(data)['central']['utilization_pct'],90)
        item['capacity_count']=None
        self.assertEqual(build_operating_target(data)['central']['utilization_pct'],75)

    def test_real_jeju_legacy_report_round_trip(self):
        path=Path(__file__).resolve().parents[1]/'output/final_validation_20260915/jeju_report.json'
        if not path.exists():self.skipTest('Local saved report unavailable')
        raw=json.loads(path.read_text(encoding='utf-8-sig'))
        actual=prepare_idea_report(raw)
        self.assertEqual(actual['ml_analysis'],raw['ml_analysis'])
        self.assertEqual(actual['quality_review'],raw['quality_review'])
        self.assertEqual(prepare_idea_report(actual),actual)
        self.assertNotEqual(actual['execution_scenario']['visitor_target_pct'],5)


if __name__=='__main__':unittest.main()
