import unittest
from datetime import date
from pydantic import ValidationError
from ai_server.app.planning_brief import PlanningBrief
from ai_server.app.case_recommendation import allowed_operation, constrain_decision
from ai_server.app.openai_responses import OpenAIResponseError
from ai_server.app.idea_proposal import prepare_idea_report
from ai_server.test_proposal_presentation_v3_contract import _sample_report


class GuidedPlanningTest(unittest.TestCase):
    def test_default_dates_are_three_calendar_months(self):
        brief=PlanningBrief(region_code='51110',input_profile='guided_v1')
        self.assertEqual(brief.start_date,date.today().replace(day=1))
        self.assertEqual((brief.end_date.year-brief.start_date.year)*12+brief.end_date.month-brief.start_date.month,2)

    def test_hidden_parameters_and_conflicts_rejected(self):
        for changes in [dict(business_direction='night_time_experience',excluded_operations=['night_time_experience']),
                        dict(visitor_target_pct=10,spending_target_pct=10),dict(preferences='hidden'),
                        dict(resources_confirmed='x'*301),dict(field_context='x'*501),
                        dict(budget_status='indicative',budget_max_krw=100,budget_hard_limit=True)]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                PlanningBrief(region_code='51110',input_profile='guided_v1',**changes)

    def test_budget_total_allocated_without_changing_ml(self):
        report=_sample_report();before=report['ml_analysis']
        report['planning_brief']={'input_profile':'guided_v1','budget_max_krw':30000000}
        result=prepare_idea_report(report)
        self.assertEqual(result['reference_estimate']['total_krw'],30000000)
        self.assertEqual(sum(i['amount'] for i in result['reference_estimate']['items']),30000000)
        self.assertEqual(result['ml_analysis'],before)
        self.assertNotIn('quantity',result['reference_estimate'])

    def test_excluded_operation_cannot_reappear_as_selected_design(self):
        brief={'input_profile':'guided_v1','business_direction':'auto','excluded_operations':['night_time_experience']}
        self.assertFalse(allowed_operation({'intervention':'야간관광'},brief))
        self.assertFalse(allowed_operation({'mechanism':'환급 지원과 야간 공연'},brief))
        with self.assertRaises(OpenAIResponseError):
            constrain_decision({'design_candidates':[{'candidate_id':'a','mechanism':'야간 공연'}]},[],brief)

    def test_rejected_selection_does_not_mix_alternative_with_old_brief(self):
        brief={'input_profile':'guided_v1','excluded_operations':['night_time_experience']}
        source={'source_id':'case:stay','source_url':'https://example.go.kr/stay',
                'intervention':'숙박 체험','operating_model':'숙박 체험 운영'}
        decision={'selected_candidate_id':'night','strategy_brief':{'mechanism':'야간 공연'},
                  'design_candidates':[{'candidate_id':'night','mechanism':'야간 공연'},
                                       {'candidate_id':'stay','mechanism':'숙박 체험'}]}
        with self.assertRaises(OpenAIResponseError):
            constrain_decision(decision,[source],brief)
        self.assertEqual(decision['selected_candidate_id'],'night')
        decision['selected_candidate_id']='stay'
        decision['strategy_brief']={'mechanism':'숙박 체험'}
        result=constrain_decision(decision,[source],brief)
        self.assertEqual([c['candidate_id'] for c in result['design_candidates']],['stay'])
        self.assertEqual(result['recommended_case_ids'],['case:stay'])

    def test_single_allowed_family_does_not_require_unwanted_alternative(self):
        from ai_server.app.agents.planning_requirements import candidate_delivery_issues
        pack={'planning_brief':{'input_profile':'guided_v1','business_direction':'stay_conversion'},
              'benchmark_cases':[{'source_id':'case:stay','intervention':'숙박 체험'}]}
        decision={'selected_candidate_id':'stay','design_candidates':[{'candidate_id':'stay','candidate_type':'stay_conversion'}]}
        fields={row['field'] for row in candidate_delivery_issues(pack,decision)}
        self.assertNotIn('planning_decision.design_candidates',fields)
