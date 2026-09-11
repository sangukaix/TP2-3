"""강남구 월별 관광수요를 학습하고 미래를 예측하는 독립 실행 파일.

프로젝트의 다른 Python 파일을 import하지 않습니다.
CSV 읽기 → 기간 선택 → Feature 생성 → train_test_split → 학습/평가
→ 재귀 예측 → 모델·CSV·JSON 저장을 이 파일 하나에서 수행합니다.

실행 예:
  python -m ai_server.ml.train_gangnam_in_year --train-period 1y --horizon 6
  python -m ai_server.ml.train_gangnam_in_year --train-period 2y --target visitors
  python -m ai_server.ml.train_gangnam_in_year --train-period all --target all

시계열이므로 train_test_split은 shuffle=False로 사용합니다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "ml" / "11680" / "monthly_demand.csv"
OUTPUT_DIRECTORY = PROJECT_ROOT / "artifacts" / "ml" / "11680" / "yearly"

TARGETS = {
    "visitors": "월간 외지인 순 방문자 수",
    "spending_krw": "월간 외지인 관광소비액(원)",
    "lodging_nights": "월간 평균 숙박일수(일)",
    "lodging_rate_pct": "월간 숙박방문자 비율(%)",
    "stay_minutes": "월간 평균 체류시간(분)",
    "navigation_searches": "월간 내비게이션 검색량(건)",
    "lodging_searches": "월간 숙박 검색량(건)",
}
INTEGER_TARGETS = {"visitors", "spending_krw", "navigation_searches", "lodging_searches"}


def load_monthly_data(path: Path) -> pd.DataFrame:
    """월별 CSV를 읽고 날짜순으로 정리합니다."""
    if not path.exists():
        raise FileNotFoundError(f"학습 CSV가 없습니다: {path}")
    data = pd.read_csv(path)
    required = {"year_month", *TARGETS}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"CSV에 필요한 열이 없습니다: {sorted(missing)}")
    data["year_month"] = data["year_month"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    data = data.sort_values("year_month").drop_duplicates("year_month").reset_index(drop=True)
    for target in TARGETS:
        data[target] = pd.to_numeric(data[target], errors="coerce")
    data = data.dropna(subset=list(TARGETS)).reset_index(drop=True)
    return data


def select_training_period(data: pd.DataFrame, period: str, train_end: str) -> pd.DataFrame:
    """train_end까지의 데이터 중 1년/2년/전체를 선택합니다."""
    if len(train_end) != 6 or not train_end.isdigit():
        raise ValueError("--train-end는 YYYYMM 형식이어야 합니다.")
    before_end = data[data["year_month"] <= train_end].copy()
    if before_end.empty:
        raise ValueError(f"{train_end}까지의 데이터가 없습니다.")
    months = {"1y": 12, "2y": 24, "all": len(before_end)}[period]
    selected = before_end.tail(months).reset_index(drop=True)
    print(f"학습 기간: {selected['year_month'].iloc[0]} ~ {selected['year_month'].iloc[-1]} ({len(selected)}개월)")
    return selected


def build_supervised_table(data: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """과거값(lag)과 계절성으로 Feature X, Target y를 만듭니다."""
    lags = [1, 3]
    if len(data) >= 13:
        lags.append(12)
    feature_names = [f"{target}_lag_{lag}" for lag in lags] + ["month_sin", "month_cos"]
    work = data.copy()
    for lag in lags:
        work[f"{target}_lag_{lag}"] = work[target].shift(lag)
    month_number = work["year_month"].str[-2:].astype(int)
    angle = 2 * np.pi * month_number / 12
    work["month_sin"], work["month_cos"] = np.sin(angle), np.cos(angle)
    work = work.dropna(subset=feature_names + [target]).reset_index(drop=True)
    if len(work) < 4:
        raise ValueError("학습 행이 4개보다 적습니다. 더 긴 기간을 선택하세요.")
    return work[feature_names], work[target], feature_names


def make_model(target: str):
    """건수 계열은 RandomForest, 연속값 계열은 LinearRegression을 사용합니다."""
    if target in {"visitors", "navigation_searches", "lodging_searches"}:
        return RandomForestRegressor(n_estimators=200, random_state=42, min_samples_leaf=1)
    return LinearRegression()


def train_one_target(data: pd.DataFrame, target: str, test_size: float) -> dict:
    """Target 하나의 시간순 학습과 평가를 수행합니다."""
    features, targets, feature_names = build_supervised_table(data, target)
    train_x, test_x, train_y, test_y = train_test_split(features, targets, test_size=test_size, shuffle=False)
    model = make_model(target)
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    mae = float(mean_absolute_error(test_y, predictions))
    rmse = float(np.sqrt(mean_squared_error(test_y, predictions)))
    test_months = data["year_month"].tail(len(test_x)).tolist()
    print(f"[{target}] Train={len(train_x)}행, Test={len(test_x)}행, MAE={mae:,.2f}, RMSE={rmse:,.2f}")
    return {"model": model, "feature_names": feature_names, "selected_model": type(model).__name__, "mae": mae, "rmse": rmse, "test_months": test_months}


def next_month(year_month: str) -> str:
    return (pd.to_datetime(year_month, format="%Y%m") + pd.offsets.MonthBegin(1)).strftime("%Y%m")


def recursive_forecast(data: pd.DataFrame, target: str, model, feature_names: list[str], horizon: int) -> pd.DataFrame:
    """한 달 예측값을 다음 달 Feature로 넣는 재귀 예측입니다."""
    history = data[["year_month", target]].copy()
    rows = []
    for _ in range(horizon):
        month = next_month(history["year_month"].iloc[-1])
        angle = 2 * np.pi * int(month[-2:]) / 12
        values = {"month_sin": np.sin(angle), "month_cos": np.cos(angle)}
        for name in feature_names:
            if name.startswith(f"{target}_lag_"):
                lag = int(name.rsplit("_", 1)[-1])
                values[name] = float(history[target].iloc[-lag])
        x = pd.DataFrame([[values[name] for name in feature_names]], columns=feature_names)
        prediction = max(0.0, float(model.predict(x)[0]))
        prediction = round(prediction) if target in INTEGER_TARGETS else round(prediction, 2)
        rows.append({"year_month": month, target: prediction, "is_forecast": True})
        history.loc[len(history)] = [month, prediction]
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="강남구 기간별 ML 학습 및 미래 예측")
    parser.add_argument("--train-period", choices=["1y", "2y", "all"], default="all", help="1년, 2년 또는 전체")
    parser.add_argument("--train-end", default="202606", help="학습 마지막 실제 월(YYYYMM)")
    parser.add_argument("--target", choices=[*TARGETS, "all"], default="visitors", help="예측 대상")
    parser.add_argument("--horizon", type=int, default=6, help="학습 종료월 다음부터 예측할 개월 수")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test 비율")
    args = parser.parse_args()
    if not 0 < args.test_size < 1 or args.horizon < 1:
        parser.error("--test-size는 0~1, --horizon은 1 이상이어야 합니다.")

    data = select_training_period(load_monthly_data(DATA_PATH), args.train_period, args.train_end)
    targets = list(TARGETS) if args.target == "all" else [args.target]
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    run_name = f"demand_{args.train_period}_through_{args.train_end}"
    summary = {"train_period": args.train_period, "train_end": args.train_end, "horizon": args.horizon, "targets": {}}

    for target in targets:
        result = train_one_target(data, target, args.test_size)
        forecast = recursive_forecast(data, target, result["model"], result["feature_names"], args.horizon)
        model_path = OUTPUT_DIRECTORY / f"{run_name}_{target}.joblib"
        forecast_path = OUTPUT_DIRECTORY / f"{run_name}_{target}_forecast.csv"
        metadata_path = OUTPUT_DIRECTORY / f"{run_name}_{target}.metadata.json"
        joblib.dump({"model": result["model"], "feature_names": result["feature_names"], "target": target}, model_path)
        forecast.to_csv(forecast_path, index=False, encoding="utf-8-sig")
        metadata = {**result, "model": None, "model_path": str(model_path), "forecast_path": str(forecast_path), "target_label": TARGETS[target], "forecast": forecast.to_dict("records")}
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["targets"][target] = metadata
        print(f"[{target}] 모델 저장: {model_path}")
        print(f"[{target}] 예측 저장: {forecast_path}")
        print(forecast.to_string(index=False))

    summary_path = OUTPUT_DIRECTORY / f"{run_name}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"전체 요약 저장: {summary_path}")


if __name__ == "__main__":
    main()


# & ".\backend\.venv\Scripts\python.exe" -c "import pandas, numpy, sklearn, joblib; print('모든 라이브러리 정상')"
#######################################

# 이 파일은 다른 프로젝트 내부 함수를 불러오지 않고 한 파일에서 다음 작업을 수행합니다.
# 1. monthly_demand.csv 읽기
# 2. 학습 기간 선택
#    - 1년: --train-period 1y
#    - 2년: --train-period 2y
#    - 전체: --train-period all
# 3. lag Feature 생성
# 4. month_sin / month_cos 생성
# 5. train_test_split(shuffle=False)로 시간순 분리
# 6. 모델 학습
# 7. MAE / RMSE 평가
# 8. 2026년 7월 이후 재귀 예측
# 9. joblib·예측 CSV·metadata JSON 저장
# 실제 데이터가 2026년 6월까지라면 기본 실행은 다음과 같습니다.
# cd C:\Users\Admin\MBCA\TeamProject\TP2-3

# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_in_year `
#   --train-period all `
#   --train-end 202606 `
#   --target visitors `
#   --horizon 6

# 학습 기간: 202401 ~ 202606 (30개월)
# [visitors] Train=14행, Test=4행, MAE=1,367,968.64, RMSE=1,734,219.24
# [visitors] 모델 저장: C:\Users\Admin\MBCA\TeamProject\TP2-3\artifacts\ml\11680\yearly\demand_all_through_202606_visitors.joblib
# [visitors] 예측 저장: C:\Users\Admin\MBCA\TeamProject\TP2-3\artifacts\ml\11680\yearly\demand_all_through_202606_visitors_forecast.csv
# year_month  visitors  is_forecast
#     202607  17117427         True
#     202608  17926596         True
#     202609  17967324         True
#     202610  17696366         True
#     202611  18290862         True
#     202612  18167533         True
# 전체 요약 저장: C:\Users\Admin\MBCA\TeamProject\TP2-3\artifacts\ml\11680\yearly\demand_all_through_202606_summary.json



# 1년 학습:
# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_in_year `
#   --train-period 1y `
#   --train-end 202606 `
#   --target visitors `
#   --horizon 6
# 2년 학습:
# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_in_year `
#   --train-period 2y `
#   --train-end 202606 `
#   --target visitors `
#   --horizon 6
# 7개 지표를 모두 학습하려면:
# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_in_year `
#   --train-period all `
#   --train-end 202606 `
#   --target all `
#   --horizon 6
# 결과는 기존 모델을 덮어쓰지 않고 아래 별도 폴더에 저장됩니다.
# artifacts/ml/11680/yearly/
# ├─ demand_all_through_202606_visitors.joblib
# ├─ demand_all_through_202606_visitors_forecast.csv
# ├─ demand_all_through_202606_visitors.metadata.json
# └─ demand_all_through_202606_summary.json
# 1년 학습으로 방문객 예측을 실제 실행해 문법과 동작도 확인했습니다. training_result.txt와 기존 demand_model.joblib은 변경하지 않았습니다.



# 7개 지표를 모두 학습하려면 의 7개 지표는 뭔가요?


# 현재 프로젝트에서 말하는 7개 지표는 다음과 같습니다.
# 코드 이름	의미	단위
# visitors	월간 외지인 순 방문자 수	명
# spending_krw	월간 외지인 관광소비액	원
# lodging_nights	월간 평균 숙박일수	일
# lodging_rate_pct	월간 숙박방문자 비율	%
# stay_minutes	월간 평균 체류시간	분
# navigation_searches	월간 내비게이션 목적지 검색량	건
# lodging_searches	월간 숙박 목적지 검색량	건


# --target all로 실행하면 위 7개 지표 각각에 대해 별도 모델을 학습합니다.
# & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_in_year `
#   --train-period all `
#   --train-end 202606 `
#   --target all `
#   --horizon 6
# 결과도 지표별로 따로 생성됩니다.
# demand_all_through_202606_visitors.joblib
# demand_all_through_202606_spending_krw.joblib
# demand_all_through_202606_lodging_nights.joblib
# demand_all_through_202606_lodging_rate_pct.joblib
# demand_all_through_202606_stay_minutes.joblib
# demand_all_through_202606_navigation_searches.joblib
# demand_all_through_202606_lodging_searches.joblib
# 즉 “7개 지표를 모두 학습한다”는 뜻은 하나의 모델이 7개 값을 동시에 예측한다는 뜻이 아니라, 각 지표별로 독립적인 예측 모델 7개를 만든다는 뜻입니다.