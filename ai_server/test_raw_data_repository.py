"""원자료 Repository의 재사용과 파일 변경 감지를 외부 API 없이 검증합니다."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ai_server.app.raw_data_repository import raw_table_cache_info, read_region_tables


class RawDataRepositoryTest(unittest.TestCase):
    def test_reuses_unchanged_csv_and_invalidates_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            region_directory = Path(temporary_directory)
            csv_path = region_directory / '방문자 수(연인원) 추이.csv'
            csv_path.write_text('기준년월,방문자수\n202601,100\n', encoding='utf-8-sig')

            first = read_region_tables(region_directory)
            first_cache = raw_table_cache_info()
            second = read_region_tables(region_directory)
            second_cache = raw_table_cache_info()

            self.assertIs(first, second)
            self.assertEqual(second_cache.hits, first_cache.hits + 1)
            self.assertEqual(second['방문자 수(연인원) 추이.csv'][0]['방문자수'], '100')

            csv_path.write_text('기준년월,방문자수\n202601,2500\n', encoding='utf-8-sig')
            changed = read_region_tables(region_directory)

            self.assertIsNot(changed, second)
            self.assertEqual(changed['방문자 수(연인원) 추이.csv'][0]['방문자수'], '2500')


if __name__ == '__main__':
    unittest.main()
