"""강남구 7개 월별 관광지표의 학습·평가·온라인 예측 기능입니다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import cos, pi, sin
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from .evaluation import BASELINE, TEST_MONTHS, VALIDATION_MONTHS, error_metrics, select_and_evaluate
from .gangnam_data import PROJECT_ROOT, REGION_CODE, load_gangnam_monthly_demand, write_processed_dataset
from .validation import TARGETS, data_fingerprint


ARTIFACT_DIRECTORY = PROJECT_ROOT / 'artifacts' / 'ml' / REGION_CODE
MODEL_PATH = ARTIFACT_DIRECTORY / 'demand_model.joblib'
METADATA_PATH = ARTIFACT_DIRECTORY / 'demand_model.metadata.json'
MODEL_VERSION = 'demand-v3.0'

# 방문자와 소비액은 서로의 과거 흐름을 함께 사용하고, 나머지는 해당 지표의 과거값만 사용합니다.
FEATURE_NAMES = (
    'visitors_lag_1', 'visitors_lag_3', 'visitors_lag_12',
    'spending_lag_1', 'spending_lag_3', 'spending_lag_12',
    'month_sin', 'month_cos',
)
TARGET_LABELS = {
    'visitors': '월간 외지인 순 방문자 수',
    'spending_krw': '월간 외지인 관광소비액(원)',
    'lodging_nights': '월간 평균 숙박일수(일)',
    'lodging_rate_pct': '월간 숙박방문자 비율(%)',
    'stay_minutes': '월간 평균 체류시간(분)',
    'navigation_searches': '월간 내비게이션 목적지 검색량(건)',
    'lodging_searches': '월간 숙박 목적지 검색건수(건)',
}
COUNT_TARGETS = {'visitors', 'spending_krw', 'navigation_searches', 'lodging_searches'}


@dataclass(frozen=True)
class RegionForecastSettings:
    """한 지역의 원자료 어댑터와 모델 산출물 경로를 묶는 재사용 설정입니다.

    예측 알고리즘은 모든 지역이 공유하지만, 원자료를 읽는 함수와 Joblib 경로는 지역별로 분리합니다.
    이 설정 덕분에 강남구 모델을 다른 시군구에 복사하지 않습니다.
    """

    region_code: str
    region_name: str
    load_monthly: Callable[[], pd.DataFrame]
    write_processed: Callable[[], pd.DataFrame]
    artifact_directory: Path
    model_version: str = MODEL_VERSION


def _univariate_feature_names(target_key: str) -> tuple[str, ...]:
    """새 Target도 같은 lag 규칙을 쓰도록 Feature 이름을 한곳에서 만듭니다."""
    return (
        f'{target_key}_lag_1', f'{target_key}_lag_3', f'{target_key}_lag_12',
        'month_sin', 'month_cos',
    )


FEATURE_NAMES_BY_TARGET = {
    key: list(FEATURE_NAMES if key in {'visitors', 'spending_krw'} else _univariate_feature_names(key))
    for key in TARGETS
}
# 기존 수업용 테스트·노트북에서 import하던 이름은 평균 숙박일 Feature의 별칭으로 유지합니다.
LODGING_FEATURE_NAMES = tuple(FEATURE_NAMES_BY_TARGET['lodging_nights'])


def _next_month(year_month: str) -> str:
    """YYYYMM 한 달 뒤의 안정적인 키를 만듭니다."""
    year, month = int(year_month[:4]), int(year_month[4:]) + 1
    if month == 13:
        year, month = year + 1, 1
    return f'{year}{month:02d}'


def _season_features(target_month: str) -> list[float]:
    """1월과 12월이 가깝다는 월 순환성을 sin·cos 두 값으로 표현합니다."""
    month_number = int(target_month[4:])
    return [sin(2 * pi * month_number / 12), cos(2 * pi * month_number / 12)]


def _feature_row(visitors: list[float], spending: list[float], target_month: str) -> list[float]:
    """방문·소비의 1·3·12개월 전 값과 계절 정보만 사용합니다."""
    if len(visitors) < 12 or len(spending) < 12:
        raise ValueError('12개월 이상의 과거 관측값이 있어야 예측 피처를 만들 수 있습니다.')
    return [
        visitors[-1], visitors[-3], visitors[-12],
        spending[-1], spending[-3], spending[-12],
        *_season_features(target_month),
    ]


def _univariate_feature_row(history: list[float], target_month: str) -> list[float]:
    """체류·검색 지표는 자기 과거값과 계절만 사용해 데이터 누수를 막습니다."""
    if len(history) < 12:
        raise ValueError('12개월 이상의 과거 관측값이 있어야 예측 피처를 만들 수 있습니다.')
    return [history[-1], history[-3], history[-12], *_season_features(target_month)]


def make_supervised_frame(
    monthly: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], np.ndarray, np.ndarray]:
    """방문·소비 시계열을 과거 Feature → 다음 달 Target 표로 변환합니다."""
    months = monthly['year_month'].astype(str).tolist()
    visitors = monthly['visitors'].astype(float).tolist()
    spending = monthly['spending_krw'].astype(float).tolist()
    rows, visitor_targets, spending_targets = [], [], []
    target_months, visitor_baseline, spending_baseline = [], [], []
    for index in range(12, len(months)):
        rows.append(_feature_row(visitors[:index], spending[:index], months[index]))
        visitor_targets.append(visitors[index])
        spending_targets.append(spending[index])
        target_months.append(months[index])
        visitor_baseline.append(visitors[index - 12])
        spending_baseline.append(spending[index - 12])
    return (
        np.asarray(rows), np.asarray(visitor_targets), np.asarray(spending_targets), target_months,
        np.asarray(visitor_baseline), np.asarray(spending_baseline),
    )


def make_univariate_supervised_frame(
    monthly: pd.DataFrame, target_key: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """지표 하나의 lag Feature·Target·전년 동월 기준선을 같은 규칙으로 만듭니다."""
    if target_key not in monthly.columns:
        raise ValueError(f'학습표에 {target_key} 열이 없습니다.')
    months = monthly['year_month'].astype(str).tolist()
    values = monthly[target_key].astype(float).tolist()
    rows, targets, baseline, target_months = [], [], [], []
    for index in range(12, len(months)):
        rows.append(_univariate_feature_row(values[:index], months[index]))
        targets.append(values[index])
        baseline.append(values[index - 12])
        target_months.append(months[index])
    return np.asarray(rows), np.asarray(targets), np.asarray(baseline), target_months


def make_lodging_supervised_frame(monthly: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """기존 호출부를 위한 평균 숙박일 전용 호환 함수입니다."""
    features, targets, baseline, _ = make_univariate_supervised_frame(monthly, 'lodging_nights')
    return features, targets, baseline


_metrics = error_metrics


def _random_forest() -> RandomForestRegressor:
    """작은 월별 표에서 과적합을 줄이도록 깊이와 잎 크기를 제한합니다."""
    return RandomForestRegressor(n_estimators=300, max_depth=3, min_samples_leaf=2, random_state=42)


def _factory_for(target_key: str) -> Callable[[], Any]:
    """수량형 수요는 비선형 후보, 비율·시간·금액은 선형 후보와 기준선을 비교합니다."""
    if target_key in {'visitors', 'navigation_searches', 'lodging_searches'}:
        return _random_forest
    return LinearRegression


def _training_frame(
    monthly: pd.DataFrame, target_key: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Target에 맞는 공통/단일 Feature 표를 선택합니다."""
    if target_key in {'visitors', 'spending_krw'}:
        features, visitors, spending, months, visitor_baseline, spending_baseline = make_supervised_frame(monthly)
        if target_key == 'visitors':
            return features, visitors, visitor_baseline, months
        return features, spending, spending_baseline, months
    return make_univariate_supervised_frame(monthly, target_key)


