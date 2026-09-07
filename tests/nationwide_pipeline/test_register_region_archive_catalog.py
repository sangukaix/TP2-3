"""원본 코드·행정코드·경로를 함께 검증한 archive 카탈로그 등록을 확인한다."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from data_pipeline.tools.register_region_archive_catalog import CATALOG_FIELDS, build_catalog_rows


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class RegisterRegionArchiveCatalogTest(unittest.TestCase):
    def test_matching_internal_and_official_code_creates_archive_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_root = root / "data" / "raw"
            (raw_root / "서울특별시" / "서울특별시_테스트구").mkdir(parents=True)
            catalog = root / "data" / "catalog" / "region_data_registry.csv"
            _write_csv(catalog, CATALOG_FIELDS, [])
            inventory = root / "inventory"
            _write_csv(
                inventory / "region_code_candidates.csv",
                ["region_folder", "province_name", "municipality_name", "mapping_status", "official_region_code"],
                [{
                    "region_folder": "서울특별시_테스트구",
                    "province_name": "서울특별시",
                    "municipality_name": "테스트구",
                    "mapping_status": "resolved_from_data",
                    "official_region_code": "99999",
                }],
            )
            official = root / "official.csv"
            _write_csv(
                official,
                ["region_code", "province_name", "municipality_name"],
                [{"region_code": "99999", "province_name": "서울특별시", "municipality_name": "테스트구"}],
            )

            rows, summary = build_catalog_rows(
                catalog_path=catalog,
                inventory_dirs=[inventory],
                official_codes_path=official,
                raw_root=raw_root,
                downloaded_at="2026-08-31",
            )

            self.assertEqual(summary["added_count"], 1)
            self.assertEqual(summary["rejected_count"], 0)
            self.assertEqual(rows[0]["raw_relative_path"], "data/raw/서울특별시/서울특별시_테스트구")
            self.assertEqual(rows[0]["adapter_type"], "standard_datalab_archive")
            self.assertEqual(rows[0]["provenance_status"], "needs_exact_download_url")

    def test_city_district_uses_full_hierarchy_for_official_name_check(self) -> None:
        """고양시_덕양구 같은 계층형 폴더는 코드표의 전체 명칭과 대조한다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_root = root / "data" / "source_snapshots"
            (raw_root / "경기도" / "경기도_고양시_덕양구").mkdir(parents=True)
            catalog = root / "data" / "catalog" / "region_data_registry.csv"
            _write_csv(catalog, CATALOG_FIELDS, [])
            inventory = root / "inventory"
            _write_csv(
                inventory / "region_code_candidates.csv",
                [
                    "region_folder", "province_name", "municipality_name",
                    "local_hierarchy_name", "mapping_status", "official_region_code",
                ],
                [{
                    "region_folder": "경기도_고양시_덕양구",
                    "province_name": "경기도",
                    "municipality_name": "덕양구",
                    "local_hierarchy_name": "고양시_덕양구",
                    "mapping_status": "resolved_from_data",
                    "official_region_code": "41281",
                }],
            )
            official = root / "official.csv"
            _write_csv(
                official,
                ["region_code", "province_name", "municipality_name"],
                [{"region_code": "41281", "province_name": "경기도", "municipality_name": "고양시 덕양구"}],
            )

            rows, summary = build_catalog_rows(
                catalog_path=catalog,
                inventory_dirs=[inventory],
                official_codes_path=official,
                raw_root=raw_root,
                downloaded_at="2026-09-03",
            )

            self.assertEqual(summary["added_count"], 1)
            self.assertEqual(summary["rejected_count"], 0)
            self.assertEqual(rows[0]["region_name"], "경기도 고양시 덕양구")
            self.assertEqual(rows[0]["short_name"], "덕양구")


if __name__ == "__main__":
    unittest.main()
