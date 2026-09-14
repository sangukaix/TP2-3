"""통합 모델 파일에서 실제 예측에 사용할 모델을 선택하는 설정입니다."""

# 이 값만 바꾸고 서버를 재시작하면 됩니다.
# 사용할 모델 계열을 이 값 하나로 선택합니다.
ACTIVE_MODEL_FAMILY = "GradientBoostingRegressor"

_MODEL_FAMILY_ALIASES = {
    "linear_regression": "linear_regression",
    "LinearRegression": "linear_regression",
    "random_forest": "random_forest",
    "RandomForestRegressor": "random_forest",
    "boosting": "boosting",
    "GradientBoostingRegressor": "boosting",
    "xgboost": "xgboost",
    "XGBRegressor": "xgboost",
}

def get_active_model_family() -> str:
    try:
        return _MODEL_FAMILY_ALIASES[ACTIVE_MODEL_FAMILY]
    except KeyError as exc:
        allowed = ", ".join(_MODEL_FAMILY_ALIASES)
        raise ValueError(f"ACTIVE_MODEL_FAMILY는 다음 이름 중 하나여야 합니다: {allowed}") from exc
