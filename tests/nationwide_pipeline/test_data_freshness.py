"""새 전략기획 생성용 데이터 최신성 차단 규칙을 검증한다."""

from __future__ import annotations

from datetime import date
import unittest

from ai_server.ml.data_freshness import assess_data_freshness


class DataFreshnessTest(unittest.TestCase):
    def test_blocks_after_three_completed_months_are_missing(self) -> None:
        status = assess_data_freshness('202607', as_of_date=date(2026, 11, 15))

        self.assertFalse(status.can_generate)
        self.assertEqual(status.reason_code, 'DATA_REFRESH_REQUIRED')
        self.assertEqual(status.latest_complete_month, '202610')
        self.assertEqual(status.missing_month_count, 3)
        self.assertEqual(status.update_start_month, '202608')
        self.assertEqual(status.update_end_month, '202610')

    def test_allows_short_source_lag_without_counting_current_month(self) -> None:
        status = assess_data_freshness('202607', as_of_date=date(2026, 9, 4))

        self.assertTrue(status.can_generate)
        self.assertEqual(status.status, 'ready')
        self.assertEqual(status.latest_complete_month, '202608')
        self.assertEqual(status.missing_month_count, 1)
        self.assertEqual(status.update_start_month, '202608')

    def test_invalid_observation_month_is_not_silently_accepted(self) -> None:
        status = assess_data_freshness('not-a-month', as_of_date=date(2026, 9, 4))

        self.assertFalse(status.can_generate)
        self.assertEqual(status.reason_code, 'DATA_FRESHNESS_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
