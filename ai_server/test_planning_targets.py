import unittest
from pydantic import ValidationError
from ai_server.app.planning_brief import PlanningBrief, without_reference_text
from ai_server.app.report_projection import execution_target, target_series


class PlanningTargetsTest(unittest.TestCase):
    def test_explicit_targets_survive_saved_conditions_and_projection(self):
        brief = PlanningBrief(region_code='51130', visitor_target_pct=2, spending_target_pct=3)
        saved = without_reference_text(brief).model_dump(mode='json')
        self.assertEqual(execution_target({'planning_brief': saved}), (2, 3))
        self.assertEqual(target_series([100, 100, 100], 3), [101, 102, 103])

    def test_missing_targets_remain_missing(self):
        self.assertIsNone(execution_target({'planning_brief': PlanningBrief(region_code='51130').model_dump()}))

    def test_partial_or_out_of_range_targets_rejected(self):
        for values in ({'visitor_target_pct': 1}, {'visitor_target_pct': -1, 'spending_target_pct': 1},
                       {'visitor_target_pct': 21, 'spending_target_pct': 1}):
            with self.assertRaises(ValidationError):
                PlanningBrief(region_code='51130', **values)

    def test_existing_saved_scenario_takes_priority(self):
        self.assertEqual(execution_target({'execution_scenario': {'visitor_target_pct': 1, 'spending_target_pct': 2},
                                          'planning_brief': {'visitor_target_pct': 4, 'spending_target_pct': 5}}), (1, 2))
