"""초보자용 강남구 방문자 수 학습 프로그램.

기존 train_gangnam.py는 7개 지표, 여러 평가 단계, 원본 ZIP 파싱을 한꺼번에
처리합니다. 이 파일은 같은 학습 과정을 이해하기 쉽도록 다음 네 단계로 줄였습니다.

    CSV 읽기 → Feature 만들기 → 학습/평가 → 별도 파일 저장

주의:
    이 파일은 교육용 대체 예제입니다. 기존 운영 모델 파일을 덮어쓰지 않습니다.

실행:
    프로젝트 루트에서
    .\\backend\\.venv\\Scripts\\python.exe -u ai_server\\ml\\train_gangnam2.py
"""

from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error


# -----------------------------
# 1. 파일 위치와 학습 설정
# -----------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = PROJECT_ROOT / "data" / "processed" / "ml" / "11680" / "monthly_demand.csv"

# 기존 demand_model.joblib과 다른 파일명입니다.
MODEL_FILE = PROJECT_ROOT / "artifacts" / "ml" / "11680" / "learning_demo_visitors_model.joblib"
INFO_FILE = PROJECT_ROOT / "artifacts" / "ml" / "11680" / "learning_demo_visitors_info.json"

TEST_MONTHS = 4
FEATURES = ["visitors_lag_1", "visitors_lag_3", "visitors_lag_12"]


# -----------------------------
# 2. 데이터 읽기와 Feature 만들기
# -----------------------------

def read_monthly_data() -> pd.DataFrame:
    """전처리된 월별 방문자 수 CSV를 읽습니다.

    이 예제에서는 원본 ZIP을 직접 처리하지 않습니다.
    원본 ZIP → 전처리 CSV 과정은 실제 프로젝트의 gangnam_data.py가 담당합니다.
    """
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"학습 데이터가 없습니다: {DATA_FILE}\n"
            "먼저 실제 학습 명령을 실행해 전처리 CSV를 만들어 주세요."
        )

    data = pd.read_csv(DATA_FILE)
    data["year_month"] = data["year_month"].astype(str)
    data = data.sort_values("year_month").reset_index(drop=True)
    return data[["year_month", "visitors"]]


def make_learning_table(monthly_data: pd.DataFrame) -> pd.DataFrame:
    """과거 방문자 수를 사용해 다음 달 예측용 학습표를 만듭니다."""
    table = monthly_data.copy()

    # 현재 달을 예측할 때 과거 1·3·12개월의 값만 봅니다.
    table["visitors_lag_1"] = table["visitors"].shift(1)
    table["visitors_lag_3"] = table["visitors"].shift(3)
    table["visitors_lag_12"] = table["visitors"].shift(12)

    # 12개월 전 값이 없는 첫 12개월은 학습에서 제외합니다.
    return table.dropna().reset_index(drop=True)


# -----------------------------
# 3. 학습과 평가
# -----------------------------

def train_and_test(learning_table: pd.DataFrame) -> tuple[LinearRegression, dict]:
    """시간순으로 학습하고 마지막 4개월의 예측 성능을 확인합니다."""
    # 미래 데이터를 미리 보지 않도록 마지막 4개월을 Test로 남깁니다.
    train = learning_table.iloc[:-TEST_MONTHS]
    test = learning_table.iloc[-TEST_MONTHS:]

    model = LinearRegression()
    model.fit(train[FEATURES], train["visitors"])

    # 음수 방문자 수는 의미가 없으므로 0보다 작으면 0으로 바꿉니다.
    predictions = model.predict(test[FEATURES]).clip(min=0)
    actual = test["visitors"]

    # 비교를 위해 작년 같은 달 값을 기준선으로 사용합니다.
    baseline = test["visitors_lag_12"]

    model_mae = mean_absolute_error(actual, predictions)
    baseline_mae = mean_absolute_error(actual, baseline)

    print("=== train_gangnam2.py ===")
    print(f"학습 기간: {train['year_month'].iloc[0]} ~ {train['year_month'].iloc[-1]}")
    print(f"테스트 기간: {test['year_month'].iloc[0]} ~ {test['year_month'].iloc[-1]}")
    print(f"모델: LinearRegression")
    print(f"모델 MAE: {model_mae:,.0f}")
    print(f"기준선 MAE: {baseline_mae:,.0f}")
    print()

    result = test[["year_month", "visitors"]].copy()
    result["prediction"] = predictions.round().astype(int)
    result["baseline"] = baseline.round().astype(int)
    print(result.to_string(index=False))

    return model, {
        "model": "LinearRegression",
        "features": FEATURES,
        "train_period": f"{train['year_month'].iloc[0]}~{train['year_month'].iloc[-1]}",
        "test_period": f"{test['year_month'].iloc[0]}~{test['year_month'].iloc[-1]}",
        "model_mae": round(float(model_mae), 2),
        "baseline_mae": round(float(baseline_mae), 2),
        "model_is_better": bool(model_mae < baseline_mae),
    }


# -----------------------------
# 4. 모델 저장
# -----------------------------

def save_learning_result(model: LinearRegression, info: dict) -> None:
    """교육용 모델과 간단한 정보를 기존 모델과 다른 파일에 저장합니다."""
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_FILE)
    INFO_FILE.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"교육용 모델 저장: {MODEL_FILE}")
    print(f"교육용 정보 저장: {INFO_FILE}")


# -----------------------------
# 프로그램 시작점
# -----------------------------

def main() -> None:
    """위의 함수를 정해진 순서대로 실행합니다."""
    monthly_data = read_monthly_data()
    learning_table = make_learning_table(monthly_data)
    model, info = train_and_test(learning_table)
    save_learning_result(model, info)


if __name__ == "__main__":
    main()
