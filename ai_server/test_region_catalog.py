"""지역 확장 카탈로그와 읽기 전용 사전점검 CLI를 확인합니다."""

from __future__ import annotations

import unittest

from ai_server.ml.region_catalog import get_region_data_catalog_entry, list_region_data_catalog
from ai_server.ml.scripts.check_regions import check_region


class RegionCatalogTest(unittest.TestCase):
    """카탈로그 한 줄이 표준 CSV 지역의 등록·점검 기준이 되는지 확인합니다."""

    def test_enabled_catalog_has_current_ml_regions(self) -> None:
        """현재 등록된 강남구·계양구 코드가 중복 없이 보이는지 검사합니다."""
        codes = [entry.region_code for entry in list_region_data_catalog()]
        self.assertIn('11680', codes)
        self.assertIn('28245', codes)
        self.assertEqual(len(codes), len(set(codes)))

    def test_gyeyang_preflight_reads_standard_csv_without_writing_raw(self) -> None:
        """계양구 공통 CSV가 30개월·7개 Target으로 점검되는지 확인합니다."""
        result = check_region(get_region_data_catalog_entry('28245'))
        self.assertEqual(result['status'], 'ready_with_provenance_warnings')
        self.assertEqual(result['observation_count'], 30)
        self.assertEqual((result['source_period']), '202401~202606')
        self.assertEqual(len(result['targets']), 7)


if __name__ == '__main__':
    unittest.main()
