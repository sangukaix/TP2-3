"""강남구 ML 전처리의 기간·누수 방지 규칙을 확인하는 단위 테스트입니다."""

import unittest

from ai_server.ml.gangnam_data import load_gangnam_monthly_demand
from ai_server.ml.gangnam_forecast import FEATURE_NAMES, LODGING_FEATURE_NAMES, make_lodging_supervised_frame, make_supervised_frame


class GangnamForecastTest(unittest.TestCase):
    """공식 원본을 읽는 전처리와 지도학습 행 생성만 빠르게 점검합니다."""

    def test_monthly_source_has_continuous_common_months(self) -> None:
        """7개 Target이 모두 있는 2024~2026 공통 월만 학습표에 남는지 확인합니다."""
        frame = load_gangnam_monthly_demand()
        self.assertEqual(frame['year_month'].iloc[0], '202401')
        self.assertEqual(frame['year_month'].iloc[-1], '202607')
        self.assertEqual(len(frame), 31)
        self.assertTrue(frame['visitors'].gt(0).all())
        self.assertTrue(frame['spending_krw'].gt(0).all())
        self.assertTrue(frame['lodging_nights'].gt(0).all())
        for target in ('lodging_rate_pct', 'stay_minutes', 'navigation_searches', 'lodging_searches'):
            self.assertTrue(frame[target].gt(0).all(), target)

    def test_supervised_features_only_start_after_twelve_past_months(self) -> None:
        """12개월 전 계절 피처를 쓰므로 첫 12개월은 학습 목표로 사용하지 않습니다."""
        frame = load_gangnam_monthly_demand()
        features, visitor_target, spending_target, target_months, visitor_baseline, spending_baseline = make_supervised_frame(frame)
        self.assertEqual(features.shape, (19, len(FEATURE_NAMES)))
        self.assertEqual(target_months[0], '202501')
        self.assertEqual(visitor_target.shape, spending_target.shape)
        self.assertEqual(visitor_target.shape, visitor_baseline.shape)
        self.assertEqual(visitor_target.shape, spending_baseline.shape)

    def test_lodging_features_also_use_only_past_months(self) -> None:
        """숙박일 예측도 같은 12개월 시차 규칙으로 미래값 누수를 막습니다."""
        features, targets, baseline = make_lodging_supervised_frame(load_gangnam_monthly_demand())
        self.assertEqual(features.shape, (19, len(LODGING_FEATURE_NAMES)))
        self.assertEqual(targets.shape, baseline.shape)
