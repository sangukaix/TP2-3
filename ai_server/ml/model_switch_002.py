"""통합 모델 파일에서 실제 예측에 사용할 모델을 선택하는 설정입니다."""

# 이 값만 바꾸고 서버를 재시작하면 됩니다.
# 사용할 모델 계열을 이 값 하나로 선택합니다.
ACTIVE_MODEL_FAMILY = "boosting"  # linear_regression, random_forest, boosting, xgboost

def get_active_model_family() -> str:
    if ACTIVE_MODEL_FAMILY not in {"linear_regression", "random_forest", "boosting", "xgboost"}:
        raise ValueError("ACTIVE_MODEL_FAMILY는 linear_regression, random_forest, boosting 또는 xgboost여야 합니다.")
    return ACTIVE_MODEL_FAMILY
