"""MySQL 적재 묶음이 source·region 참조 무결성을 확인하는지 검증한다."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from data_pipeline.tools.build_mysql_load_bundle import build_load_bundle


class MysqlLoadBundleTest(unittest.TestCase):
    def test_bundle_requires_known_region_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            staging = root / "staging.csv"
            fields = [
                "region_code", "year_month", "province_name", "municipality_name",
                "local_hierarchy_name", "visitors", "visitors_previous_year", "visitors_yoy_pct",
                "domestic_tourism_spend_thousand_krw", "nonlocal_tourism_spend_thousand_krw",
                "unique_visitors", "overnight_ratio_pct", "avg_stay_days", "avg_stay_minutes",
                "data_status",
            ] + [
                f"{metric}_source_id"
                for metric in (
                    "visitors", "visitors_previous_year", "visitors_yoy_pct",
                    "domestic_tourism_spend_thousand_krw", "nonlocal_tourism_spend_thousand_krw",
                    "unique_visitors", "overnight_ratio_pct", "avg_stay_days", "avg_stay_minutes",
                )
            ]
            row = {field: "" for field in fields}
            row.update({"region_code": "11680", "year_month": "2026-01", "data_status": "complete"})
            for field in fields:
                if field.endswith("_source_id"):
                    row[field] = "source-1"
            with staging.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader()
                writer.writerow(row)

            mapping = root / "mapping.csv"
            mapping.write_text(
                "region_folder,province_name,municipality_name,local_hierarchy_name,official_region_code,mapping_status\n"
                "서울특별시_강남구,서울특별시,강남구,강남구,11680,validated_from_datalab\n",
                encoding="utf-8-sig",
            )
            sources = root / "sources.csv"
            sources.write_text(
                "source_id,source_name,source_page_url,downloaded_at,file_name,file_hash,date_range,geographic_level,filters,methodology_notes\n"
                "source-1,Data Lab,,2026-09-01,a.zip,abc,2026-01,시군구,,\n",
                encoding="utf-8-sig",
            )
            summary = build_load_bundle(staging, [mapping], [sources], root / "output")
            self.assertEqual(summary["fact_tourism_monthly_count"], 1)
            self.assertEqual(summary["data_source_count"], 1)


if __name__ == "__main__":
    unittest.main()