def _model_inputs(histories: dict[str, list[float]], target_key: str, month: str) -> np.ndarray:
    """온라인 예측에서도 학습 때와 동일한 Feature 순서를 재사용합니다."""
    if target_key in {'visitors', 'spending_krw'}:
        row = _feature_row(histories['visitors'], histories['spending_krw'], month)
    else:
        row = _univariate_feature_row(histories[target_key], month)
    return np.asarray(row).reshape(1, -1)


def _round_prediction(target_key: str, value: float) -> float | int:
    """원자료 단위에 맞춰 건수·금액은 정수, 비율·기간은 소수로 보존합니다."""
    value = max(0, value)
    return round(value) if target_key in COUNT_TARGETS else round(value, 2)


def _recursive_forecasts(artifact: dict, monthly: pd.DataFrame, horizon: int) -> list[dict]:
    """앞 달 예측값을 다음 달 입력에 넣어 요청 기간만큼 재귀 예측합니다.

    계산 가능 기간과 검증된 기간은 다릅니다. 현재 1~3개월만 별도 재귀 시험했으며,
    기획용 4~12개월 결과는 horizon_policy에서 탐색 전망으로 표시합니다.
    """
    months = monthly['year_month'].astype(str).tolist()
    histories = {key: monthly[key].astype(float).tolist() for key in TARGETS}
    models = artifact.get('models') or {}
    if not models:
        models = {
            'visitors': artifact.get('visitor_model'), 'spending_krw': artifact.get('spending_model'),
            'lodging_nights': artifact.get('lodging_model'),
        }
    result = []
    for _ in range(horizon):
        month = _next_month(months[-1])
        row = {'month': month, 'is_forecast': True}
        for key in TARGETS:
            model = models.get(key)
            value = float(model.predict(_model_inputs(histories, key, month))[0]) if model is not None else histories[key][-12]
            if not np.isfinite(value):
                raise ValueError('ML_PREDICTION_INVALID: 유한한 예측값을 만들지 못했습니다.')
            row[key] = _round_prediction(key, value)
        for key in TARGETS:
            histories[key].append(float(row[key]))
        months.append(month)
        result.append(row)
    return result


