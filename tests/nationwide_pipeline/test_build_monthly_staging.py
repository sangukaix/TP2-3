"""월별 staging이 원본 행과 제외 사유를 빠짐없이 기록하는지 확인한다."""

from __future__ import annotations

import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from data_pipeline.tools.build_monthly_staging import build_staging, normalize_number
from data_pipeline.tools.data_inventory import build_inventory


class MonthlyStagingTest(unittest.TestCase):
    # 과학 표기와 천 단위 쉼표를 DB 적재 가능한 문자열로 바꾼다.
    def test_normalize_number(self) -> None:
        self.assertEqual(normalize_number("1.25E3"), "1250")
        self.assertEqual(normalize_number("1,234.50"), "1234.5")

    # 단일 지역의 방문·소비를 같은 region_code + year_month 행으로 병합한다.
    def test_build_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "raw"
            visitor_dir = root / "서울특별시_강남구" / "방문자"
            spend_dir = root / "서울특별시_강남구" / "관광소비"
            visitor_dir.mkdir(parents=True)
            spend_dir.mkdir(parents=True)

            with zipfile.ZipFile(visitor_dir / "2025_01_12.zip", "w") as archive:
                archive.writestr(
                    "방문자 수(연인원) 추이.csv",
                    "기준년월,방문자수,전년동월방문자수,방문자수증감률\n202501,100,90,11.1\n",
                )
                archive.writestr(
                    "지역코드.csv",
                    "기준연월,지역코드,지역명\n202501,11680,강남구\n",
                )
            with zipfile.ZipFile(spend_dir / "2025_01_12.zip", "w") as archive:
                archive.writestr(
                    "관광소비 추이_내국인.csv",
                    "기준연월,업종대분류명,소비액(천원)\n202501,전체,250\n202501,식음료업,100\n",
                )

            inventory_dir = Path(temp_dir) / "inventory"
            output_dir = Path(temp_dir) / "processed"
            build_inventory(root, inventory_dir)
            summary = build_staging(root, inventory_dir, output_dir)

            self.assertEqual(summary["monthly_row_count"], 1)
            self.assertEqual(summary["row_accounting_failure_count"], 0)
            with (output_dir / "tourism_monthly_staging.csv").open(
                encoding="utf-8-sig", newline=""
            ) as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["region_code"], "11680")
            self.assertEqual(row["visitors"], "100")
            self.assertEqual(row["domestic_tourism_spend_thousand_krw"], "250")


if __name__ == "__main__":
    unittest.main()
