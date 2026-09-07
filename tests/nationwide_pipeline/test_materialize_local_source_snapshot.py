"""수동 원본을 snapshot으로 복제할 때 원본·기존 snapshot이 보존되는지 점검한다."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from data_pipeline.tools.materialize_local_source_snapshot import materialize_local_source_snapshot


class MaterializeLocalSourceSnapshotTest(unittest.TestCase):
    def test_materializes_and_reuses_identical_local_source_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "raw" / "인천광역시"
            source_file = source_root / "계양구" / "숙박_체류시간" / "2026" / "월별.csv"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("기준연월,순 방문자수\n202601,1\n", encoding="utf-8")
            original = source_file.read_bytes()

            output_root = root / "source_snapshots"
            manifest_dir = root / "manifest"
            first = materialize_local_source_snapshot(
                source_root=source_root,
                output_root=output_root,
                destination_relative_path=Path("인천광역시"),
                manifest_dir=manifest_dir,
            )
            copied = output_root / "인천광역시" / "계양구" / "숙박_체류시간" / "2026" / "월별.csv"
            self.assertEqual(first["materialized_count"], 1)
            self.assertEqual(first["error_count"], 0)
            self.assertEqual(source_file.read_bytes(), original)
            self.assertEqual(copied.read_bytes(), original)

            second = materialize_local_source_snapshot(
                source_root=source_root,
                output_root=output_root,
                destination_relative_path=Path("인천광역시"),
                manifest_dir=root / "manifest-second",
            )
            self.assertEqual(second["reused_count"], 1)
            with (manifest_dir / "local_source_snapshot_manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["source_sha256"], rows[0]["materialized_sha256"])

    def test_does_not_overwrite_different_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "raw" / "인천광역시"
            source_file = source_root / "계양구" / "source.csv"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("official", encoding="utf-8")
            output_root = root / "source_snapshots"
            target = output_root / "인천광역시" / "계양구" / "source.csv"
            target.parent.mkdir(parents=True)
            target.write_text("different", encoding="utf-8")

            result = materialize_local_source_snapshot(
                source_root=source_root,
                output_root=output_root,
                destination_relative_path=Path("인천광역시"),
                manifest_dir=root / "manifest",
            )
            self.assertEqual(result["error_count"], 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "different")


if __name__ == "__main__":
    unittest.main()
