"""지역별 ML 기준선 평가는 시간순으로만 나뉘는지 검증한다."""

from __future__ import annotations

import unittest

import pandas as pd

from data_pipeline.nationwide_ml.evaluate_region_baselines import evaluate_region_baselines


class RegionBaselineEvaluationTest(unittest.TestCase):
    """타깃별 seasonal-naive 결과가 지원 지역에만 생기는지 확인합니다."""

    def test_returns_validation_and_test_for_eligible_region(self) -> None:
        months = pd.period_range("2024-01", "2026-06", freq="M").strftime("%Y-%m")
        frame = pd.DataFrame({
            "region_code": ["11110"] * len(months),
            "year_month": months,
            "visitors": list(range(100, 100 + len(months))),
            "domestic_tourism_spend_thousand_krw": list(range(200, 200 + len(months))),
            "overnight_ratio_pct": [10.0] * len(months),
            "avg_stay_days": [1.5] * len(months),
        })
        readiness = pd.DataFrame({"region_code": ["11110"], "readiness": ["eligible_for_time_split_evaluation"]})

        result = evaluate_region_baselines(frame, readiness)

        self.assertEqual(set(result["target"]), {
            "visitors", "domestic_tourism_spend_thousand_krw", "overnight_ratio_pct", "avg_stay_days",
        })
        self.assertEqual(set(result["split"]), {"validation", "test"})
        self.assertTrue((result["decision_status"] == "baseline_only").all())

