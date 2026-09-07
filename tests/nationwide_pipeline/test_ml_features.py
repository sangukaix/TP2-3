"""ML feature가 미래값을 사용하지 않고 과거 시점만 참조하는지 확인한다."""

from __future__ import annotations

import unittest

import pandas as pd

from data_pipeline.nationwide_ml.train_visitors_panel import build_features, calculate_metrics, select_operational_model


class MlFeatureTest(unittest.TestCase):
    # target 월의 lag1·lag12가 정확히 이전 월과 전년 동월을 가리켜야 한다.
    def test_lag_features_use_only_past_values(self) -> None:
        months = pd.date_range("2024-01-01", periods=17, freq="MS")
        frame = pd.DataFrame(
            {
                "region_code": ["11680"] * len(months),
                "year_month": months.strftime("%Y-%m"),
                "visitors": list(range(100, 100 + len(months))),
                "domestic_tourism_spend_thousand_krw": [1000] * len(months),
                "nonlocal_tourism_spend_thousand_krw": [800] * len(months),
                "overnight_ratio_pct": [10] * len(months),
                "avg_stay_days": [2] * len(months),
                "avg_stay_minutes": [300] * len(months),
            }
        )
        features = build_features(frame)
        target = features.iloc[0]
        self.assertEqual(target["year_month"].strftime("%Y-%m"), "2025-02")
        self.assertEqual(target["visitors_lag1"], 112)
        self.assertEqual(target["visitors_lag12"], 101)
        self.assertEqual(target["visitors_lag13"], 100)

    # MAE·RMSE·MAPE가 같은 표본에서 계산되는지 작은 예제로 검증한다.
    def test_metrics(self) -> None:
        metrics = calculate_metrics([100, 200], [90, 220])
        self.assertEqual(metrics["mae"], 15.0)
        self.assertAlmostEqual(float(metrics["mape_pct"]), 10.0)

    def test_failed_holdout_uses_predeclared_baseline(self) -> None:
        evaluations = {
            "seasonal_naive": {
                "validation": {"mae": 100.0},
                "test": {"mae": 80.0},
            },
            "random_forest": {
                "validation": {"mae": 70.0},
                "test": {"mae": 90.0},
            },
        }
        candidate, operational, status, validation_win, test_win = select_operational_model(
            evaluations
        )
        self.assertEqual(candidate, "random_forest")
        self.assertEqual(operational, "seasonal_naive")
        self.assertEqual(status, "baseline_only")
        self.assertTrue(validation_win)
        self.assertFalse(test_win)


if __name__ == "__main__":
    unittest.main()
