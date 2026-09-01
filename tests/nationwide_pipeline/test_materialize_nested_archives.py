"""중첩 ZIP의 한글 경로 복원과 경로 탈출 차단을 검증한다."""

from __future__ import annotations

import unittest

from data_pipeline.tools.materialize_nested_archives import repair_member_name, safe_relative_member


class MaterializeNestedArchivesTest(unittest.TestCase):
    def test_cp949_filename_is_repaired_and_bundle_folder_removed(self) -> None:
        original = "서울특별시/서울특별시_강남구/방문자/2026_01_06.zip"
        mojibake = original.encode("cp949").decode("cp437")
        self.assertEqual(repair_member_name(mojibake), original)
        self.assertEqual(
            safe_relative_member(mojibake).as_posix(),
            "서울특별시_강남구/방문자/2026_01_06.zip",
        )

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            safe_relative_member("../outside.zip")


if __name__ == "__main__":
    unittest.main()
