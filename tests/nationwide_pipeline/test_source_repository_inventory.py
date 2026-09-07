"""상위 공유폴더 inventory가 변경 파일만 다시 처리하는지 확인한다."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from data_pipeline.tools.source_repository_inventory import build_repository_inventory


class SourceRepositoryInventoryTest(unittest.TestCase):
    # 첫 실행은 new, 같은 파일 재실행은 unchanged로 기록한다.
    def test_incremental_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repository"
            section = root / "전국 현황"
            section.mkdir(parents=True)
            (section / "방문자수.csv").write_text(
                "기준연월,방문자수\n202501,100\n", encoding="utf-8"
            )
            output = Path(temp_dir) / "inventory"

            first = build_repository_inventory(root, output)
            second = build_repository_inventory(root, output)
            self.assertEqual(first["change_counts"], {"new": 1})
            self.assertEqual(second["change_counts"], {"unchanged": 1})

            audited = build_repository_inventory(root, output, full_hash=True)
            self.assertEqual(audited["change_counts"], {"verified_unchanged": 1})
            self.assertEqual(audited["hash_mode"], "full")

            with (output / "files.csv").open(encoding="utf-8-sig", newline="") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["section"], "전국 현황")
            self.assertEqual(row["change_status"], "verified_unchanged")

    # 사라진 파일은 삭제하지 않고 deleted audit에 남긴다.
    def test_deleted_file_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repository"
            root.mkdir()
            source_file = root / "out.csv"
            source_file.write_text("a\n1\n", encoding="utf-8")
            output = Path(temp_dir) / "inventory"
            build_repository_inventory(root, output)
            source_file.unlink()
            summary = build_repository_inventory(root, output)
            self.assertEqual(summary["deleted_file_count"], 1)


if __name__ == "__main__":
    unittest.main()
