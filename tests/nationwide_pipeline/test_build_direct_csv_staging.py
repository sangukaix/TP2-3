"""직접 CSV snapshot도 ZIP staging과 같은 사실·출처 구조를 만드는지 확인한다."""

from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_pipeline.tools.build_direct_csv_staging import build_direct_csv_staging


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DirectCsvStagingTest(unittest.TestCase):
    def test_builds_complete_traceable_row_from_direct_csv_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_root = root / "data" / "source_snapshots" / "인천광역시" / "계양구"
            files: dict[str, str] = {}
            for year in (2024, 2025):
                months = [f"{year}{month:02d}" for month in range(1, 13)]
                files[f"방문자/{year}/방문자 수(연인원) 추이.csv"] = (
                    "기준년월,방문자수,전년동월방문자수,방문자수증감률\n"
                    + "".join(f"{month},100,90,11.1\n" for month in months)
                )
                files[f"관광소비/{year}/관광소비 추이_내국인.csv"] = (
                    "기준연월,업종대분류명,소비액(천원)\n"
                    + "".join(f"{month},전체,250\n" for month in months)
                )
                files[f"관광소비/{year}/관광소비 추이_외지인.csv"] = (
                    "기준연월,업종대분류명,소비액(천원)\n"
                    + "".join(f"{month},전체,175\n" for month in months)
                )
                files[f"숙박_체류시간/{year}/순 방문자 수 및 숙박 비율.csv"] = (
                    "기준연월,순 방문자수,숙박자 비율\n"
                    + "".join(f"{month},80,4.5\n" for month in months)
                )
                files[f"숙박_체류시간/{year}/평균 숙박일.csv"] = (
                    "기준연월,평균 숙박일수\n"
                    + "".join(f"{month},2.4\n" for month in months)
                )
                files[f"숙박_체류시간/{year}/평균 체류시간 추이.csv"] = (
                    "기준연월,지역명,체류시간(분)\n"
                    + "".join(f"{month},계양구,120\n" for month in months)
                )
            manifest_rows: list[dict[str, str]] = []
            for relative, contents in files.items():
                path = snapshot_root / relative
                digest = _write(path, contents)
                manifest_rows.append({
                    "materialized_relative_path": f"인천광역시/계양구/{relative}",
                    "materialized_sha256": digest,
                })

            catalog = root / "catalog.csv"
            _write(
                catalog,
                "region_code,region_name,short_name,raw_relative_path,adapter_type,source_name,source_url,downloaded_at,provenance_status,enabled\n"
                "28245,인천광역시 계양구,계양구,data/source_snapshots/인천광역시/계양구,standard_datalab_csv,한국관광 데이터랩,https://example.test,2026-08-24,needs_exact_download_url,true\n",
            )
            manifest = root / "manifest.csv"
            with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["materialized_relative_path", "materialized_sha256"])
                writer.writeheader()
                writer.writerows(manifest_rows)

            with patch("data_pipeline.tools.build_direct_csv_staging.PROJECT_ROOT", root):
                result = build_direct_csv_staging(
                    catalog_path=catalog,
                    region_code="28245",
                    snapshot_manifest_path=manifest,
                    output_dir=root / "output",
                )
            self.assertEqual(result["monthly_row_count"], 24)
            with (root / "output" / "tourism_monthly_staging.csv").open(encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["visitors"], "100")
            self.assertEqual(row["unique_visitors"], "80")
            self.assertEqual(row["nonlocal_tourism_spend_thousand_krw"], "175")
            self.assertTrue(row["visitors_source_id"].startswith("datalab-snapshot:"))


if __name__ == "__main__":
    unittest.main()
