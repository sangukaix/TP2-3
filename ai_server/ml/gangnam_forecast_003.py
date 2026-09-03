"""초보자가 읽기 쉽도록 정리한 독립적인 강남구 예측 모듈입니다.

다른 forecast 파일을 import하지 않습니다.
따라서 이 파일 안에서 데이터 준비, 학습, 평가, 예측 과정을 확인할 수 있습니다.
"""

# gangnam_forecast_002.py
# 함수 저장 방식을 초보자 수준으로 표현한 독립 버전입니다.
# gangnam_forecast_003.py으로 변경


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

from .evaluation import (
    BASELINE,
    TEST_MONTHS,
    VALIDATION_MONTHS,
    error_metrics,
    select_and_evaluate,
)
from .gangnam_data import (
    PROJECT_ROOT,
    REGION_CODE,
    load_gangnam_monthly_demand,
    write_processed_dataset,
)
from .validation import TARGETS, data_fingerprint


# 모델 파일을 저장할 위치입니다.
ARTIFACT_DIRECTORY = PROJECT_ROOT / "artifacts" / "ml" / REGION_CODE
MODEL_PATH = ARTIFACT_DIRECTORY / "demand_model.joblib"
METADATA_PATH = ARTIFACT_DIRECTORY / "demand_model.metadata.json"
MODEL_VERSION = "demand-v3.0"

# 방문자 수와 소비액 모델이 사용하는 입력값의 이름입니다.
FEATURE_NAMES = (
    "visitors_lag_1",
    "visitors_lag_3",
    "visitors_lag_12",
    "spending_lag_1",
    "spending_lag_3",
    "spending_lag_12",
    "month_sin",
    "month_cos",
)

TARGET_LABELS = {
    "visitors": "월간 외지인 순 방문자 수",
    "spending_krw": "월간 외지인 관광소비액(원)",
    "lodging_nights": "월간 평균 숙박일수(일)",
    "lodging_rate_pct": "월간 숙박방문자 비율(%)",
    "stay_minutes": "월간 평균 체류시간(분)",
    "navigation_searches": "월간 내비게이션 목적지 검색량(건)",
    "lodging_searches": "월간 숙박 목적지 검색건수(건)",
}

# 이 지표들은 예측 결과를 정수로 반올림합니다.
COUNT_TARGETS = {
    "visitors",
    "spending_krw",
    "navigation_searches",
    "lodging_searches",
}


@dataclass(frozen=True)
class RegionForecastSettings:
    """한 지역의 데이터 함수와 모델 저장 위치를 모아 둔 설정입니다."""

    region_code: str
    region_name: str
    # 최신 월별 데이터를 읽는 함수입니다.
    load_monthly_function: Callable[[], pd.DataFrame]
    # 데이터를 전처리하고 DataFrame으로 반환하는 함수입니다.
    processed_data_function: Callable[[], pd.DataFrame]
    artifact_directory: Path
    model_version: str = MODEL_VERSION


def _univariate_feature_names(target_key: str) -> tuple[str, ...]:
    """지표 하나만 사용하는 모델의 입력값 이름을 만듭니다."""
    return (
        f"{target_key}_lag_1",
        f"{target_key}_lag_3",
        f"{target_key}_lag_12",
        "month_sin",
        "month_cos",
    )


FEATURE_NAMES_BY_TARGET = {}
for target_name in TARGETS:
    if target_name in {"visitors", "spending_krw"}:
        FEATURE_NAMES_BY_TARGET[target_name] = list(FEATURE_NAMES)
    else:
        FEATURE_NAMES_BY_TARGET[target_name] = list(
            _univariate_feature_names(target_name)
        )

LODGING_FEATURE_NAMES = tuple(FEATURE_NAMES_BY_TARGET["lodging_nights"])


def _next_month(year_month: str) -> str:
    """YYYYMM 형식의 월을 받아 다음 달을 YYYYMM 형식으로 반환합니다."""
    year = int(year_month[:4])
    month = int(year_month[4:])
    month += 1

    if month == 13:
        year += 1
        month = 1

    return f"{year}{month:02d}"


def _season_features(target_month: str) -> list[float]:
    """월 정보를 계절성 입력값인 sin과 cos으로 바꿉니다."""
    month_number = int(target_month[4:])
    angle = 2 * pi * month_number / 12
    month_sin = sin(angle)
    month_cos = cos(angle)
    return [month_sin, month_cos]


