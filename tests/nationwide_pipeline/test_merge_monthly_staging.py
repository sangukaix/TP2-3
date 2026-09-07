"""snapshot 병합이 동값 중복과 관측값 충돌을 구분하는지 검증한다."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.tools.merge_monthly_staging import OBSERVATION_COLUMNS, merge_staging


SOURCE_COLUMNS = [
    f"{column}_source_id"
    for column in OBSERVATION_COLUMNS
    if column
    not in {"province_name", "municipality_name", "local_hierarchy_name", "missing_metrics", "data_status"}
]
FIELDS = ["region_code", "year_month", *OBSERVATION_COLUMNS, *SOURCE_COLUMNS]


def row(code: str, month: str, visitors: str, source: str) -> dict[str, str]:
    values = {field: "" for field in FIELDS}
    values.update(
        {
            "region_code": code,
            "year_month": month,
            "province_name": "서울특별시",
            "municipality_name": "강남구",
            "local_hierarchy_name": "강남구",
            "visitors": visitors,
            "visitors_previous_year": "90",
            "visitors_yoy_pct": "11.1",
            "domestic_tourism_spend_thousand_krw": "1000",
            "nonlocal_tourism_spend_thousand_krw": "900",
            "unique_visitors": "80",
            "overnight_ratio_pct": "3",
            "avg_stay_days": "2",
            "avg_stay_minutes": "300",
            "missing_metrics": "",
            "data_status": "complete",
        }
    )
    for field in SOURCE_COLUMNS:
        values[field] = source
    return values


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class MergeMonthlyStagingTest(unittest.TestCase):
    def test_same_values_are_aliases_and_conflicts_are_not_silently_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary, secondary = root / "primary.csv", root / "secondary.csv"
            write_rows(primary, [row("11680", "2026-01", "100", "primary")])
            write_rows(
                secondary,
                [
                    row("11680", "2026-01", "100", "secondary"),
                    row("11740", "2026-01", "200", "secondary"),
                    row("11680", "2026-02", "300", "secondary"),
                ],
            )
            summary = merge_staging(primary, secondary, root / "output")
            self.assertEqual(summary["merged_row_count"], 3)
            self.assertEqual(summary["same_value_duplicate_count"], 1)
            self.assertEqual(summary["conflict_count"], 0)

            # 동일 key라도 실제 관측값이 다르면 primary를 보존하고 conflict audit을 남긴다.
            write_rows(secondary, [row("11680", "2026-01", "999", "secondary")])
            summary = merge_staging(primary, secondary, root / "output2")
            self.assertEqual(summary["conflict_count"], 1)
            with (root / "output2" / "snapshot_conflicts.csv").open(
                encoding="utf-8-sig", newline=""
            ) as source:
                conflict = next(csv.DictReader(source))
            self.assertIn("visitors", json.loads(conflict["conflicting_columns_json"]))


if __name__ == "__main__":
    unittest.main()
