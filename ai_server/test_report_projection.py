"""LLM·MySQL 없이 기획 기간, Word/PPT 월 배열, 목표 산식의 일치를 확인합니다."""

from copy import deepcopy
from datetime import date
import unittest

from ai_server.app.report_projection import execution_target, select_report_forecast, target_series
from ai_server.app.proposal_document import _ml_forecast_rows, _execution_target
from ai_server.app.proposal_presentation_v3 import _scenario_rows
from ai_server.ml.horizon_policy import resolve_planning_horizon


def fixture(timeframe='2026-09 ~ 2027-02, 6개월'):
    return {
        'strategies': [{'timeframe': timeframe}],
        'ml_analysis': {
            'status': 'available', 'latest_observed_month': '202607',
            'horizon_policy': resolve_planning_horizon(None, '202607', as_of_date=date(2026, 9, 2)).model_payload(),
            'forecasts': [{'month': month, 'visitors': 100 + index, 'spending_krw': 1000 + index}
                          for index, month in enumerate(['202608', '202609', '202610', '202611', '202612', '202701', '202702'])],
        },
    }


class ReportProjectionTests(unittest.TestCase):
    def test_six_month_plan_excludes_gap_month_and_keeps_february(self):
        report = fixture()
        result = select_report_forecast(report)
        self.assertEqual([row['month'] for row in result['rows']], ['202609','202610','202611','202612','202701','202702'])
        self.assertTrue(result['complete'])
        self.assertEqual(_scenario_rows(report)['categories'], ['26.09','26.10','26.11','26.12','27.01','27.02'])
        self.assertEqual(_ml_forecast_rows(report)[-1]['month'], '2027.02')

    def test_month_count_selects_corresponding_candidate_not_first(self):
        self.assertEqual(len(select_report_forecast(fixture('6개월 시범 운영'))['rows']), 6)
        self.assertEqual(len(select_report_forecast(fixture('3개월 시범 운영'))['rows']), 3)

    def test_explicit_year_month_formats(self):
        for period in ('2026.11~2027.01', '2026년 11월~2027년 1월', '202611~202701'):
            with self.subTest(period=period):
                self.assertEqual(select_report_forecast(fixture(period))['period'], '202611~202701')

    def test_ambiguous_new_plan_does_not_guess(self):
        self.assertEqual(select_report_forecast(fixture('3~6개월 검토'))['rows'], [])
        self.assertEqual(select_report_forecast(fixture('미정'))['rows'], [])

    def test_requested_dates_used_when_no_final_duration(self):
        report = fixture('희망 기간')
        report['ml_analysis']['horizon_policy'] = resolve_planning_horizon(
            {'schedule_status':'flexible','start_date':'2026-11-01','end_date':'2027-01-31'},
            '202607', as_of_date=date(2026,9,2)).model_payload()
        self.assertEqual(select_report_forecast(report)['period'], '202611~202701')

    def test_partial_range_is_labelled_and_does_not_move_target_month(self):
        report = fixture('2026-09~2027-04')
        report['execution_scenario'] = {'visitor_target_pct': 10, 'spending_target_pct': 20}
        selection = select_report_forecast(report)
        self.assertFalse(selection['complete'])
        self.assertTrue(selection['notes'])
        self.assertFalse(_scenario_rows(report)['has_target'])
        self.assertIsNone(_execution_target(report))

    def test_out_of_range_missing_month_and_nonfinite_are_not_zero_filled(self):
        self.assertEqual(select_report_forecast(fixture('2028-01~2028-03'))['rows'], [])
        for corruption in ('missing','duplicate','nan','none'):
            report = fixture()
            rows = report['ml_analysis']['forecasts']
            if corruption == 'missing':
                rows.pop(3)
            elif corruption == 'duplicate':
                rows.append(deepcopy(rows[0]))
            else:
                rows[3]['visitors'] = float('nan') if corruption == 'nan' else None
            with self.subTest(corruption=corruption):
                self.assertEqual(select_report_forecast(report)['rows'], [])

    def test_target_needs_both_explicit_numbers_and_same_formula(self):
        report = fixture()
        for scenario in ({}, {'visitor_target_pct':5}, {'visitor_target_pct':True,'spending_target_pct':8}):
            report['execution_scenario'] = scenario
            self.assertIsNone(execution_target(report))
            self.assertFalse(_scenario_rows(report)['has_target'])
        report['execution_scenario'] = {'visitor_target_pct': 6, 'spending_target_pct': 12}
        ppt = _scenario_rows(report)
        self.assertEqual(_execution_target(report), (6,12))
        self.assertEqual(ppt['target_visitors'], target_series(ppt['baseline_visitors'], 6))
        self.assertEqual(target_series([100], 10), [110.00000000000001])

    def test_input_is_not_mutated(self):
        report = fixture()
        original = deepcopy(report)
        select_report_forecast(report)
        _scenario_rows(report)
        self.assertEqual(report, original)


if __name__ == '__main__':
    unittest.main()
