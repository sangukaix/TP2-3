import unittest
from pathlib import Path
from ai_server.ml.module_usage import GUIDES, build_module_usage
from ai_server.ml.gangnam_forecast import TARGETS


class ModuleUsageTest(unittest.TestCase):
    def test_every_actual_target_has_existing_code_paths(self):
        self.assertEqual(set(GUIDES), set(TARGETS))
        root = Path(__file__).resolve().parents[1]
        for key in TARGETS:
            guide = build_module_usage(key)
            self.assertEqual(len(guide['steps']), 7)
            for step in guide['steps']:
                self.assertTrue((root / step['file']).is_file(), step['file'])
            self.assertIn(f'forecasts[].{key}', guide['tree'])
            self.assertIn('자동 선택 규칙이 아닙니다', guide['limit'])

    def test_unknown_target_does_not_claim_existing_integration(self):
        self.assertEqual(build_module_usage('new_metric'), {})

    def test_ratio_aggregation_and_display_boundaries(self):
        self.assertEqual(build_module_usage('lodging_rate_pct')['aggregation'], '월별 값의 산술평균')
        self.assertIn('직접 그리지 않으며', build_module_usage('stay_minutes')['display'])
        self.assertIn('목표 KPI', build_module_usage('visitors')['display'])
