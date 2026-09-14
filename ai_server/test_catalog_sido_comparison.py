"""A flat snapshot must support province comparison just like the old raw hierarchy."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_server.app import main


class CatalogSidoComparisonTest(unittest.TestCase):
    def test_flat_catalog_paths_and_district_labels_are_used(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / 'flat_one', root / 'flat_two'
            first.mkdir()
            second.mkdir()
            entries = [SimpleNamespace(region_name='경상남도 창원시 의창구', raw_path=first), SimpleNamespace(region_name='경상남도 창원시 성산구', raw_path=second)]
            tables = {
                '순 방문자 수 및 숙박 비율': [{'기준년월': month, '순 방문자수': '100', '숙박자 비율': '10'} for month in ['202604', '202605', '202606']],
                '관광소비 추이_외지인': [{'기준년월': month, '업종대분류명': '전체', '소비액(천원)': '200'} for month in ['202604', '202605', '202606']],
                '평균 숙박일': [{'기준년월': month, '평균 숙박일수': '2'} for month in ['202604', '202605', '202606']],
            }
            with patch.object(main, 'list_region_data_catalog', return_value=entries), patch.object(main, '_find_sido_directory', side_effect=AssertionError('must use catalog')), patch.object(main, '_read_tables', return_value=tables):
                comparison = main.build_sido_comparison('경상남도')
            self.assertEqual([r.region_name for r in comparison.regions], ['창원시 의창구', '창원시 성산구'])
            self.assertEqual(comparison.period, '2026.04~2026.06')
            self.assertEqual(comparison.regions[0].spending_krw, 200000)


if __name__ == '__main__':
    unittest.main()
