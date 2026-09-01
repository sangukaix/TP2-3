"""전국 지역 panel 데이터로 다음 달 방문자 수 모델을 학습·평가한다.

웹 요청에서는 이 파일을 실행하지 않는다. 시간순 검증에서 seasonal-naive보다
나은 후보만 저장하며, 데이터 코드 승인 전 결과는 experimental로 표시한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


TARGET = "visitors"
CATEGORICAL_FEATURES = ["region_code"]
NUMERIC_FEATURES = [
    "target_month_sin",
    "target_month_cos",
    "visitors_lag1",
    "visitors_lag2",
    "visitors_lag3",
    "visitors_lag12",
    "visitors_lag13",
    "visitors_yoy_ratio_lag1",
    "visitors_rolling3",
    "domestic_tourism_spend_lag1",
    "nonlocal_tourism_spend_lag1",
    "overnight_ratio_lag1",
    "avg_stay_days_lag1",
    "avg_stay_minutes_lag1",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


# 학습 데이터 파일도 hash로 고정해 같은 모델을 재현할 수 있게 한다.
def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


# MAPE는 실제값 0에서 정의되지 않으므로 0을 제외한 표본 수를 함께 반환한다.
def calculate_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    nonzero = actual_array != 0
    mape = (
        float(np.mean(np.abs((actual_array[nonzero] - predicted_array[nonzero]) / actual_array[nonzero])) * 100)
        if nonzero.any()
        else math.nan
    )
    return {
        "mae": float(mean_absolute_error(actual_array, predicted_array)),
        "rmse": float(mean_squared_error(actual_array, predicted_array) ** 0.5),
        "mape_pct": mape,
        "mape_sample_count": int(nonzero.sum()),
        "sample_count": int(len(actual_array)),
    }


# 예측 월의 값은 쓰지 않고 직전 월까지 이용 가능한 lag만 feature로 만든다.
def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["year_month"] = pd.to_datetime(data["year_month"], format="%Y-%m")
    numeric_sources = [
        "visitors",
        "domestic_tourism_spend_thousand_krw",
        "nonlocal_tourism_spend_thousand_krw",
        "overnight_ratio_pct",
        "avg_stay_days",
        "avg_stay_minutes",
    ]
    for column in numeric_sources:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.sort_values(["region_code", "year_month"]).reset_index(drop=True)
    grouped = data.groupby("region_code", sort=False)

    for lag in (1, 2, 3, 12, 13):
        data[f"visitors_lag{lag}"] = grouped["visitors"].shift(lag)
    data["visitors_yoy_ratio_lag1"] = (
        data["visitors_lag1"] / data["visitors_lag13"].replace(0, np.nan)
    )
    data["visitors_rolling3"] = grouped["visitors"].transform(
        lambda series: series.shift(1).rolling(3, min_periods=3).mean()
    )
    data["domestic_tourism_spend_lag1"] = grouped[
        "domestic_tourism_spend_thousand_krw"
    ].shift(1)
    data["nonlocal_tourism_spend_lag1"] = grouped[
        "nonlocal_tourism_spend_thousand_krw"
    ].shift(1)
    data["overnight_ratio_lag1"] = grouped["overnight_ratio_pct"].shift(1)
    data["avg_stay_days_lag1"] = grouped["avg_stay_days"].shift(1)
    data["avg_stay_minutes_lag1"] = grouped["avg_stay_minutes"].shift(1)
    month_number = data["year_month"].dt.month
    data["target_month_sin"] = np.sin(2 * np.pi * month_number / 12)
    data["target_month_cos"] = np.cos(2 * np.pi * month_number / 12)

    # seasonal-naive와 모든 후보가 같은 표본에서 평가되도록 lag12 필수 행만 남긴다.
    return data.dropna(
        subset=[
            TARGET,
            "visitors_lag1",
            "visitors_lag2",
            "visitors_lag3",
            "visitors_lag12",
            "visitors_lag13",
            "visitors_yoy_ratio_lag1",
            "visitors_rolling3",
        ]
    )


# 인코더·결측 처리도 모델과 함께 저장해 온라인 예측의 전처리 차이를 막는다.
def make_pipeline(model: object) -> Pipeline:
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessor = ColumnTransformer(
        [
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def select_operational_model(
    evaluations: dict[str, dict[str, dict[str, float | int]]]
) -> tuple[str, str, str, bool, bool]:
    """validation으로 후보를 고른 뒤 test 실패 시 사전 기준선으로 안전 복귀한다."""

    baseline_validation_mae = float(evaluations["seasonal_naive"]["validation"]["mae"])
    baseline_test_mae = float(evaluations["seasonal_naive"]["test"]["mae"])
    candidate_names = [name for name in evaluations if name != "seasonal_naive"]
    best_candidate = min(
        candidate_names,
        key=lambda name: float(evaluations[name]["validation"]["mae"]),
    )
    beats_validation = (
        float(evaluations[best_candidate]["validation"]["mae"])
        < baseline_validation_mae
    )
    beats_test = float(evaluations[best_candidate]["test"]["mae"]) < baseline_test_mae
    if beats_validation and beats_test:
        return best_candidate, best_candidate, "experimental", True, True
    # test를 보고 다른 복잡한 후보로 갈아타지 않는다. 미리 정한 계절 기준선만 허용한다.
    return best_candidate, "seasonal_naive", "baseline_only", beats_validation, beats_test


def train_and_save(input_csv: Path, artifact_root: Path) -> dict[str, object]:
    """시간순 baseline 비교 후 선택 모델과 모든 평가 근거를 저장한다."""

    raw = pd.read_csv(input_csv, dtype={"region_code": str, "year_month": str})
    data = build_features(raw)

    train = data[data["year_month"] <= "2025-06-01"]
    validation = data[(data["year_month"] >= "2025-07-01") & (data["year_month"] <= "2025-12-01")]
    test = data[(data["year_month"] >= "2026-01-01") & (data["year_month"] <= "2026-06-01")]
    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError("고정된 시간순 train/validation/test 구간에 필요한 행이 없습니다.")

    baseline_validation = calculate_metrics(validation[TARGET], validation["visitors_lag12"])
    baseline_test = calculate_metrics(test[TARGET], test["visitors_lag12"])
    candidates = {
        "linear_regression": (make_pipeline(LinearRegression()), "direct"),
        "linear_seasonal_residual": (make_pipeline(LinearRegression()), "seasonal_residual"),
        "linear_log_seasonal_ratio": (make_pipeline(LinearRegression()), "log_seasonal_ratio"),
        "random_forest": (
            make_pipeline(
                RandomForestRegressor(
                    n_estimators=300,
                    min_samples_leaf=3,
                    random_state=42,
                    n_jobs=-1,
                )
            ),
            "direct",
        ),
        "random_forest_seasonal_residual": (
            make_pipeline(
                RandomForestRegressor(
                    n_estimators=300,
                    min_samples_leaf=3,
                    random_state=42,
                    n_jobs=-1,
                )
            ),
            "seasonal_residual",
        ),
        "random_forest_log_seasonal_ratio": (
            make_pipeline(
                RandomForestRegressor(
                    n_estimators=300,
                    min_samples_leaf=3,
                    random_state=42,
                    n_jobs=-1,
                )
            ),
            "log_seasonal_ratio",
        ),
    }

    evaluations: dict[str, dict[str, dict[str, float | int]]] = {
        "seasonal_naive": {"validation": baseline_validation, "test": baseline_test},
        "recent_naive": {
            "validation": calculate_metrics(validation[TARGET], validation["visitors_lag1"]),
            "test": calculate_metrics(test[TARGET], test["visitors_lag1"]),
        },
        "seasonal_recent_blend": {
            "validation": calculate_metrics(
                validation[TARGET], 0.75 * validation["visitors_lag12"] + 0.25 * validation["visitors_lag1"]
            ),
            "test": calculate_metrics(
                test[TARGET], 0.75 * test["visitors_lag12"] + 0.25 * test["visitors_lag1"]
            ),
        },
        "yoy_rate_naive": {
            "validation": calculate_metrics(
                validation[TARGET],
                validation["visitors_lag12"]
                * validation["visitors_yoy_ratio_lag1"].clip(lower=0.5, upper=1.5),
            ),
            "test": calculate_metrics(
                test[TARGET],
                test["visitors_lag12"]
                * test["visitors_yoy_ratio_lag1"].clip(lower=0.5, upper=1.5),
            ),
        },
    }
    fitted: dict[str, Pipeline] = {}
    prediction_modes: dict[str, str] = {}
    for name, (pipeline, prediction_mode) in candidates.items():
        training_target = (
            train[TARGET] - train["visitors_lag12"]
            if prediction_mode == "seasonal_residual"
            else (
                np.log1p(train[TARGET]) - np.log1p(train["visitors_lag12"])
                if prediction_mode == "log_seasonal_ratio"
                else train[TARGET]
            )
        )
        pipeline.fit(train[FEATURES], training_target)
        fitted[name] = pipeline
        prediction_modes[name] = prediction_mode

        def predict(split: pd.DataFrame) -> np.ndarray:
            raw_prediction = pipeline.predict(split[FEATURES])
            if prediction_mode == "seasonal_residual":
                return np.maximum(0, split["visitors_lag12"].to_numpy() + raw_prediction)
            if prediction_mode == "log_seasonal_ratio":
                return np.maximum(
                    0,
                    np.expm1(np.log1p(split["visitors_lag12"].to_numpy()) + raw_prediction),
                )
            return np.maximum(0, raw_prediction)

        evaluations[name] = {
            "validation": calculate_metrics(validation[TARGET], predict(validation)),
            "test": calculate_metrics(test[TARGET], predict(test)),
        }

    (
        candidate_name,
        selected_name,
        decision_status,
        beats_baseline,
        beats_baseline_on_test,
    ) = select_operational_model(evaluations)

    version = datetime.now(timezone.utc).strftime("visitors-panel-%Y%m%dT%H%M%SZ")
    output_dir = artifact_root / version
    output_dir.mkdir(parents=True, exist_ok=False)
    artifact_payload = {
        "pipeline": fitted.get(selected_name),
        "prediction_mode": prediction_modes.get(selected_name, selected_name),
        "fallback": "visitors_lag12" if selected_name == "seasonal_naive" else None,
        "features": FEATURES,
        "target": TARGET,
        "model_name": selected_name,
    }
    artifact_path = output_dir / "model.joblib"
    joblib.dump(artifact_payload, artifact_path)

    data_hash = sha256_file(input_csv)
    artifact_hash = sha256_file(artifact_path)
    evaluation_payload = {
        "split": {
            "train": {"start": "2025-02", "end": "2025-06", "rows": len(train)},
            "validation": {"start": "2025-07", "end": "2025-12", "rows": len(validation)},
            "test": {"start": "2026-01", "end": "2026-06", "rows": len(test)},
        },
        "models": evaluations,
        "selection_metric": "validation_mae",
        "selection_candidate_model": candidate_name,
        "operational_model": selected_name,
        "beats_seasonal_naive_on_validation": beats_baseline,
        "beats_seasonal_naive_on_test": beats_baseline_on_test,
    }
    metadata = {
        "model_version": version,
        "target": "next_month_visitors",
        "model_name": selected_name,
        "selection_candidate_model": candidate_name,
        "decision_status": decision_status,
        "artifact_file": "model.joblib",
        "artifact_sha256": artifact_hash,
        "training_start_month": "2025-02",
        "training_end_month": "2025-06",
        "supported_region_count": int(data["region_code"].nunique()),
        "feature_count": len(FEATURES),
        "limitations": [
            "지역코드는 2026-02-01 시행 행정안전부 법정동 코드와 Data Lab 내부 코드를 교차 검증함",
            "테스트 기간이 6개월이므로 장기 일반화 성능을 보장하지 않음",
            "예측값은 인과 효과나 사업 성과 보장값이 아님",
        ],
        "libraries": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    training_manifest = {
        "input_file": input_csv.name,
        "input_sha256": data_hash,
        "input_rows": len(raw),
        "feature_rows": len(data),
        "region_count": int(data["region_code"].nunique()),
        "time_split": evaluation_payload["split"],
        "random_seed": 42,
    }
    feature_schema = {
        "target": TARGET,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "prediction_contract": "target 월 직전까지 공개된 값만 사용",
    }

    for file_name, payload in (
        ("metadata.json", metadata),
        ("metrics.json", evaluation_payload),
        ("training_data_manifest.json", training_manifest),
        ("feature_schema.json", feature_schema),
    ):
        (output_dir / file_name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {
        "artifact_dir": str(output_dir),
        "model_version": version,
        "selected_model": selected_name,
        "selection_candidate_model": candidate_name,
        "decision_status": decision_status,
        "beats_seasonal_naive_on_validation": beats_baseline,
        "beats_seasonal_naive_on_test": beats_baseline_on_test,
        "validation_mae": evaluations[selected_name]["validation"]["mae"],
        "baseline_validation_mae": baseline_validation["mae"],
        "test_mae": evaluations[selected_name]["test"]["mae"],
        "baseline_test_mae": baseline_test["mae"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="다음 달 방문자 panel 모델 학습")
    parser.add_argument(
        "--input-csv",
        default="data/processed/merged_nationwide_staging/tourism_monthly_staging.csv",
    )
    parser.add_argument(
        "--artifact-root",
        default="artifacts/models/next_month_visitors_merged",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_csv = Path(args.input_csv)
    if not input_csv.is_file():
        print(f"오류: staging 파일을 찾을 수 없습니다: {input_csv}", file=sys.stderr)
        return 2
    result = train_and_save(input_csv, Path(args.artifact_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
