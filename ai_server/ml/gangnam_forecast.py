"""강남구 월별 방문자·관광소비 예측 모델의 학습, 평가, 온라인 조회 기능입니다."""

from __future__ import annotations

import json
from math import cos, pi, sin
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .gangnam_data import PROJECT_ROOT, REGION_CODE, load_gangnam_monthly_demand, write_processed_dataset


ARTIFACT_DIRECTORY = PROJECT_ROOT / 'artifacts' / 'ml' / REGION_CODE
# 모델 파일과 메타데이터를 분리해, 예측 결과뿐 아니라 학습 기간·성능도 함께 확인할 수 있게 합니다.
MODEL_PATH = ARTIFACT_DIRECTORY / 'demand_model.joblib'
METADATA_PATH = ARTIFACT_DIRECTORY / 'demand_model.metadata.json'
MODEL_VERSION = 'gangnam-demand-v1.1'
FEATURE_NAMES = (
    'visitors_lag_1', 'visitors_lag_3', 'visitors_lag_12',
    'spending_lag_1', 'spending_lag_3', 'spending_lag_12',
    'month_sin', 'month_cos',
)
LODGING_FEATURE_NAMES = ('lodging_lag_1', 'lodging_lag_3', 'lodging_lag_12', 'month_sin', 'month_cos')


def _next_month(year_month: str) -> str:
    """YYYYMM 한 달 뒤의 안정적인 키를 만듭니다."""
    year, month = int(year_month[:4]), int(year_month[4:]) + 1
    if month == 13:
        year, month = year + 1, 1
    return f'{year}{month:02d}'


def _feature_row(visitors: list[float], spending: list[float], target_month: str) -> list[float]:
    """예측 시점 이전 값만 써서 누수 없는 한 달치 피처를 만듭니다."""
    if len(visitors) < 12 or len(spending) < 12:
        raise ValueError('12개월 이상의 과거 관측값이 있어야 예측 피처를 만들 수 있습니다.')
    month_number = int(target_month[4:])
    return [
        visitors[-1], visitors[-3], visitors[-12],
        spending[-1], spending[-3], spending[-12],
        sin(2 * pi * month_number / 12), cos(2 * pi * month_number / 12),
    ]


def _lodging_feature_row(lodging_nights: list[float], target_month: str) -> list[float]:
    """평균 숙박일도 과거 숙박일과 계절 정보만으로 다음 달을 예측합니다."""
    if len(lodging_nights) < 12:
        raise ValueError('12개월 이상의 과거 숙박일이 있어야 예측 피처를 만들 수 있습니다.')
    month_number = int(target_month[4:])
    return [
        lodging_nights[-1], lodging_nights[-3], lodging_nights[-12],
        sin(2 * pi * month_number / 12), cos(2 * pi * month_number / 12),
    ]


def make_supervised_frame(monthly: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], np.ndarray, np.ndarray]:
    """원 시계열을 t 시점까지의 피처 → t+1 목표값 형태의 지도학습 표로 변환합니다."""
    # 과거 12개월 lag를 만든 뒤 바로 다음 월을 target으로 지정합니다.
    # 따라서 target 월의 값을 feature에 섞는 데이터 누수가 생기지 않습니다.
    months = monthly['year_month'].astype(str).tolist()
    visitors = monthly['visitors'].astype(float).tolist()
    spending = monthly['spending_krw'].astype(float).tolist()
    rows: list[list[float]] = []
    visitor_targets: list[float] = []
    spending_targets: list[float] = []
    target_months: list[str] = []
    visitor_baseline: list[float] = []
    spending_baseline: list[float] = []
    for index in range(12, len(months)):
        rows.append(_feature_row(visitors[:index], spending[:index], months[index]))
        visitor_targets.append(visitors[index])
        spending_targets.append(spending[index])
        target_months.append(months[index])
        # 계절 단순 기준선: 작년 같은 달의 실제 값입니다.
        visitor_baseline.append(visitors[index - 12])
        spending_baseline.append(spending[index - 12])
    return (
        np.asarray(rows), np.asarray(visitor_targets), np.asarray(spending_targets), target_months,
        np.asarray(visitor_baseline), np.asarray(spending_baseline),
    )


