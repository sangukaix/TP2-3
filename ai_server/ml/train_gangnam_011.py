"""초보자용 강남구 방문자 수 학습 파일.

기존 train_gangnam_007.py와 운영 서버 모델을 수정하지 않습니다.
실행 흐름은 데이터 읽기 → 정리 → 분리 → 학습 → 확인 → 저장입니다.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
import zipfile

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

from .gangnam_data import load_gangnam_monthly_demand

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# RAW_BUNDLE_PATH = PROJECT_ROOT / "data" / "raw" / "서울특별시" / "서울특별시_강남구-20260828T031131Z-1-001.zip"
# LATEST_VISITOR_ZIP = PROJECT_ROOT / "test-gangnam-dashboard" / "download" / "강남구_방문자.zip"
# PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "ml" / "11680" / "visitors_only.csv"
# MODEL_PATH = PROJECT_ROOT / "artifacts" / "ml" / "11680" / "learning_demo_009_visitors_model.joblib"


# def decode_csv(raw_bytes: bytes) -> str:
#     """CSV 파일의 글자 인코딩을 확인하고 문자열로 바꿉니다."""
#     for encoding in ("utf-8-sig", "cp949", "euc-kr"):
#         try:
#             return raw_bytes.decode(encoding)
#         except UnicodeDecodeError:
#             continue
#     raise ValueError("CSV 파일의 인코딩을 확인할 수 없습니다.")


# def read_number(value: str) -> float:
#     """쉼표가 포함된 숫자 문자열을 계산 가능한 숫자로 바꿉니다."""
#     return float(str(value).replace(",", "").strip())


# def add_visitors_from_zip(archive: zipfile.ZipFile, monthly_visitors: dict[str, float]) -> None:
#     """ZIP 안의 방문자 CSV에서 YYYYMM과 방문자 수를 가져옵니다."""
#     for entry in archive.infolist():
#         filename = entry.filename

#         # 방문자 표가 아닌 CSV는 이번 예제에서 사용하지 않습니다.
#         if not filename.lower().endswith(".csv"):
#             continue
#         if "순 방문자 수 및 숙박 비율" not in filename:
#             continue

#         rows = csv.DictReader(io.StringIO(decode_csv(archive.read(entry))))
#         for row in rows:
#             month = str(row.get("기준년월") or row.get("기준연월") or "").strip()
#             value = row.get("순 방문자수")

#             # 월 형식이 아니거나 방문자 값이 없으면 건너뜁니다.
#             if len(month) != 6 or not month.isdigit() or not value:
#                 continue
#             monthly_visitors[month] = read_number(value)


# def read_nested_zip(monthly_visitors: dict[str, float]) -> None:
#     """바깥 ZIP 안에 있는 여러 연도별 ZIP을 차례대로 읽습니다."""
#     if not RAW_BUNDLE_PATH.exists():
#         raise FileNotFoundError(f"원본 ZIP을 찾지 못했습니다: {RAW_BUNDLE_PATH}")

#     with zipfile.ZipFile(RAW_BUNDLE_PATH) as outer_zip:
#         for entry in outer_zip.infolist():
#             # 바깥 ZIP 안의 방문자 관련 안쪽 ZIP만 선택합니다.
#             if not entry.filename.lower().endswith(".zip"):
#                 continue
#             if "/방문자/" not in entry.filename:
#                 continue

#             # 안쪽 ZIP을 디스크에 풀지 않고 메모리에서 바로 읽습니다.
#             inner_bytes = outer_zip.read(entry)
#             with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zip:
#                 add_visitors_from_zip(inner_zip, monthly_visitors)


# def read_latest_visitor_zip(monthly_visitors: dict[str, float]) -> None:
#     """가장 최근에 별도로 받은 방문자 ZIP을 읽습니다."""
#     if not LATEST_VISITOR_ZIP.exists():
#         raise FileNotFoundError(f"최신 방문자 ZIP을 찾지 못했습니다: {LATEST_VISITOR_ZIP}")

#     with zipfile.ZipFile(LATEST_VISITOR_ZIP) as archive:
#         add_visitors_from_zip(archive, monthly_visitors)


def write_processed_dataset() -> pd.DataFrame:
    """방문자 데이터를 모아 DataFrame으로 만들고 CSV 파일로 저장합니다.

    이 함수가 009 파일 안에 있는 전처리의 중심입니다.
    ZIP 읽기 → 같은 월 데이터 합치기 → DataFrame 만들기 → CSV 저장 순서입니다.
    """
    print()
    print("[3] write_processed_dataset()함수 ")
    print("[전처리] 방문자 데이터를 모으는 중입니다...")
    data = {}

    # # 프로젝트의 공식 전처리 함수가 중첩 ZIP과 여러 CSV 표를 정확히 읽습니다.
    # # 여기서는 그 결과에서 이번 예제에 필요한 두 열만 선택합니다.

    print("[4]load_gangnam_monthly_demand()함수 ")
    all_data = load_gangnam_monthly_demand()
    print("[5]load_gangnam_monthly_demand()함수 끝 : 뒤에 더 해야 함. ")

    print('[6]all data를 data 로 만듦')
    # data = all_data[["year_month", "visitors"]].copy()
    # data["visitors"] = data["visitors"].round().astype(int)

    # # 나중에 내용을 직접 확인할 수 있도록 처리 결과도 CSV로 저장합니다.
    # PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    # data.to_csv(PROCESSED_PATH, index=False, encoding="utf-8-sig")
    # print(f"[전처리] {len(data)}개월 데이터를 저장했습니다: {PROCESSED_PATH}")
    return data


def read_data() -> pd.DataFrame:
    """원본 ZIP을 읽어 하나의 월별 표(DataFrame)로 가져옵니다."""
    print("read_data함수 내 : [1] 데이터 읽기")

    print("write_processed_dataset()함수 호출[2]") 
    data = write_processed_dataset()

    print(f"    행 수: {len(data)}개")
    return data


# def prepare_data(data: pd.DataFrame) -> pd.DataFrame:
#     """학습에 필요한 열만 골라 날짜순으로 정리합니다."""
#     print("[2] 데이터 정리")

#     # 이번 예제에서는 방문자 수만 사용합니다.
#     result = data[["year_month", "visitors"]].copy()
#     result["year_month"] = result["year_month"].astype(int)
#     result = result.sort_values("year_month").dropna().reset_index(drop=True)

#     print("    사용할 열: year_month, visitors")
#     return result


# def make_input_and_answer(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
#     """날짜를 입력값 X로, 방문자 수를 정답 y로 바꿉니다."""
#     print("[3] 입력값(X)과 정답(y) 만들기")

#     # 202607을 2026년 7월로 나눕니다.
#     year = data["year_month"] // 100
#     month = data["year_month"] % 100

#     # X: 모델이 참고하는 정보
#     x = pd.DataFrame({"year": year, "month": month})

#     # y: 모델이 맞혀야 하는 값
#     y = data["visitors"]
#     return x, y


# def split_data(
#     x: pd.DataFrame,
#     y: pd.Series,
#     test_count: int = 4,
# ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
#     """앞부분은 학습용, 최근 데이터는 테스트용으로 나눕니다."""
#     print("[4] 학습용과 테스트용으로 나누기")

#     # 시간 데이터이므로 섞지 않고 과거부터 미래 순서로 나눕니다.
#     split_index = len(x) - test_count
#     train_x = x.iloc[:split_index]
#     test_x = x.iloc[split_index:]
#     train_y = y.iloc[:split_index]
#     test_y = y.iloc[split_index:]

#     print(f"    학습용: {len(train_x)}개 / 테스트용: {len(test_x)}개")
#     return train_x, test_x, train_y, test_y


# def learn(train_x: pd.DataFrame, train_y: pd.Series) -> LinearRegression:
#     """Linear Regression 모델에게 학습용 데이터를 보여줍니다."""
#     print("[5] 모델 학습")
#     model = LinearRegression()
#     model.fit(train_x, train_y)
#     return model


# def show_result(model: LinearRegression, test_x: pd.DataFrame, test_y: pd.Series) -> None:
#     """테스트 데이터로 예측하고 실제값과 나란히 출력합니다."""
#     print("[6] 예측 결과 확인")

#     prediction = model.predict(test_x)
#     error = mean_absolute_error(test_y, prediction)
#     print(f"    평균 오차: {error:,.0f}명")

#     for actual, predicted in zip(test_y, prediction):
#         print(f"    실제 {actual:,.0f}명 → 예측 {predicted:,.0f}명")


# def save_model(model: LinearRegression) -> None:
#     """연습용 모델을 운영 모델과 다른 이름으로 저장합니다."""
#     print("[7] 모델 저장")
#     MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
#     joblib.dump(model, MODEL_PATH)
#     print(f"    저장 위치: {MODEL_PATH}")


def main() -> None:
    """위 함수들을 학습 순서대로 실행합니다."""

    print("PROJECT_ROOT : ", PROJECT_ROOT)
    print()



    print("강남구 방문자 수 학습을 시작합니다.\n")

    print("read_data() 함수 호출 과 판다스 data객체 생성")
    data = read_data()

    
    # data = prepare_data(data)
    # x, y = make_input_and_answer(data)
    # train_x, test_x, train_y, test_y = split_data(x, y)
    # model = learn(train_x, train_y)
    # show_result(model, test_x, test_y)
    # save_model(model)

    print("\n학습이 끝났습니다.")


if __name__ == "__main__":
    main()


# 실행하기
#  .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_011    

# print한 내용 저장하기 
# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_009 `
#    > ".\training_result.txt" 2>&1