def _fit_selected_models(monthly: pd.DataFrame, evaluation: dict[str, Any]) -> dict[str, Any]:
    """Validation에서 선택된 Target만 후보모델을 fit하고 기준선 Target은 None으로 둡니다."""
    models = {}
    for key in TARGETS:
        if evaluation[key]['selected_model'] == BASELINE:
            models[key] = None
            continue
        features, targets, _, _ = _training_frame(monthly, key)
        models[key] = _factory_for(key)().fit(features, targets)
    return models


def _recursive_test(monthly: pd.DataFrame, evaluation: dict[str, Any]) -> dict[str, Any]:
    """마지막 Test 구간에서 실제 미래값을 입력하지 않고 1·2·3개월 오차를 확인합니다."""
    results = {
        key: {str(h): {'actual': [], 'predicted': [], 'baseline': []} for h in range(1, 4)}
        for key in TARGETS
    }
    origins = []
    for origin in range(len(monthly) - TEST_MONTHS, len(monthly) - 2):
        history = monthly.iloc[:origin]
        artifact = {'models': _fit_selected_models(history, evaluation)}
        forecasts = _recursive_forecasts(artifact, history, 3)
        origins.append(str(history['year_month'].iloc[-1]))
        for index, forecast in enumerate(forecasts):
            for key in TARGETS:
                bucket = results[key][str(index + 1)]
                bucket['actual'].append(float(monthly[key].iloc[origin + index]))
                bucket['predicted'].append(float(forecast[key]))
                bucket['baseline'].append(float(monthly[key].iloc[origin + index - 12]))
    return {
        'method': 'rolling_origin_recursive_1_to_3_months',
        'origins': origins,
        'by_horizon': {
            key: {
                horizon: {
                    'selected': error_metrics(bucket['actual'], bucket['predicted']),
                    'baseline': error_metrics(bucket['actual'], bucket['baseline']),
                }
                for horizon, bucket in horizons.items()
            }
            for key, horizons in results.items()
        },
    }


def train_region_models(settings: RegionForecastSettings) -> dict[str, Any]:
    """설정된 한 지역의 7개 Target을 시간순 검증하고 Joblib으로 저장합니다."""
    # 웹 요청에서는 실행하지 않습니다. 지역별 원본 검증이 끝난 관리용 CLI에서만 호출합니다.


    print('')
    monthly = settings.write_processed()
    evaluation, models, target_months = {}, {}, None
    for key in TARGETS:
        features, targets, baseline, months = _training_frame(monthly, key)
        model, result = select_and_evaluate(features, targets, baseline, _factory_for(key))
        models[key], evaluation[key] = model, result
        target_months = target_months or months

    fingerprint = data_fingerprint(monthly)
    artifact = {
        'version': settings.model_version, 'region_code': settings.region_code, 'data_fingerprint': fingerprint,
        'feature_names': FEATURE_NAMES, 'models': models,
        'latest_observed_month': str(monthly['year_month'].iloc[-1]),
    }
    test_start = len(target_months) - TEST_MONTHS
    val_start = test_start - VALIDATION_MONTHS
    metadata = {
        'version': settings.model_version,
        'region_code': settings.region_code,
        'region_name': settings.region_name,
        'trained_at': datetime.now(timezone.utc).isoformat(),
        'data_fingerprint': fingerprint,
        'target': TARGET_LABELS,
        'source_period': f"{monthly['year_month'].iloc[0]}~{monthly['year_month'].iloc[-1]}",
        'observation_count': len(monthly),
        'feature_names': list(FEATURE_NAMES),
        'feature_names_by_target': FEATURE_NAMES_BY_TARGET,
        'train_target_period': f'{target_months[0]}~{target_months[val_start - 1]}',
        'validation_period': f'{target_months[val_start]}~{target_months[test_start - 1]}',
        'test_period': f'{target_months[test_start]}~{target_months[-1]}',
        'baseline': BASELINE,
        'evaluation': evaluation,
        'recursive_evaluation': _recursive_test(monthly, evaluation),
        'limitations': [
            f'{len(monthly)}개월·한 지역의 초기 모델이며 3개월 재귀 시험 origin은 제한적일 수 있습니다.',
            '모델 선택은 Validation에서만 하며 Test 결과를 보고 선택을 바꾸지 않습니다.',
            '예측은 기존 이력의 자연 추세이며 정책 미실행 반사실이나 사업 인과효과가 아닙니다.',
            '검색량은 관심 신호이며 실제 방문자·숙박 예약 건수와 같은 지표가 아닙니다.',
            '업종별 소비비중과 SNS 언급량은 이번 1차 추가 ML의 Target이 아닙니다.',
        ],
    }
    settings.artifact_directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, settings.artifact_directory / 'demand_model.joblib')
    (settings.artifact_directory / 'demand_model.metadata.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8',
    )
    return metadata


