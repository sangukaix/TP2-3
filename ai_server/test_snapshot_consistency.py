"""AI 기획안 관측값과 등록 ML 원자료의 기준월 일치 여부를 점검합니다."""

from __future__ import annotations

import unittest

from ai_server.app.main import build_region_snapshot
from ai_server.ml.region_registry import get_region_pipeline


class SnapshotConsistencyTest(unittest.TestCase):
    """같은 지역의 관측 근거와 ML 전망이 서로 다른 최신월을 쓰지 않게 합니다."""

    def test_gangnam_snapshot_uses_registered_history_latest_month(self) -> None:
        pipeline = get_region_pipeline('11680')
        history = pipeline.load_history()
        expected_month = str(history['year_month'].iloc[-1])

        snapshot = build_region_snapshot('서울특별시 강남구')

        self.assertEqual(snapshot['latest_month'], f'{expected_month[:4]}-{expected_month[4:]}')
        self.assertEqual(snapshot['monthly_trend'][-1]['month'], f'{expected_month[:4]}.{expected_month[4:]}')
        self.assertEqual(snapshot['monthly_trend'][-1]['visitors'], round(float(history.iloc[-1]['visitors'])))
        self.assertEqual(snapshot['monthly_trend'][-1]['spending_krw'], round(float(history.iloc[-1]['spending_krw'])))

    def test_each_observation_keeps_its_actual_period(self) -> None:
        snapshot = build_region_snapshot('서울특별시 강남구')
        periods = {item['metric']: item['period'] for item in snapshot['observations']}

        self.assertEqual(periods['월간 순 방문자 수'], snapshot['latest_month'])
        # SNS 원본 공개가 늦어도 최신 ML 월로 날짜를 바꾸어 표시하지 않습니다.
        self.assertLessEqual(periods['SNS 언급량'], snapshot['latest_month'])


if __name__ == '__main__':
    unittest.main()
