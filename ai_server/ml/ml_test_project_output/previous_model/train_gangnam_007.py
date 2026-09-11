"""초보자용 강남구 방문자 수 학습 예제.

이 파일은 운영 서버의 모델을 바꾸지 않는 학습 연습용 파일입니다.

전체 흐름
1. 월별 데이터 읽기
2. 학습에 사용할 열 선택
3. 과거 데이터와 테스트 데이터 나누기
4. 머신러닝 모델 학습
5. 예측값과 실제값 비교
6. 연습용 모델 파일 저장

실행 방법
    프로젝트 루트에서 다음 명령을 실행합니다.

    .\\backend\\.venv\\Scripts\\python.exe -m ai_server.ml.train_gangnam_007

이 파일이 저장하는 파일은
artifacts/ml/11680/learning_demo_007_visitors_model.joblib 입니다.
운영 서버가 사용하는 demand_model.joblib은 수정하지 않습니다.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

from .gangnam_data import write_processed_dataset


# 이 파일이 있는 위치를 기준으로 프로젝트 루트 경로를 계산합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 연습 결과를 저장할 별도 파일입니다. 운영 모델 파일과 이름이 다릅니다.
DEMO_MODEL_PATH = PROJECT_ROOT / "artifacts" / "ml" / "11680" / "learning_demo_007_visitors_model.joblib"


def read_data() -> pd.DataFrame:
    """원본 ZIP을 읽어 월별 DataFrame을 준비합니다.

    실제 ZIP 해석은 기존 전처리 함수를 사용합니다.
    이 함수의 역할은 '데이터를 가져오는 단계'라고 이해하면 됩니다.
    """

    print("[1단계] 데이터를 읽는 중입니다...")
    data = write_processed_dataset()
    print(f"       데이터 행 수: {len(data)}개")
    print(f"       데이터 기간: {data['year_month'].min()} ~ {data['year_month'].max()}")
    return data


def clean_data(data: pd.DataFrame) -> pd.DataFrame:
    """학습에 필요한 열만 남기고 날짜 순서대로 정렬합니다."""

    print("[2단계] 데이터를 정리하는 중입니다...")

    # 이번 예제에서는 방문자 수 하나만 학습합니다.
    simple_data = data[["year_month", "visitors"]].copy()

    # year_month가 문자열이어도 계산할 수 있도록 숫자로 변환합니다.
    simple_data["year_month"] = simple_data["year_month"].astype(int)

    # 데이터가 오래된 월부터 정렬되어 있는지 보장합니다.
    simple_data = simple_data.sort_values("year_month").reset_index(drop=True)

    # 비어 있는 값이 있으면 학습할 수 없으므로 제거합니다.
    simple_data = simple_data.dropna()

    print(f"       정리 후 데이터 행 수: {len(simple_data)}개")
    return simple_data


def make_features(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """날짜에서 모델이 사용할 입력값 X와 정답 y를 만듭니다."""

    print("[3단계] 학습용 입력값과 정답을 만드는 중입니다...")

    # year_month 예: 202607 -> 연도 2026, 월 7
    year = data["year_month"] // 100
    month = data["year_month"] % 100

    # X는 모델에게 보여주는 정보입니다.
    features = pd.DataFrame({"year": year, "month": month})

    # y는 모델이 맞혀야 하는 정답입니다.
    target = data["visitors"]

    print("       X(입력값): year, month")
    print("       y(정답): visitors")
    return features, target


def split_by_time(
    features: pd.DataFrame,
    target: pd.Series,
    test_month_count: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """시간 순서를 지키면서 앞부분은 학습용, 뒷부분은 테스트용으로 나눕니다."""

    print("[4단계] 학습용과 테스트용 데이터를 나누는 중입니다...")

    # 관광 데이터는 시간 순서가 중요하므로 무작위로 섞지 않습니다.
    split_index = len(features) - test_month_count
    train_features = features.iloc[:split_index]
    test_features = features.iloc[split_index:]
    train_target = target.iloc[:split_index]
    test_target = target.iloc[split_index:]

    print(f"       학습 데이터: {len(train_features)}개")
    print(f"       테스트 데이터: {len(test_features)}개")
    return train_features, test_features, train_target, test_target


def train_model(
    train_features: pd.DataFrame,
    train_target: pd.Series,
) -> LinearRegression:
    """LinearRegression 모델을 만들고 학습시킵니다."""

    print("[5단계] 머신러닝 모델을 학습하는 중입니다...")

    # LinearRegression은 입력값과 정답의 관계를 직선으로 학습하는 간단한 모델입니다.
    model = LinearRegression()
    model.fit(train_features, train_target)

    print("       학습 완료")
    return model


def check_result(
    model: LinearRegression,
    test_features: pd.DataFrame,
    test_target: pd.Series,
) -> None:
    """테스트 데이터로 예측하고 실제값과 비교합니다."""

    print("[6단계] 예측값과 실제값을 비교하는 중입니다...")
    predicted = model.predict(test_features)
    error = mean_absolute_error(test_target, predicted)

    print(f"       평균 오차: {error:,.0f}명")
    print()
    print("       실제 방문자 수  →  모델 예측 방문자 수")

    for actual, prediction in zip(test_target, predicted):
        print(f"       {actual:>12,.0f}명  →  {prediction:>12,.0f}명")


def save_model(model: LinearRegression) -> None:
    """학습한 연습용 모델을 별도 파일로 저장합니다."""

    print("[7단계] 연습용 모델을 저장하는 중입니다...")
    DEMO_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, DEMO_MODEL_PATH)
    print(f"       저장 완료: {DEMO_MODEL_PATH}")


def main() -> None:
    """위의 함수를 정해진 순서로 실행합니다."""

    print("강남구 방문자 수 학습 예제를 시작합니다.\n")

    # 1. 데이터 읽기
    raw_data = read_data()

    # 2. 데이터 정리
    clean = clean_data(raw_data)

    # 3. X와 y 만들기
    features, target = make_features(clean)

    # 4. 학습용/테스트용 나누기
    train_x, test_x, train_y, test_y = split_by_time(features, target)

    # 5. 학습
    model = train_model(train_x, train_y)

    # 6. 결과 확인
    check_result(model, test_x, test_y)

    # 7. 별도 파일 저장
    save_model(model)

    print("\n학습 예제가 끝났습니다.")


if __name__ == "__main__":
    main()