def _load_region_artifact(settings: RegionForecastSettings) -> tuple[dict[str, Any], dict[str, Any]]:
    """온라인 요청은 해당 지역의 저장 산출물만 읽고 자동 재학습하지 않습니다."""
    model_path = settings.artifact_directory / 'demand_model.joblib'
    metadata_path = settings.artifact_directory / 'demand_model.metadata.json'
    if not model_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(f'ML_MODEL_MISSING: {settings.region_name} 모델이 아직 없습니다. train_regions CLI를 실행하세요.')
    return joblib.load(model_path), json.loads(metadata_path.read_text(encoding='utf-8'))


def predict_region_future_months(settings: RegionForecastSettings, horizon: int = 4) -> dict[str, Any]:
    """저장된 해당 지역 모델로 최신 관측월 뒤 지정한 개월만 예측합니다."""
    if horizon < 3 or horizon > 24:
        raise ValueError('예측 기간은 3개월 이상 24개월 이하여야 합니다.')
    artifact, metadata = _load_region_artifact(settings)
    monthly = settings.load_monthly()
    if artifact.get('data_fingerprint') and artifact['data_fingerprint'] != data_fingerprint(monthly):
        raise ValueError('ML_MODEL_STALE: 원자료가 변경되었습니다. train_regions CLI로 재학습하세요.')
    if metadata.get('data_fingerprint') != artifact.get('data_fingerprint'):
        raise ValueError('ML_ARTIFACT_MISMATCH: 모델과 평가 메타데이터 버전이 다릅니다.')
    forecasts = _recursive_forecasts(artifact, monthly, horizon)
    latest = monthly.iloc[-1]
    return {
        'latest_observed_month': str(latest['year_month']),
        'latest_observed_visitors': round(float(latest['visitors'])),
        'latest_observed_spending_krw': round(float(latest['spending_krw'])),
        'latest_observed_lodging_nights': round(float(latest['lodging_nights']), 2),
        'latest_observed_metrics': {key: _round_prediction(key, float(latest[key])) for key in TARGETS},
        'recent_actuals': [
            {
                'month': str(row.year_month), 'is_forecast': False,
                **{key: _round_prediction(key, float(getattr(row, key))) for key in TARGETS},
            }
            for row in monthly.tail(3).itertuples(index=False)
        ],
        'forecasts': forecasts,
        'model': metadata,
    }


# 기존 강남구 호출부와 수업용 import는 유지하면서, 내부 알고리즘만 공통 지역 함수로 연결합니다.
GANGNAM_FORECAST_SETTINGS = RegionForecastSettings(
    region_code=REGION_CODE,
    region_name='서울특별시 강남구',
    load_monthly=load_gangnam_monthly_demand,
    write_processed=write_processed_dataset,
    artifact_directory=ARTIFACT_DIRECTORY,
    model_version=MODEL_VERSION,
)


def train_gangnam_models() -> dict[str, Any]:
    """기존 CLI 호환용 강남구 학습 함수입니다."""

    print('train_region_models(GANGNAM_FORECAST_SETTINGS)으로 변수값을 넣어 리턴 : gangnam_forecast.py')
    print('GANGNAM_FORECAST_SETTINGS: ', GANGNAM_FORECAST_SETTINGS)
    print()


    return train_region_models(GANGNAM_FORECAST_SETTINGS)


def predict_future_months(horizon: int = 4) -> dict[str, Any]:
    """기존 API 호환용 강남구 예측 함수입니다."""
    return predict_region_future_months(GANGNAM_FORECAST_SETTINGS, horizon)


def predict_next_three_months() -> dict[str, Any]:
    """기존 호출부 호환용 3개월 예측 함수입니다."""
    return predict_future_months(3)
