"""지역명 계층 표기를 포함한 관광데이터랩 원본 필터를 검증한다."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from ai_server.ml.regional_datalab_data import StandardDatalabRegion, _put_filtered_rows


class RegionalDatalabDataTests(unittest.TestCase):
    def test_city_district_uses_full_source_region_name(self) -> None:
        """수원시 장안구 원본을 장안구라는 짧은 이름 때문에 놓치지 않는다."""
        spec = StandardDatalabRegion(
            region_code="41111",
            region_name="경기도 수원시 장안구",
            short_name="장안구",
            raw_directory=Path("unused"),
        )
        frame = pd.DataFrame(
            {
                "기준연월": ["202401", "202401"],
                "지역명": ["수원시 장안구", "전국 기초지자체별 평균"],
                "숙박방문자 비율": [3.25, 9.99],
            }
        )
        values: dict[str, float] = {}
        _put_filtered_rows(
            values,
            frame,
            "숙박방문자 비율",
            lambda row: str(row.get("지역명") or "").strip() == spec.source_region_name,
        )

        self.assertEqual(spec.source_region_name, "수원시 장안구")
        self.assertEqual(values, {"202401": 3.25})


if __name__ == "__main__":
    unittest.main()
