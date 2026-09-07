from __future__ import annotations

import unittest

import pandas as pd

from data_pipeline.tools.assess_region_ml_readiness import assess_readiness


class RegionMlReadinessTests(unittest.TestCase):
    """지역별 모델 등록 전에 시간축과 target 누락을 차단하는지 확인합니다."""

    def test_marks_only_continuous_complete_region_as_eligible(self) -> None:
        months = pd.period_range("2024-01", periods=24, freq="M").astype(str)
        complete = pd.DataFrame({
            "region_code": ["11110"] * 24,
            "year_month": months,
            "visitors": range(24),
            "domestic_tourism_spend_thousand_krw": range(24),
            "overnight_ratio_pct": range(24),
            "avg_stay_days": range(24),
        })
        gap = complete.iloc[:-1].copy()
        gap["region_code"] = "11140"
        result = assess_readiness(pd.concat([complete, gap], ignore_index=True))
        status = dict(zip(result["region_code"], result["readiness"]))
        self.assertEqual(status["11110"], "eligible_for_time_split_evaluation")
        self.assertEqual(status["11140"], "not_ready")

