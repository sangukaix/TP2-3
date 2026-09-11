"""초보자용 강남구 방문자 수 학습 파일.

기존 train_gangnam_007.py와 운영 서버 모델을 수정하지 않습니다.
실행 흐름은 데이터 읽기 → 정리 → 분리 → 학습 → 확인 → 저장입니다.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

from .gangnam_data import write_processed_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "artifacts" / "ml" / "11680" / "learning_demo_008_visitors_model.joblib"


def read_data() -> pd.DataFrame:
    """원본 ZIP을 읽어 하나의 월별 표(DataFrame)로 가져옵니다."""
    print("[1] 데이터 읽기")
    data = write_processed_dataset()
    print(f"    행 수: {len(data)}개")
    return data


def prepare_data(data: pd.DataFrame) -> pd.DataFrame:
    """학습에 필요한 열만 골라 날짜순으로 정리합니다."""
    print("[2] 데이터 정리")

    # 이번 예제에서는 방문자 수만 사용합니다.
    result = data[["year_month", "visitors"]].copy()
    result["year_month"] = result["year_month"].astype(int)
    result = result.sort_values("year_month").dropna().reset_index(drop=True)

    print("    사용할 열: year_month, visitors")
    return result


def make_input_and_answer(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """날짜를 입력값 X로, 방문자 수를 정답 y로 바꿉니다."""
    print("[3] 입력값(X)과 정답(y) 만들기")

    # 202607을 2026년 7월로 나눕니다.
    year = data["year_month"] // 100
    month = data["year_month"] % 100

    # X: 모델이 참고하는 정보
    x = pd.DataFrame({"year": year, "month": month})

    # y: 모델이 맞혀야 하는 값
    y = data["visitors"]
    return x, y


def split_data(
    x: pd.DataFrame,
    y: pd.Series,
    test_count: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """앞부분은 학습용, 최근 데이터는 테스트용으로 나눕니다."""
    print("[4] 학습용과 테스트용으로 나누기")

    # 시간 데이터이므로 섞지 않고 과거부터 미래 순서로 나눕니다.
    split_index = len(x) - test_count
    train_x = x.iloc[:split_index]
    test_x = x.iloc[split_index:]
    train_y = y.iloc[:split_index]
    test_y = y.iloc[split_index:]

    print(f"    학습용: {len(train_x)}개 / 테스트용: {len(test_x)}개")
    return train_x, test_x, train_y, test_y


def learn(train_x: pd.DataFrame, train_y: pd.Series) -> LinearRegression:
    """Linear Regression 모델에게 학습용 데이터를 보여줍니다."""
    print("[5] 모델 학습")
    model = LinearRegression()
    model.fit(train_x, train_y)
    return model


def show_result(model: LinearRegression, test_x: pd.DataFrame, test_y: pd.Series) -> None:
    """테스트 데이터로 예측하고 실제값과 나란히 출력합니다."""
    print("[6] 예측 결과 확인")

    prediction = model.predict(test_x)
    error = mean_absolute_error(test_y, prediction)
    print(f"    평균 오차: {error:,.0f}명")

    for actual, predicted in zip(test_y, prediction):
        print(f"    실제 {actual:,.0f}명 → 예측 {predicted:,.0f}명")


def save_model(model: LinearRegression) -> None:
    """연습용 모델을 운영 모델과 다른 이름으로 저장합니다."""
    print("[7] 모델 저장")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"    저장 위치: {MODEL_PATH}")


def main() -> None:
    """위 함수들을 학습 순서대로 실행합니다."""
    print("강남구 방문자 수 학습을 시작합니다.\n")

    data = read_data()
    data = prepare_data(data)
    x, y = make_input_and_answer(data)
    train_x, test_x, train_y, test_y = split_data(x, y)
    model = learn(train_x, train_y)
    show_result(model, test_x, test_y)
    save_model(model)

    print("\n학습이 끝났습니다.")


if __name__ == "__main__":
    main()


#########################################
# cd C:\Users\Admin\MBCA\TeamProject\TP2-3

# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_008
# 코드 흐름:
# read_data()
#     ↓
# prepare_data()
#     ↓
# make_input_and_answer()
#     ↓
# split_data()
#     ↓
# learn()
#     ↓
# show_result()
#     ↓
# save_model()
# 이 파일은 운영 서버의 모델을 수정하지 않고 다음 별도 파일에 저장합니다.
# artifacts\ml\11680\learning_demo_008_visitors_model.joblib
# 문법 검사도 완료했습니다. 참고로 Git 상태에 표시되는 train_gangnam_007.py의 기존 수정 표시는 이전 작업에서 발생한 것이며, 이번 새 파일 생성 작업에서는 007 파일을 수정하지 않았습니다.


# 오후 6:34








# train_gangnam_008.py   을 가지고 joblib를 만들었다고 합니다. 그러면 그걸 어디서 로드해서 사용하고 있나요?







# 오후 6:34






# 현재 train_gangnam_008.py가 만든 Joblib 파일은 서버에서 로드하지 않습니다.
# 저장 위치:
# C:\Users\Admin\MBCA\TeamProject\TP2-3\artifacts\ml\11680\learning_demo_008_visitors_model.joblib
# train_gangnam_008.py의 목적은 학습 과정을 연습하는 것이며, 운영 서버 모델에는 영향을 주지 않도록 만들어졌습니다.
# 현재 AI 서버가 사용하는 파일은 다음입니다.
# C:\Users\Admin\MBCA\TeamProject\TP2-3\artifacts\ml\11680\demand_model.joblib
# 서버의 흐름은 대략 다음과 같습니다.
# React
#   ↓
# AI 서버 API
#   ↓
# ai_server/ml/gangnam_forecast.py
#   ↓
# demand_model.joblib 로드
#   ↓
# 방문자 수·소비액 등 예측
# 즉 현재는:
# train_gangnam_008.py
#     → learning_demo_008_visitors_model.joblib 저장
#     → 서버에서 사용하지 않음
# train_gangnam.py
#     → demand_model.joblib 저장
#     → AI 서버가 사용
# Joblib 파일을 직접 확인하려면 다음 명령을 실행할 수 있습니다.
# cd C:\Users\Admin\MBCA\TeamProject\TP2-3

# .\backend\.venv\Scripts\python.exe -c "import joblib; m=joblib.load('artifacts/ml/11680/learning_demo_008_visitors_model.joblib'); print(m)