"""서울 바깥 ZIP과 지역별 category ZIP snapshot의 원본 보존을 점검한다."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from data_pipeline.tools.materialize_regional_archives import materialize_regional_archives


class MaterializeRegionalArchivesTest(unittest.TestCase):
    def test_direct_and_nested_archives_are_materialized_without_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            gangwon = base / "강원특별자치도_강릉시"
            (gangwon / "방문자").mkdir(parents=True)
            direct_archive = gangwon / "방문자" / "2024_01_12.zip"
            with zipfile.ZipFile(direct_archive, "w") as archive:
                archive.writestr("방문자.csv", "기준연월,방문자수\n202401,1\n")
            original_direct = direct_archive.read_bytes()

            outer = base / "서울특별시.zip"
            inner_buffer = io.BytesIO()
            with zipfile.ZipFile(inner_buffer, "w") as inner:
                inner.writestr("방문자.csv", "기준연월,방문자수\n202401,1\n")
            with zipfile.ZipFile(outer, "w") as bundle:
                bundle.writestr(
                    "서울특별시/서울특별시_강남구/방문자/2024_01_12.zip",
                    inner_buffer.getvalue(),
                )

            output = base / "raw"
            manifest = base / "manifest"
            summary = materialize_regional_archives(
                gangwon_root=base,
                seoul_outer_zip=outer,
                output_root=output,
                manifest_dir=manifest,
            )

            self.assertEqual(direct_archive.read_bytes(), original_direct)
            self.assertEqual(summary["direct_archive_count"], 1)
            self.assertEqual(summary["nested_archive_count"], 1)
            self.assertTrue((output / "강원특별자치도" / "강원특별자치도_강릉시" / "방문자" / "2024_01_12.zip").is_file())
            self.assertTrue((output / "서울특별시" / "서울특별시_강남구" / "방문자" / "2024_01_12.zip").is_file())
            with (manifest / "regional_archive_manifest.csv").open(encoding="utf-8-sig", newline="") as source:
                self.assertEqual(len(list(csv.DictReader(source))), 3)

            # 동일 상대경로의 새 공식 ZIP은 기존 snapshot을 바꾸지 않고 날짜별
            # conflict 보관소에만 별도 저장해야 한다.
            with zipfile.ZipFile(direct_archive, "w") as archive:
                archive.writestr("방문자.csv", "기준연월,방문자수\n202401,2\n")
            versioned_root = output / "versioned_conflicts" / "20260903"
            second_summary = materialize_regional_archives(
                gangwon_root=base,
                seoul_outer_zip=outer,
                output_root=output,
                manifest_dir=base / "manifest-second",
                conflict_snapshot_root=versioned_root,
            )
            self.assertEqual(second_summary["versioned_conflict_count"], 1)
            self.assertEqual(
                (versioned_root / "강원특별자치도" / "강원특별자치도_강릉시" / "방문자" / "2024_01_12.zip").read_bytes(),
                direct_archive.read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