def make_lodging_supervised_frame(monthly: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """숙박일 장기 시계열을 시간순 검증용 지도학습 표로 변환합니다."""
    months = monthly['year_month'].astype(str).tolist()
    lodging_nights = monthly['lodging_nights'].astype(float).tolist()
    rows: list[list[float]] = []
    targets: list[float] = []
    baseline: list[float] = []
    for index in range(12, len(months)):
        rows.append(_lodging_feature_row(lodging_nights[:index], months[index]))
        targets.append(lodging_nights[index])
        baseline.append(lodging_nights[index - 12])
    return np.asarray(rows), np.asarray(targets), np.asarray(baseline)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """모델과 기준선을 같은 MAE/RMSE로 비교해 선택 근거를 남깁니다."""
    # MAE는 실제 단위 오차, RMSE는 큰 오차에 더 민감한 지표, MAPE는 상대 오차입니다.
    return {
        'mae': round(float(mean_absolute_error(actual, predicted)), 2),
        'rmse': round(float(mean_squared_error(actual, predicted) ** 0.5), 2),
        'mape_percent': round(float(np.mean(np.abs((actual - predicted) / actual)) * 100), 2),
    }


def train_gangnam_models() -> dict[str, Any]:
    """시간순 마지막 4개월로 평가한 뒤, 검증을 통과한 두 모델을 저장합니다.

    방문자 수는 랜덤 포리스트, 소비액은 선형회귀를 후보와 기준선으로 비교해
    선택했습니다. 학습은 HTTP 요청이 아니라 이 명시적 함수에서만 발생합니다.
    """
    # 1) 원본 ZIP 파싱·전처리 → 2) 시간순 평가 → 3) 전체 데이터 최종 학습 → 4) artifact 저장 순서입니다.
    monthly = write_processed_dataset()
    features, visitors, spending, target_months, visitor_baseline, spending_baseline = make_supervised_frame(monthly)
    lodging_features, lodging_targets, lodging_baseline = make_lodging_supervised_frame(monthly)
    if len(target_months) < 16:
        raise ValueError('시간순 평가에는 지도학습 행이 16개 이상 필요합니다.')

    # 가장 최근 4개월은 한 번도 학습에 보이지 않는 테스트 구간입니다.
    split_index = len(target_months) - 4
    train_x, test_x = features[:split_index], features[split_index:]
    train_visitors, test_visitors = visitors[:split_index], visitors[split_index:]
    train_spending, test_spending = spending[:split_index], spending[split_index:]

    # 방문자 수는 계절성과 비선형 변화를 반영하기 위해 Random Forest를 후보로 사용합니다.
    visitor_model = RandomForestRegressor(
        n_estimators=300, max_depth=3, min_samples_leaf=2, random_state=42,
    )
    # 소비액은 현재 작은 표본에서 표준화보다 원 단위 선형회귀의 테스트 오차가 낮았습니다.
    spending_model = LinearRegression()
    visitor_model.fit(train_x, train_visitors)
    spending_model.fit(train_x, train_spending)

    visitor_model_metrics = _metrics(test_visitors, visitor_model.predict(test_x))
    spending_model_metrics = _metrics(test_spending, spending_model.predict(test_x))
    visitor_baseline_metrics = _metrics(test_visitors, visitor_baseline[split_index:])
    spending_baseline_metrics = _metrics(test_spending, spending_baseline[split_index:])
    if visitor_model_metrics['mae'] >= visitor_baseline_metrics['mae']:
        raise ValueError('방문자 모델이 계절 기준선보다 낮은 오차를 보이지 않아 저장하지 않았습니다.')
    if spending_model_metrics['mae'] >= spending_baseline_metrics['mae']:
        raise ValueError('소비액 모델이 계절 기준선보다 낮은 오차를 보이지 않아 저장하지 않았습니다.')

    # 숙박일은 변동이 작으므로 선형 모델과 계절 기준선을 반드시 비교합니다.
    lodging_model = LinearRegression().fit(lodging_features[:split_index], lodging_targets[:split_index])
    lodging_model_metrics = _metrics(lodging_targets[split_index:], lodging_model.predict(lodging_features[split_index:]))
    lodging_baseline_metrics = _metrics(lodging_targets[split_index:], lodging_baseline[split_index:])
    # 숙박일은 변동 폭이 작아, 모델이 기준선보다 나쁠 때 전년 동월 기준선을 사용합니다.
    use_lodging_model = lodging_model_metrics['mae'] < lodging_baseline_metrics['mae']

    # 화면 예측에는 평가용 모델이 아니라, 전체 과거 자료를 다시 학습한 최종 모델을 사용합니다.
    final_visitor_model = RandomForestRegressor(
        n_estimators=300, max_depth=3, min_samples_leaf=2, random_state=42,
    ).fit(features, visitors)
    final_spending_model = LinearRegression().fit(features, spending)
    final_lodging_model = LinearRegression().fit(lodging_features, lodging_targets) if use_lodging_model else None
    artifact = {
        'version': MODEL_VERSION,
        'feature_names': FEATURE_NAMES,
        'visitor_model': final_visitor_model,
        'spending_model': final_spending_model,
        'lodging_model': final_lodging_model,
        'lodging_forecast_method': 'LinearRegression' if use_lodging_model else 'seasonal_naive_previous_year_same_month',
        'latest_observed_month': monthly['year_month'].iloc[-1],
    }
    metadata = {
        'version': MODEL_VERSION,
        'region_code': '11680',
        'region_name': '서울특별시 강남구',
        'target': {
            'visitors': '월간 외지인 순 방문자 수',
            'spending_krw': '월간 외지인 관광소비액(원)',
            'lodging_nights': '월간 평균 숙박일수(일)',
        },
        'source_period': f"{monthly['year_month'].iloc[0]}~{monthly['year_month'].iloc[-1]}",
        'feature_names': list(FEATURE_NAMES),
        'test_period': f'{target_months[split_index]}~{target_months[-1]}',
        'baseline': 'seasonal_naive_previous_year_same_month',
        'evaluation': {
            'visitors': {'selected_model': 'RandomForestRegressor', 'selected_model_metrics': visitor_model_metrics, 'baseline_metrics': visitor_baseline_metrics},
            'spending_krw': {'selected_model': 'LinearRegression', 'selected_model_metrics': spending_model_metrics, 'baseline_metrics': spending_baseline_metrics},
            'lodging_nights': {'selected_model': 'LinearRegression' if use_lodging_model else 'seasonal_naive_previous_year_same_month', 'selected_model_metrics': lodging_model_metrics if use_lodging_model else lodging_baseline_metrics, 'baseline_metrics': lodging_baseline_metrics},
        },
        'limitations': [
            '강남구 한 지역의 31개월 관측값으로 학습한 초기 모델입니다.',
            '예측은 자연 추세 추정이며, 정책 실행 효과나 매출 증가의 인과관계를 뜻하지 않습니다.',
            '업종별 예상 소비 패턴은 최신 관측월 업종 비중을 유지한다는 별도 가정으로 계산합니다.',
        ],
    }
    # joblib에는 학습된 모델 객체를, JSON에는 사람이 읽을 평가 결과를 저장합니다.
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata


def _load_artifact() -> tuple[dict[str, Any], dict[str, Any]]:
    """온라인 API는 저장된 산출물만 읽습니다. 없으면 학습을 몰래 실행하지 않고 오류를 냅니다."""
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        raise FileNotFoundError('예측 모델이 아직 없습니다. python -m ai_server.ml.train_gangnam 을 먼저 실행하세요.')
    return joblib.load(MODEL_PATH), json.loads(METADATA_PATH.read_text(encoding='utf-8'))


def predict_future_months(horizon: int = 4) -> dict[str, Any]:
    """최신 관측값 뒤 지정한 개월 수만큼 재귀 예측합니다.

    현재 달이 바뀌어도 다음 달부터 3개월을 보여 주기 위해, API가 필요한 만큼의
    중간 월 예측을 요청합니다. 중간 예측값은 다음 달 피처로만 쓰일 수 있습니다.
    """
    if horizon < 3 or horizon > 24:
        raise ValueError('예측 기간은 3개월 이상 24개월 이하여야 합니다.')
    # 서비스 시점에는 fit을 다시 하지 않고 저장 모델만 로드해 응답 시간을 일정하게 유지합니다.
    artifact, metadata = _load_artifact()
    monthly = load_gangnam_monthly_demand()
    months = monthly['year_month'].astype(str).tolist()
    visitors = monthly['visitors'].astype(float).tolist()
    spending = monthly['spending_krw'].astype(float).tolist()
    lodging_nights = monthly['lodging_nights'].astype(float).tolist()
    forecasts: list[dict[str, Any]] = []
    # 첫 예측 뒤에는 그 예측값을 다음 달 lag에 넣는 재귀 방식입니다.
    for _ in range(horizon):
        target_month = _next_month(months[-1])
        features = np.asarray(_feature_row(visitors, spending, target_month)).reshape(1, -1)
        predicted_visitors = max(0, round(float(artifact['visitor_model'].predict(features)[0])))
        predicted_spending = max(0, round(float(artifact['spending_model'].predict(features)[0])))
        if artifact.get('lodging_model') is None:
            predicted_lodging_nights = lodging_nights[-12]
        else:
            lodging_features = np.asarray(_lodging_feature_row(lodging_nights, target_month)).reshape(1, -1)
            predicted_lodging_nights = max(0, round(float(artifact['lodging_model'].predict(lodging_features)[0]), 2))
        forecasts.append({
            'month': target_month,
            'visitors': predicted_visitors,
            'spending_krw': predicted_spending,
            'lodging_nights': predicted_lodging_nights,
            'is_forecast': True,
        })
        # 2·3개월 차 예측에는 아직 관측되지 않은 직전 월 대신 1개월 차 예측값을 사용합니다.
        months.append(target_month)
        visitors.append(predicted_visitors)
        spending.append(predicted_spending)
        lodging_nights.append(predicted_lodging_nights)
    return {
        'latest_observed_month': monthly['year_month'].iloc[-1],
        'latest_observed_visitors': round(monthly['visitors'].iloc[-1]),
        'latest_observed_spending_krw': round(monthly['spending_krw'].iloc[-1]),
        'latest_observed_lodging_nights': round(float(monthly['lodging_nights'].iloc[-1]), 2),
        # 차트에는 최근 3개월 관측값과 이후 3개월 예측값을 나란히 표시합니다.
        'recent_actuals': [
            {
                'month': str(row.year_month),
                'visitors': round(float(row.visitors)),
                'spending_krw': round(float(row.spending_krw)),
                'lodging_nights': round(float(row.lodging_nights), 2),
                'is_forecast': False,
            }
            for row in monthly.tail(3).itertuples(index=False)
        ],
        'forecasts': forecasts,
        'model': metadata,
    }


def predict_next_three_months() -> dict[str, Any]:
    """기존 호출부 호환용 3개월 예측 함수입니다. 새 화면은 predict_future_months를 사용합니다."""
    return predict_future_months(3)
