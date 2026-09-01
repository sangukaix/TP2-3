"""원자료 Repository의 재사용과 파일 변경 감지를 외부 API 없이 검증합니다."""

from __future__ import annotations

from pathlib import Path
from io import BytesIO
import tempfile
import unittest
from zipfile import ZipFile

from ai_server.app.raw_data_repository import raw_table_cache_info, read_region_tables


class RawDataRepositoryTest(unittest.TestCase):
    def test_reads_a_catalog_style_single_zip_path(self) -> None:
        """강남구처럼 카탈로그가 ZIP 파일 자체를 가리키는 원본도 읽습니다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            zip_path = Path(temporary_directory) / 'region.zip'
            with ZipFile(zip_path, 'w') as archive:
                archive.writestr('방문자 수.csv', '기준년월,방문자수\n202601,321\n'.encode('utf-8-sig'))

            tables = read_region_tables(zip_path)

            self.assertEqual(tables['region.zip::방문자 수.csv'][0]['방문자수'], '321')

    def test_reads_nested_zip_without_extracting_raw_files(self) -> None:
        """데이터랩 묶음 ZIP 안쪽 ZIP의 CSV도 data/raw를 수정하지 않고 읽습니다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            inner_buffer = BytesIO()
            with ZipFile(inner_buffer, 'w') as inner:
                inner.writestr('관광소비 추이.csv', '기준년월,소비액\n202601,999\n'.encode('utf-8-sig'))
            outer_path = Path(temporary_directory) / 'bundle.zip'
            with ZipFile(outer_path, 'w') as outer:
                outer.writestr('서울특별시_강남구/관광소비/2026.zip', inner_buffer.getvalue())

            tables = read_region_tables(outer_path)

            nested_name = next(name for name in tables if name.endswith('관광소비 추이.csv'))
            self.assertEqual(tables[nested_name][0]['소비액'], '999')

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