def _feature_row(
    visitors: list[float],
    spending: list[float],
    target_month: str,
) -> list[float]:
    """방문자와 소비액의 과거값으로 한 줄의 입력값을 만듭니다."""
    if len(visitors) < 12 or len(spending) < 12:
        raise ValueError("12개월 이상의 과거 관측값이 필요합니다.")

    visitor_1_month_ago = visitors[-1]
    visitor_3_months_ago = visitors[-3]
    visitor_12_months_ago = visitors[-12]
    spending_1_month_ago = spending[-1]
    spending_3_months_ago = spending[-3]
    spending_12_months_ago = spending[-12]
    season_values = _season_features(target_month)

    return [
        visitor_1_month_ago,
        visitor_3_months_ago,
        visitor_12_months_ago,
        spending_1_month_ago,
        spending_3_months_ago,
        spending_12_months_ago,
        season_values[0],
        season_values[1],
    ]


def _univariate_feature_row(
    history: list[float],
    target_month: str,
) -> list[float]:
    """지표 하나의 과거값으로 한 줄의 입력값을 만듭니다."""

    print('_univariate_feature_row 함수 내부')
    if len(history) < 12:
        raise ValueError("12개월 이상의 과거 관측값이 필요합니다.")

    
    old_1_month = history[-1]
    print('과거 전 한달:',old_1_month)
    old_3_months = history[-3]
    print('과거 전 3달:',old_3_months)
    old_12_months = history[-12]
    print('과거 전 12달:',old_12_months)


    season_values = _season_features(target_month)
    print('_season_features(target_month) : ',season_values,'\n')

    return [
        old_1_month,
        old_3_months,
        old_12_months,
        season_values[0],
        season_values[1],
    ]


def make_supervised_frame(
    monthly: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], np.ndarray, np.ndarray]:
    """방문자·소비액의 과거값을 다음 달을 맞히는 학습표로 바꿉니다."""

    print('make_supervised_frame 함수 호출 in gangnam_forecast.py ')
    months = monthly["year_month"].astype(str).tolist()
    visitors = monthly["visitors"].astype(float).tolist()
    spending = monthly["spending_krw"].astype(float).tolist()

    features = []
    visitor_targets = []
    spending_targets = []
    target_months = []
    visitor_baseline = []
    spending_baseline = []

    # 처음 12개월은 과거 12개월을 만들기 위한 자료로만 사용합니다.
    for index in range(12, len(months)):
        feature = _feature_row(visitors[:index], spending[:index], months[index])
        features.append(feature)
        visitor_targets.append(visitors[index])
        spending_targets.append(spending[index])
        target_months.append(months[index])
        visitor_baseline.append(visitors[index - 12])
        spending_baseline.append(spending[index - 12])

    return (
        np.asarray(features),
        np.asarray(visitor_targets),
        np.asarray(spending_targets),
        target_months,
        np.asarray(visitor_baseline),
        np.asarray(spending_baseline),
    )


