"""다중 헤더 관광지 표와 중복 파일 처리를 검증한다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from data_pipeline.tools.build_supplemental_staging import (
    deduplicate_files,
    flatten_benchmark_metrics,
    transform_attraction_monthly,
)


class SupplementalStagingTest(unittest.TestCase):
    def test_deduplicate_prefers_named_section(self) -> None:
        files = [
            {"sha256": "same", "section": "(root)", "relative_path": "out.csv"},
            {"sha256": "same", "section": "지역별 관광지 관광객 현황표", "relative_path": "지역별 관광지 관광객 현황표/서울.csv"},
        ]
        selected = deduplicate_files(files)
        self.assertEqual(selected[0]["section"], "지역별 관광지 관광객 현황표")

    def test_two_row_header_unpivots_months(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "서울.csv"
            path.write_text(
                "시도,군구,관광지,내/외국인,총계,2024년,Unnamed\n"
                ",,,,,인원계,2024년 01월\n"
                "서울특별시,종로구,경복궁,내국인,100,100,10\n"
                "서울특별시,종로구,경복궁,합계,100,100,10\n",
                encoding="utf-8",
            )
            file_row = {"relative_path": "서울.csv", "sha256": "a" * 64}
            rows, rejected, audit = transform_attraction_monthly(root, file_row)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["year_month"], "2024-01")
            self.assertEqual(rows[0]["visitors"], "10")
            self.assertTrue(str(rows[0]["attraction_key"]).startswith("name:"))
            self.assertEqual(rejected, [])
            self.assertEqual(audit["loaded_monthly_values"], 1)
            self.assertEqual(audit["filtered_summary_rows"], 1)

    def test_benchmark_json_flattens_without_guessing_unknown_unit(self) -> None:
        rows = flatten_benchmark_metrics(
            [
                {
                    "dataset_name": "지역 방문자수_관광지출액 추세",
                    "snapshot_year": "2026",
                    "row_number": 2,
                    "dimensions_json": '{"기준연월":"202601"}',
                    "metrics_json": '{"방문자수":"100","관광지출액":"200"}',
                    "source_id": "source-1",
                }
            ]
        )
        self.assertEqual({row["year_month"] for row in rows}, {"2026-01"})
        units = {row["metric_name"]: row["unit"] for row in rows}
        self.assertEqual(units["방문자수"], "persons")
        self.assertEqual(units["관광지출액"], "source_defined_unknown")


if __name__ == "__main__":
    unittest.main()
