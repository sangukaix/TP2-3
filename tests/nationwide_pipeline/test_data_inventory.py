"""전국 데이터 인벤토리의 핵심 파싱과 원본 비변경 동작을 확인한다."""

from __future__ import annotations

import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from data_pipeline.tools.data_inventory import (
    build_inventory,
    local_hierarchy_name,
    normalize_month,
    parse_archive_period,
    region_name_matches,
    split_region_folder,
)


class DataInventoryTest(unittest.TestCase):
    # 관광데이터랩 ZIP 이름의 시작·종료 월을 정확히 해석해야 한다.
    def test_parse_archive_period(self) -> None:
        self.assertEqual(parse_archive_period("2025_01_12"), ("2025-01", "2025-12"))
        self.assertEqual(parse_archive_period("invalid"), ("", ""))

    # 숫자형 CSV에서 흔한 .0 표기도 YYYY-MM로 정규화한다.
    def test_normalize_month(self) -> None:
        self.assertEqual(normalize_month("202501"), "2025-01")
        self.assertEqual(normalize_month("2025-02"), "2025-02")
        self.assertEqual(normalize_month("202503.0"), "2025-03")

    # 복합 행정구역과 이름 일부가 겹치는 지역을 잘못 매칭하지 않아야 한다.
    def test_region_name_matching(self) -> None:
        self.assertEqual(split_region_folder("경기도_고양시_덕양구"), ("경기도", "덕양구"))
        self.assertEqual(local_hierarchy_name("경기도_고양시_덕양구"), "고양시_덕양구")
        self.assertTrue(region_name_matches("경기도 고양시 덕양구", "경기도", "덕양구", "고양시_덕양구"))
        self.assertTrue(region_name_matches("양주시", "경기도", "양주시", "양주시"))
        self.assertFalse(region_name_matches("남양주시", "경기도", "양주시", "양주시"))

    # 임시 원본 ZIP을 검사해 산출물과 지역코드 후보가 생성되는지 확인한다.
    def test_build_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "raw"
            category = root / "서울특별시_강남구" / "숙박_체류시간"
            category.mkdir(parents=True)
            archive_path = category / "2025_01_12.zip"
            csv_text = "기준연월,지역코드,지역명,숙박자 비율\n202501,11680,강남구,8.5\n"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("순 방문자 수 및 숙박 비율.csv", csv_text.encode("utf-8-sig"))

            original_hash = archive_path.read_bytes()
            output_dir = Path(temp_dir) / "output"
            summary = build_inventory(root, output_dir)

            self.assertEqual(summary["region_count"], 1)
            self.assertEqual(summary["archive_count"], 1)
            self.assertEqual(archive_path.read_bytes(), original_hash)
            with (output_dir / "region_code_candidates.csv").open(encoding="utf-8-sig", newline="") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["official_region_code"], "11680")
            self.assertEqual(row["mapping_status"], "resolved_from_data")


if __name__ == "__main__":
    unittest.main()