def make_univariate_supervised_frame(
    monthly: pd.DataFrame,
    target_key: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """하나의 지표를 과거값으로 예측하는 학습표를 만듭니다."""

    print('make_univariate_supervised_frame 내부')
    if target_key not in monthly.columns:
        raise ValueError(f"학습표에 {target_key} 열이 없습니다.")



    months = monthly["year_month"].astype(str).tolist()
    print('monthly["year_month"].astype(str).tolist()값\n',months,'\n')
    values = monthly[target_key].astype(float).tolist()
    print('monthly[target_key].astype(float).tolist()값\n',values,'\n')

    print('features, targets,baseline, target_months 초기화')
    features = []
    targets = []
    baseline = []
    target_months = []


    for index in range(12, len(months)):
        print('index:',index,'\n')
        feature = _univariate_feature_row(values[:index], months[index])
        print(feature,'\n')
        features.append(feature)
        print(features,'\n')
        targets.append(values[index])
        print(targets,'\n')
        baseline.append(values[index - 12])
        print(baseline,'\n')
        target_months.append(months[index])
        print(target_months,'\n')

    return (
        np.asarray(features),
        np.asarray(targets),
        np.asarray(baseline),
        target_months,
    )


def make_lodging_supervised_frame(
    monthly: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """기존 호출부를 위한 숙박일수 전용 함수입니다."""
    features, targets, baseline, unused_months = make_univariate_supervised_frame(
        monthly,
        "lodging_nights",
    )
    return features, targets, baseline


_metrics = error_metrics


def _random_forest() -> RandomForestRegressor:
    """랜덤 포레스트 모델을 같은 설정으로 만듭니다."""
    return RandomForestRegressor(
        n_estimators=300,
        max_depth=3,
        min_samples_leaf=2,
        random_state=42,
    )


def _factory_for(target_key: str) -> Callable[[], Any]:
    """지표에 맞는 모델을 반환합니다."""

    print('_factory_for 함수 호출 in gangnam_forecast.py\n')
    random_forest_targets = {
        "visitors",
        "navigation_searches",
        "lodging_searches",
    }
    print(random_forest_targets)

    if target_key in random_forest_targets:
        print("target_key:",target_key)
        return _random_forest

    print("LinearRegression 을 반환")
    print(LinearRegression,'\n')
    return LinearRegression


def _training_frame(
    monthly: pd.DataFrame,
    target_key: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """지표 종류에 맞는 학습용 입력값, 정답값, 기준선을 반환합니다."""

    print('_training_frame 호출한 내부\n\n ')


    shared_targets = {"visitors", "spending_krw"}

    if target_key in shared_targets:
        (
            features,
            visitor_targets,
            spending_targets,
            months,
            visitor_baseline,
            spending_baseline,
        ) = make_supervised_frame(monthly)
        print('make_supervised_frame(monthly)가 반환하는 6개의 값을 각각 변수에 나누어 저장하는 것\n')

        if target_key == "visitors":
            print('target_key가 visition인 경우:\n\n')
            print('target_key가 visitors이면 features, visitor_targets, visitor_baseline, months 를 출력 \n\n',features, visitor_targets, visitor_baseline, months)
            return features, visitor_targets, visitor_baseline, months

        print('최종 반환하는 features, spending_targets, spending_baseline, months 를 출력 \n\n',features, visitor_targets, visitor_baseline, months)
        return features, spending_targets, spending_baseline, months

    print('최종 반환된 파라미터로 출력한 make_univariate_supervised_frame(monthly, target_key) \n\n',make_univariate_supervised_frame(monthly, target_key))
    return make_univariate_supervised_frame(monthly, target_key)


def _model_inputs(
    histories: dict[str, list[float]],
    target_key: str,
    month: str,
) -> np.ndarray:
    """저장된 모델에 넣을 입력값을 2차원 배열로 만듭니다."""
    if target_key in {"visitors", "spending_krw"}:
        row = _feature_row(
            histories["visitors"],
            histories["spending_krw"],
            month,
        )
    else:
        row = _univariate_feature_row(histories[target_key], month)

    return np.asarray(row).reshape(1, -1)


def _round_prediction(target_key: str, value: float) -> float | int:
    """음수를 없애고 지표 단위에 맞게 반올림합니다."""
    value = max(0, value)

    if target_key in COUNT_TARGETS:
        return round(value)

    return round(value, 2)


def _recursive_forecasts(
    artifact: dict,
    monthly: pd.DataFrame,
    horizon: int,
) -> list[dict]:
    """예측한 값을 다음 달의 입력값으로 사용해 여러 달을 예측합니다."""
    months = monthly["year_month"].astype(str).tolist()

    # 각 지표의 과거값을 별도 리스트로 복사합니다.
    histories = {}
    for target_name in TARGETS:
        values = monthly[target_name].astype(float).tolist()
        histories[target_name] = values

    models = artifact.get("models")
    if not models:
        models = {
            "visitors": artifact.get("visitor_model"),
            "spending_krw": artifact.get("spending_model"),
            "lodging_nights": artifact.get("lodging_model"),
        }

    forecasts = []

    for step in range(horizon):
        next_month = _next_month(months[-1])
        forecast = {"month": next_month, "is_forecast": True}

        for target_name in TARGETS:
            model = models.get(target_name)

            if model is None:
                # 모델을 선택하지 않은 경우 전년 같은 달 값을 사용합니다.
                predicted_value = histories[target_name][-12]
            else:
                model_input = _model_inputs(histories, target_name, next_month)
                predicted_value = float(model.predict(model_input)[0])

            if not np.isfinite(predicted_value):
                raise ValueError("유한한 예측값을 만들지 못했습니다.")

            forecast[target_name] = _round_prediction(target_name, predicted_value)

        # 이번 달 예측값을 저장해 다음 달 예측에 사용할 수 있게 합니다.
        for target_name in TARGETS:
            histories[target_name].append(float(forecast[target_name]))

        months.append(next_month)
        forecasts.append(forecast)

    return forecasts


def _fit_selected_models(
    monthly: pd.DataFrame,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    """평가에서 선택된 지표 모델만 다시 학습합니다."""
    models = {}

    for target_name in TARGETS:
        selected_model = evaluation[target_name]["selected_model"]

        if selected_model == BASELINE:
            models[target_name] = None
            continue

        features, targets, unused_baseline, unused_months = _training_frame(
            monthly,
            target_name,
        )
        model_factory = _factory_for(target_name)
        models[target_name] = model_factory().fit(features, targets)

    return models


def _recursive_test(
    monthly: pd.DataFrame,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    """실제 미래값을 미리 사용하지 않고 1~3개월 예측을 시험합니다."""
    results = {}

    for target_name in TARGETS:
        results[target_name] = {}
        for horizon in range(1, 4):
            results[target_name][str(horizon)] = {
                "actual": [],
                "predicted": [],
                "baseline": [],
            }

    origins = []
    first_origin = len(monthly) - TEST_MONTHS
    last_origin = len(monthly) - 2

    for origin in range(first_origin, last_origin):
        history = monthly.iloc[:origin]
        selected_models = _fit_selected_models(history, evaluation)
        forecasts = _recursive_forecasts(
            {"models": selected_models},
            history,
            3,
        )
        origins.append(str(history["year_month"].iloc[-1]))

        for forecast_index, forecast in enumerate(forecasts):
            horizon = str(forecast_index + 1)

            for target_name in TARGETS:
                bucket = results[target_name][horizon]
                actual_value = monthly[target_name].iloc[origin + forecast_index]
                baseline_value = monthly[target_name].iloc[origin + forecast_index - 12]
                bucket["actual"].append(float(actual_value))
                bucket["predicted"].append(float(forecast[target_name]))
                bucket["baseline"].append(float(baseline_value))

    by_horizon = {}
    for target_name in TARGETS:
        by_horizon[target_name] = {}

        for horizon, values in results[target_name].items():
            selected_metrics = error_metrics(
                values["actual"],
                values["predicted"],
            )
            baseline_metrics = error_metrics(
                values["actual"],
                values["baseline"],
            )
            by_horizon[target_name][horizon] = {
                "selected": selected_metrics,
                "baseline": baseline_metrics,
            }

    return {
        "method": "rolling_origin_recursive_1_to_3_months",
        "origins": origins,
        "by_horizon": by_horizon,
    }


def train_region_models(settings: RegionForecastSettings) -> dict[str, Any]:
    """한 지역의 모든 지표를 학습하고 모델 파일을 저장합니다."""
    # 설정 상자에 저장해 둔 전처리 함수를 실행합니다.
    print('train_region_models in gangnam_forecast.py\n')

    print('processed_data_function in gangnam_forecast.py\n')

    

    print("processed_data_function 함수를 monthly 에 반영 in gangnam_forecast.py \n ")

    print('processed_data_function = write_processed_dataset() 함수를 실행하고, 그 함수가 반환한 결과를 monthly에 저장한다.')
    monthly = settings.processed_data_function()  
    print("monthly 값:" , monthly)
    evaluation = {}
    models = {}
    target_months = None

    print('Symbol : 00000000000')
    print(monthly,'\n',evaluation,'\n',target_months,'\n')

    for target_name in TARGETS:

        print("debug: target_name  : \n", target_name,'\n')


        features, targets, baseline, months = _training_frame(
            monthly,
            target_name,
        )

        print('features, targets, baseline, months 값 =  _training_frame( monthly, target_name,)\n',features,'\n', targets,'\n', baseline,'\n', months)


        model_factory = _factory_for(target_name)
        model, result = select_and_evaluate(
            features,
            targets,
            baseline,
            model_factory,
        )
        models[target_name] = model
        evaluation[target_name] = result

        if target_months is None:
            target_months = months

    fingerprint = data_fingerprint(monthly)
    artifact = {
        "version": settings.model_version,
        "region_code": settings.region_code,
        "data_fingerprint": fingerprint,
        "feature_names": FEATURE_NAMES,
        "models": models,
        "latest_observed_month": str(monthly["year_month"].iloc[-1]),
    }

    test_start = len(target_months) - TEST_MONTHS
    validation_start = test_start - VALIDATION_MONTHS
    recursive_evaluation = _recursive_test(monthly, evaluation)

    metadata = {
        "version": settings.model_version,
        "region_code": settings.region_code,
        "region_name": settings.region_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_fingerprint": fingerprint,
        "target": TARGET_LABELS,
        "source_period": (
            f"{monthly['year_month'].iloc[0]}~{monthly['year_month'].iloc[-1]}"
        ),
        "observation_count": len(monthly),
        "feature_names": list(FEATURE_NAMES),
        "feature_names_by_target": FEATURE_NAMES_BY_TARGET,
        "train_target_period": (
            f"{target_months[0]}~{target_months[validation_start - 1]}"
        ),
        "validation_period": (
            f"{target_months[validation_start]}~{target_months[test_start - 1]}"
        ),
        "test_period": f"{target_months[test_start]}~{target_months[-1]}",
        "baseline": BASELINE,
        "evaluation": evaluation,
        "recursive_evaluation": recursive_evaluation,
        "limitations": [
            f"{len(monthly)}개월·한 지역의 초기 모델입니다.",
            "모델 선택은 Validation에서만 합니다.",
            "예측은 과거 데이터의 자연스러운 추세를 바탕으로 합니다.",
            "검색량은 실제 방문자나 예약 건수와 같은 지표가 아닙니다.",
            "업종별 소비비중과 SNS 언급량은 예측하지 않습니다.",
        ],
    }

    settings.artifact_directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, settings.artifact_directory / "demand_model.joblib")

    metadata_path = settings.artifact_directory / "demand_model.metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return metadata


def _load_region_artifact(
    settings: RegionForecastSettings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """저장된 모델과 모델 설명 파일을 읽습니다."""
    model_path = settings.artifact_directory / "demand_model.joblib"
    metadata_path = settings.artifact_directory / "demand_model.metadata.json"

    if not model_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(
            f"{settings.region_name} 모델이 없습니다. 먼저 학습을 실행하세요."
        )

    artifact = joblib.load(model_path)
    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)
    return artifact, metadata


def predict_region_future_months(
    settings: RegionForecastSettings,
    horizon: int = 4,
) -> dict[str, Any]:
    """저장된 모델로 최신 관측월 다음의 여러 달을 예측합니다."""
    if horizon < 3 or horizon > 24:
        raise ValueError("예측 기간은 3개월 이상 24개월 이하여야 합니다.")

    artifact, metadata = _load_region_artifact(settings)
    # 설정 상자에 저장해 둔 데이터 읽기 함수를 실행합니다.
    monthly = settings.load_monthly_function()

    saved_fingerprint = artifact.get("data_fingerprint")
    current_fingerprint = data_fingerprint(monthly)
    if saved_fingerprint and saved_fingerprint != current_fingerprint:
        raise ValueError("원자료가 변경되었습니다. 모델을 다시 학습하세요.")

    if metadata.get("data_fingerprint") != artifact.get("data_fingerprint"):
        raise ValueError("모델 파일과 메타데이터가 서로 다릅니다.")

    forecasts = _recursive_forecasts(artifact, monthly, horizon)
    latest = monthly.iloc[-1]

    latest_metrics = {}
    for target_name in TARGETS:
        latest_metrics[target_name] = _round_prediction(
            target_name,
            float(latest[target_name]),
        )

    recent_actuals = []
    for row in monthly.tail(3).itertuples(index=False):
        actual = {"month": str(row.year_month), "is_forecast": False}
        for target_name in TARGETS:
            actual[target_name] = _round_prediction(
                target_name,
                float(getattr(row, target_name)),
            )
        recent_actuals.append(actual)

    return {
        "latest_observed_month": str(latest["year_month"]),
        "latest_observed_visitors": round(float(latest["visitors"])),
        "latest_observed_spending_krw": round(float(latest["spending_krw"])),
        "latest_observed_lodging_nights": round(
            float(latest["lodging_nights"]),
            2,
        ),
        "latest_observed_metrics": latest_metrics,
        "recent_actuals": recent_actuals,
        "forecasts": forecasts,
        "model": metadata,
    }


# 강남구에서 사용할 설정입니다.
GANGNAM_FORECAST_SETTINGS = RegionForecastSettings(
    region_code=REGION_CODE,
    region_name="서울특별시 강남구",
    load_monthly_function=load_gangnam_monthly_demand,
    processed_data_function=write_processed_dataset,
    artifact_directory=ARTIFACT_DIRECTORY,
    model_version=MODEL_VERSION,
)


def train_gangnam_models() -> dict[str, Any]:
    """강남구 모델 학습을 시작하는 함수입니다."""

    print("train_region_models(GANGNAM_FORECAST_SETTINGS) : gangnam_forecast.py")
    return train_region_models(GANGNAM_FORECAST_SETTINGS)


def predict_future_months(horizon: int = 4) -> dict[str, Any]:
    """강남구의 미래 여러 달을 예측합니다."""
    return predict_region_future_months(GANGNAM_FORECAST_SETTINGS, horizon)


def predict_next_three_months() -> dict[str, Any]:
    """강남구의 다음 3개월을 예측합니다."""
    return predict_future_months(3)
