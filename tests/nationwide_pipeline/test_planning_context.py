"""기획서용 지역 비교 계산이 기간과 자기 지역 제외 규칙을 지키는지 검증한다."""

from __future__ import annotations

import unittest

import pandas as pd

from data_pipeline.tools.build_planning_context import add_percentiles, build_peer_rows, summarize_region


class PlanningContextTest(unittest.TestCase):
    def test_summary_uses_latest_12_and_previous_12_months(self) -> None:
        months = pd.date_range("2024-01-01", periods=30, freq="MS")
        frame = pd.DataFrame(
            {
                "region_code": "11680",
                "province_name": "서울특별시",
                "municipality_name": "강남구",
                "local_hierarchy_name": "강남구",
                "month": months,
                "visitors": [100.0] * 18 + [200.0] * 12,
                "domestic_tourism_spend_thousand_krw": [10.0] * 18 + [40.0] * 12,
                "nonlocal_tourism_spend_thousand_krw": [5.0] * 30,
                "overnight_ratio_pct": [10.0] * 30,
                "avg_stay_days": [2.0] * 30,
                "avg_stay_minutes": [300.0] * 30,
                "visitors_source_id": ["source-1"] * 30,
            }
        )
        summary = summarize_region(frame, months.max())
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["visitors_12m"], 2400)
        self.assertEqual(summary["visitors_yoy_pct"], 100.0)
        self.assertEqual(summary["spend_per_visitor_krw"], 200.0)

    def test_peer_list_never_contains_self(self) -> None:
        profile = add_percentiles(
            pd.DataFrame(
                [
                    {
                        "region_code": str(index),
                        "province_name": "도",
                        "local_hierarchy_name": f"지역{index}",
                        "period_end": "2026-06",
                        "visitors_12m": 1000 + index * 100,
                        "spend_per_visitor_krw": 100 + index,
                        "overnight_ratio_avg_pct": 10 + index,
                        "avg_stay_days": 2 + index / 10,
                    }
                    for index in range(6)
                ]
            )
        )
        peers = build_peer_rows(profile, peer_count=2)
        self.assertTrue(all(row["region_code"] != row["peer_region_code"] for row in peers))
        self.assertEqual(len(peers), 12)


if __name__ == "__main__":
    unittest.main()
