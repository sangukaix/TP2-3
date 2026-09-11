"""demand_model_switch_002.joblib을 읽는 별도 예측 로더입니다."""
from __future__ import annotations

import json

import joblib

from .gangnam_data import load_gangnam_monthly_demand
from .gangnam_forecast import ARTIFACT_DIRECTORY, _model_inputs, _next_month, _round_prediction
from .model_switch_002 import get_active_model_family
from .validation import TARGETS

MODEL_PATH = ARTIFACT_DIRECTORY / "demand_model.joblib"
METADATA_PATH = ARTIFACT_DIRECTORY / "demand_model.metadata.json"


def predict_region_demand(region_code: str, horizon: int = 3) -> dict:
    if str(region_code) != '11680':
        raise ValueError('현재 switch 로더는 강남구(11680)만 지원합니다.')
    if horizon < 1 or horizon > 24:
        raise ValueError('horizon은 1~24 범위여야 합니다.')
    artifact = joblib.load(MODEL_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    family = get_active_model_family()
    models = artifact['models_by_family'][family]
    monthly = load_gangnam_monthly_demand()
    histories = {target: monthly[target].astype(float).tolist() for target in TARGETS}
    months = monthly['year_month'].astype(str).tolist()
    forecasts = []
    for _ in range(horizon):
        month = _next_month(months[-1])
        row = {'month': month, 'is_forecast': True}
        for target in TARGETS:
            value = float(models[target].predict(_model_inputs(histories, target, month))[0])
            row[target] = _round_prediction(target, max(0.0, value))
        for target in TARGETS:
            histories[target].append(float(row[target]))
        months.append(month)
        forecasts.append(row)
    latest = monthly.iloc[-1]
    recent_actuals = []
    for row_data in monthly.tail(3).itertuples(index=False):
        actual = {'month': str(row_data.year_month), 'is_forecast': False}
        for target in TARGETS:
            actual[target] = _round_prediction(target, float(getattr(row_data, target)))
        recent_actuals.append(actual)
    return {
        'latest_observed_month': str(latest['year_month']),
        'latest_observed_visitors': _round_prediction('visitors', float(latest['visitors'])),
        'latest_observed_spending_krw': _round_prediction('spending_krw', float(latest['spending_krw'])),
        'latest_observed_lodging_nights': _round_prediction('lodging_nights', float(latest['lodging_nights'])),
        'latest_observed_metrics': {target: float(latest[target]) for target in TARGETS},
        'recent_actuals': recent_actuals,
        'forecasts': forecasts,
        # 대시보드·기획서가 사용하는 평가/학습 메타데이터도 함께 반환합니다.
        'model': {
            **metadata,
            'version': metadata.get('version', artifact.get('version', '')),
            'active_model_family': family,
            'limitations': metadata.get('limitations', ['통합 모델 비교용 초기 모델입니다.']),
        },
    }


def train_region_demand(region_code: str) -> dict:
    """기존 서비스 계약을 유지합니다. 통합 학습은 전용 CLI에서 실행합니다."""
    if str(region_code) == '11680':
        from .train_gangnam_model_switch_002 import train_gangnam_models
        return train_gangnam_models()
    from .region_registry import get_region_pipeline
    return get_region_pipeline(region_code).train()
