"""시간순 Train → Validation → Test 평가를 여러 지역·지표에서 재사용합니다."""

from __future__ import annotations

from typing import Callable, Any
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


BASELINE = 'seasonal_naive_previous_year_same_month'
VALIDATION_MONTHS = 3
TEST_MONTHS = 4


def _metric_priority(metrics: dict[str, Any]) -> tuple[float, float, float, float]:
    """R²가 1에 가까운 순서, 이후 RMSE·MSE·MAE가 작은 순서로 정렬합니다."""
    r2 = metrics.get('r2')
    return (
        abs(float(r2) - 1.0) if r2 is not None else float('inf'),
        float(metrics.get('rmse', float('inf'))),
        float(metrics.get('mse', float('inf'))),
        float(metrics.get('mae', float('inf'))),
    )


def is_better_by_priority(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    """우선순위 지표가 모두 같으면 기준선을 선택하도록 엄격 비교합니다."""
    return _metric_priority(candidate) < _metric_priority(baseline)


def error_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    """MAE는 평균 절대오차, RMSE는 큰 오차에 민감한 값입니다. 0인 실제값은 MAPE에서 제외합니다."""
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    nonzero = actual != 0
    return {
        'mae': round(float(mean_absolute_error(actual, predicted)), 2),
        'mse': round(float(mean_squared_error(actual, predicted)), 2),
        'rmse': round(float(mean_squared_error(actual, predicted) ** 0.5), 2),
        'r2': round(float(r2_score(actual, predicted)), 4) if len(actual) >= 2 else None,
        'mape_percent': round(float(np.mean(np.abs((actual[nonzero] - predicted[nonzero]) / actual[nonzero])) * 100), 2) if nonzero.any() else None,
        'sample_count': int(len(actual)),
        'mape_sample_count': int(nonzero.sum()),
    }


def select_and_evaluate(
    features: np.ndarray, targets: np.ndarray, baseline: np.ndarray,
    factory: Callable[[], Any],
) -> tuple[Any, dict[str, Any]]:
    """검증 3개월에서 후보/기준선을 선택하고, 마지막 4개월은 선택에 쓰지 않습니다."""
    if len(targets) < 16:
        raise ValueError('시간순 Train/Validation/Test 평가에는 지도학습 행이 16개 이상 필요합니다.')
    test_start = len(targets) - TEST_MONTHS
    validation_start = test_start - VALIDATION_MONTHS
    validation_model = factory().fit(features[:validation_start], targets[:validation_start])
    candidate_validation = error_metrics(targets[validation_start:test_start], np.maximum(0, validation_model.predict(features[validation_start:test_start])))
    baseline_validation = error_metrics(targets[validation_start:test_start], baseline[validation_start:test_start])
    # 검증 지표 우선순위로만 선택합니다. Test 결과로 선택을 바꾸지 않습니다.
    use_model = is_better_by_priority(candidate_validation, baseline_validation)
    test_model = factory().fit(features[:test_start], targets[:test_start])
    candidate_test = error_metrics(targets[test_start:], np.maximum(0, test_model.predict(features[test_start:])))
    baseline_test = error_metrics(targets[test_start:], baseline[test_start:])
    selected_test = candidate_test if use_model else baseline_test
    evaluation = {
        'selected_model': type(test_model).__name__ if use_model else BASELINE,
        'selection_basis': 'validation_r2_then_rmse_mse_mae',
        'validation': {'candidate': candidate_validation, 'baseline': baseline_validation},
        'candidate_test_metrics': candidate_test,
        'selected_model_metrics': selected_test,
        'baseline_metrics': baseline_test,
        'beats_baseline_on_test': selected_test['mae'] < baseline_test['mae'],
        'train_target_count': validation_start,
    }
    # 성능 측정 종료 후에만 모든 관측값으로 최종 모델을 학습합니다.
    return (factory().fit(features, targets) if use_model else None), evaluation
