"""두 번째 등록 지역이 공통 어댑터·ML·대시보드까지 연결되는지 확인합니다."""

from __future__ import annotations

import unittest

from ai_server.app.main import _build_registered_ml_dashboard
from ai_server.ml.region_registry import get_region_pipeline


class RegisteredRegionMlTest(unittest.TestCase):
    """계양구는 강남구 전용 코드가 아닌 공통 계약으로만 동작해야 합니다."""

    def test_gyeyang_csv_adapter_has_continuous_common_months(self) -> None:
        """카탈로그 기반 공통 어댑터가 7개 Target의 30개월을 읽는지 확인합니다."""
        frame = get_region_pipeline('28245').load_history()
        self.assertIsNotNone(frame)
        self.assertEqual(set(frame['region_code']), {'28245'})
        self.assertEqual(len(frame), 30)
        self.assertEqual((frame['year_month'].iloc[0], frame['year_month'].iloc[-1]), ('202401', '202606'))

    def test_registered_pipeline_and_dashboard_use_gyeyang_model(self) -> None:
        """등록표의 계양구 모델이 예측 대시보드로 변환되는지 확인합니다."""
        pipeline = get_region_pipeline('28245')
        self.assertEqual(pipeline.region_name, '인천광역시 계양구')
        dashboard = _build_registered_ml_dashboard('28245', pipeline.region_name)
        self.assertEqual(dashboard.region_name, pipeline.region_name)
        self.assertTrue(dashboard.diagnostic.is_forecast)
        self.assertEqual(len(dashboard.monthly_trend), 6)


if __name__ == '__main__':
    unittest.main()
