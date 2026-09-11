import unittest
from copy import deepcopy

from ai_server.app.report_projection import target_series, visitor_linked_spending
from ai_server.app.proposal_presentation_v3 import _scenario_rows
from ai_server.test_proposal_presentation_v3_contract import _sample_report


class VisitorLinkedSpendingTest(unittest.TestCase):
    def test_monthly_rates_match_but_weighted_totals_differ(self):
        visitors, spending = [100, 200, 300], [1000, 4000, 12000]
        targets = target_series(visitors, 6)
        result = visitor_linked_spending(visitors, spending, targets)
        self.assertEqual(result['ratios'], [10, 20, 40])
        self.assertEqual(result['targets'], [1020, 4160, 12720])
        for v, s, tv, ts in zip(visitors, spending, targets, result['targets']):
            self.assertAlmostEqual(tv / v, ts / s)
        self.assertNotAlmostEqual(sum(targets) / sum(visitors), sum(result['targets']) / sum(spending))

    def test_zero_denominator_is_not_invented_and_bad_values_rejected(self):
        self.assertEqual(visitor_linked_spending([0], [50], [0]), {'ratios': [None], 'targets': [None]})
        for values in (([1], [], [1]), ([float('nan')], [1], [1]), ([True], [1], [1])):
            with self.assertRaises(ValueError):
                visitor_linked_spending(*values)

    def test_export_uses_linked_formula_without_overwriting_explicit_other_target(self):
        report = _sample_report()
        report['execution_scenario'] = {'visitor_target_pct': 5, 'spending_target_pct': 5}
        before = deepcopy(report)
        scenario = _scenario_rows(report)
        self.assertEqual(scenario['spending_calculation'], 'visitor_linked')
        self.assertEqual(report, before)
        for expected, actual in zip(target_series(scenario['baseline_spending'], 5), scenario['target_spending']):
            self.assertAlmostEqual(expected, actual, places=3)
        report['execution_scenario']['spending_target_pct'] = 8
        scenario = _scenario_rows(report)
        self.assertEqual(scenario['spending_calculation'], 'independent_target')
        self.assertEqual(scenario['target_spending'], target_series(scenario['baseline_spending'], 8))


if __name__ == '__main__':
    unittest.main()
