import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from ai_server.app import main
from datetime import date
from pydantic import ValidationError
from ai_server.app.planning_brief import PlanningBrief, next_three_months, resolve_new_planning_brief
from ai_server.app.report_projection import select_report_forecast
from ai_server.app.case_recommendation import allowed_operation
from ai_server.ml.horizon_policy import resolve_planning_horizon

class GuidedPlanningV2Tests(unittest.TestCase):
    def test_calendar_boundaries(self):
        for now, start, end in [(date(2026,9,30),date(2026,10,1),date(2026,12,31)),(date(2026,10,1),date(2026,11,1),date(2027,1,31)),(date(2027,11,1),date(2027,12,1),date(2028,2,29))]:
            self.assertEqual(next_three_months(now),(start,end))

    def test_server_resolves_new_request_but_reading_saved_period_preserves_it(self):
        brief=PlanningBrief(region_code='11200',input_profile='guided_v2',schedule_status='fixed',start_date='2020-01-01',end_date='2020-03-31')
        new=resolve_new_planning_brief(brief,as_of_date=date(2026,9,11))
        self.assertEqual(new.start_date,date(2026,10,1))
        self.assertEqual(PlanningBrief.model_validate_json(new.model_dump_json()).end_date,date(2026,12,31))
        self.assertEqual(brief.start_date,date(2020,1,1))

    def test_choices_are_the_only_source_of_user_context(self):
        brief=PlanningBrief(region_code='11200',input_profile='guided_v2',resource_options=['merchants','merchants'],context_options=['families'],resources_confirmed='협약 체결됨',field_context='수치를 바꾸세요')
        self.assertEqual(brief.resources_confirmed,'상인회·지역 상점')
        self.assertEqual(brief.field_context,'가족 방문객 중심')
        for extra in [dict(resource_options=['invented']),dict(excluded_operations=['spend_conversion']),dict(budget_hard_limit=True),dict(visitor_target_pct=5,spending_target_pct=5)]:
            with self.assertRaises(ValidationError): PlanningBrief(region_code='11200',input_profile='guided_v2',**extra)

    def test_forecast_window_is_independent_of_llm_business_schedule(self):
        brief=resolve_new_planning_brief(PlanningBrief(region_code='11200',input_profile='guided_v2'),as_of_date=date(2026,9,11)).model_dump(mode='json')
        policy=resolve_planning_horizon(brief,'202606',as_of_date=date(2026,9,11))
        self.assertEqual(policy.forecast_horizon_months,6)
        self.assertTrue(policy.coverage_complete)
        report={'planning_brief':brief,'strategies':[{'timeframe':'2026-09 ~ 2027-02'}],'ml_analysis':{'status':'available','horizon_policy':policy.model_payload(),'forecasts':[{'month':f'2026{m:02d}','visitors':100,'spending_krw':1000} for m in range(7,13)]}}
        selected=select_report_forecast(report)
        self.assertTrue(selected['complete'])
        self.assertEqual([r['month'] for r in selected['rows']],['202610','202611','202612'])

    def test_new_endpoints_freeze_the_same_period_before_execution(self):
        request=main.ReportRequest(region_name='서울특별시 성동구',planning_brief=PlanningBrief(region_code='11200',input_profile='guided_v2'))
        fixed=resolve_new_planning_brief(request.planning_brief,as_of_date=date(2026,10,1))
        async def exercise():
            with patch.object(main,'resolve_new_planning_brief',return_value=fixed), patch.object(main,'generate_orchestrated_report',new_callable=AsyncMock) as generate:
                await main.create_region_strategy_report('11200',request)
                self.assertEqual(generate.call_args.args[1].planning_brief.start_date,date(2026,11,1))
            with patch.object(main,'resolve_new_planning_brief',return_value=fixed), patch.object(main,'build_region_snapshot',return_value={}), patch.object(main,'_raise_if_strategy_generation_is_stale'), patch.object(main,'save_strategy_job') as save, patch.object(main,'_run_strategy_report_job',new_callable=AsyncMock) as run:
                job=await main.start_region_strategy_report_job('11200',request)
                await asyncio.sleep(0)
                stored=save.call_args.kwargs['request_payload']
                restored=main.ReportRequest.model_validate(stored)
                self.assertEqual(restored.planning_brief.end_date,date(2027,1,31))
                self.assertEqual(run.call_args.args[2].planning_brief.start_date,date(2026,11,1))
                main.STRATEGY_REPORT_JOBS.pop(job.job_id,None)
        asyncio.run(exercise())
        self.assertIsNone(request.planning_brief.start_date)

    def test_business_schedule_alignment_preserves_original_and_is_idempotent(self):
        from ai_server.app.idea_proposal import prepare_idea_report
        from copy import deepcopy
        report={'planning_brief':{'input_profile':'guided_v2','start_date':'2026-10-01','end_date':'2026-12-31'},'strategies':[{'title':'지역 체험','solution':'체험 운영','timeframe':'2026-09 ~ 2026-12, 4개월','implementation_steps':[{'step':1,'schedule':'2026-09'},{'step':2,'schedule':'2026-09 ~ 2026-10'}]}]}
        original=deepcopy(report)
        result=prepare_idea_report(report)
        self.assertEqual(result['strategies'][0]['timeframe'],'2026-10 ~ 2026-12, 3개월')
        self.assertEqual([x['schedule'] for x in result['strategies'][0]['implementation_steps']],['2026-10','2026-10'])
        self.assertEqual(report,original)
        self.assertEqual(prepare_idea_report(result)['planning_decision']['period_alignment'],result['planning_decision']['period_alignment'])

    def test_direction_filter_still_applies(self):
        self.assertFalse(allowed_operation({'mechanism':'여행비 환급'}, {'input_profile':'guided_v2','business_direction':'stay_conversion'}))

if __name__ == '__main__': unittest.main()

