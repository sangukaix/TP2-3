"""네 가지 모델군을 하나의 joblib에 저장합니다.

실행:
python -m ai_server.ml.train_gangnam_model_switch_002
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor

from .evaluation import BASELINE, TEST_MONTHS, VALIDATION_MONTHS, error_metrics, is_better_by_priority
from .gangnam_data import load_gangnam_monthly_demand
from .gangnam_forecast import ARTIFACT_DIRECTORY, _training_frame
from .validation import TARGETS, data_fingerprint

# 통합 모델의 최종 파일명입니다.
OUTPUT_MODEL = ARTIFACT_DIRECTORY / "demand_model.joblib"
OUTPUT_META = ARTIFACT_DIRECTORY / "demand_model.metadata.json"


def _factory(target: str, family: str):
    # 비교 화면에서 네 알고리즘을 각각 독립적으로 확인할 수 있도록
    # target 종류와 관계없이 선택한 알고리즘을 그대로 사용합니다.
    if family == "linear_regression":
        return LinearRegression
    if family == "random_forest":
        return lambda: RandomForestRegressor(n_estimators=300, max_depth=3, min_samples_leaf=2, random_state=42)
    if family == "boosting":
        return lambda: GradientBoostingRegressor(n_estimators=200, learning_rate=0.05, max_depth=2, min_samples_leaf=2, random_state=42)
    if family == "xgboost":
        return lambda: XGBRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, objective="reg:squarederror", random_state=42, n_jobs=1, verbosity=0)
    raise ValueError(f"알 수 없는 모델 계열: {family}")


def _train_one(frame, target: str, family: str):
    features, targets, baseline, _ = _training_frame(frame, target)
    test_start = len(targets) - TEST_MONTHS
    validation_start = test_start - VALIDATION_MONTHS
    factory = _factory(target, family)
    validation_model = factory().fit(features[:validation_start], targets[:validation_start])
    validation_pred = np.maximum(0, validation_model.predict(features[validation_start:test_start]))
    candidate_validation = error_metrics(targets[validation_start:test_start], validation_pred)
    baseline_validation = error_metrics(targets[validation_start:test_start], baseline[validation_start:test_start])
    test_model = factory().fit(features[:test_start], targets[:test_start])
    candidate_test = error_metrics(targets[test_start:], np.maximum(0, test_model.predict(features[test_start:])))
    baseline_test = error_metrics(targets[test_start:], baseline[test_start:])
    final_model = factory().fit(features, targets)
    # 최종 선택 기준: 검증 R²(1에 가까운 순서) → RMSE → MSE → MAE입니다.
    selected = type(test_model).__name__ if is_better_by_priority(candidate_validation, baseline_validation) else BASELINE
    return final_model, {
        'selected_model': selected,
        'selection_basis': 'validation_r2_then_rmse_mse_mae',
        'validation': {'candidate': candidate_validation, 'baseline': baseline_validation},
        'candidate_test_metrics': candidate_test,
        'selected_model_metrics': candidate_test if selected != BASELINE else baseline_test,
        'baseline_metrics': baseline_test,
        # 테스트 구간에서 후보 알고리즘과 기준선을 비교한 결과입니다.
        'candidate_beats_baseline_on_test': candidate_test['mae'] < baseline_test['mae'],
        'selected_is_baseline': selected == BASELINE,
        'beats_baseline_on_test': candidate_test['mae'] < baseline_test['mae'],
        'train_target_count': validation_start,
    }


def train() -> dict:
    frame = load_gangnam_monthly_demand()
    models_by_family = {}
    evaluation_by_family = {}
    for family in ("linear_regression", "random_forest", "boosting", "xgboost"):
        models_by_family[family] = {}
        evaluation_by_family[family] = {}
        for target in TARGETS:
            models_by_family[family][target], evaluation_by_family[family][target] = _train_one(frame, target, family)

    artifact = {
        'version': 'demand-v3.0-switch-002',
        'region_code': '11680',
        'data_fingerprint': data_fingerprint(frame),
        'models': models_by_family['random_forest'],
        'models_by_family': models_by_family,
        'active_model_family': 'random_forest',
    }
    metadata = {
        'version': artifact['version'],
        'region_code': '11680',
        'source_period': f"{frame['year_month'].iloc[0]}~{frame['year_month'].iloc[-1]}",
        'model_families': ('linear_regression', 'random_forest', 'boosting', 'xgboost'),
        'active_model_family': 'random_forest',
        # 기존 train_gangnam.py가 사용하는 호환 필드입니다.
        'evaluation': evaluation_by_family['random_forest'],
        'target': {target: target for target in TARGETS},
        'test_period': 'see evaluation test metrics',
        'evaluation_by_family': evaluation_by_family,
    }
    OUTPUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, OUTPUT_MODEL)
    OUTPUT_META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata


def train_gangnam_models() -> dict:
    """기존 CLI·외부 코드와 같은 함수명으로 통합 학습을 실행합니다."""
    return train()


def main() -> None:
    metadata = train_gangnam_models()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
