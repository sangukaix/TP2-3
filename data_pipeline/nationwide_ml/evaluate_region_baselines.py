"""전국 시군구별 계절 기준선의 시간순 성능을 평가한다.

이 단계는 복잡한 모델을 억지로 등록하지 않는다. 각 지역의 작년 같은 달 값을
seasonal-naive 기준선으로 먼저 평가해, 이후 후보 모델이 이 수치를 이겼는지
판단할 공통 기준을 만든다. 웹 요청에서 실행하지 않는 오프라인 파이프라인이다.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Sequence

import pandas as pd

from .train_visitors_panel import calculate_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "nationwide" / "merged_nationwide_staging" / "tourism_monthly_staging.csv"
DEFAULT_READINESS = PROJECT_ROOT / "data" / "processed" / "nationwide" / "region_ml_readiness.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "nationwide" / "region_ml_baseline_evaluation.csv"

# 기획 품질에 직접 연결되는 지표만 우선 평가한다. 새 target을 추가하면 결과 CSV에도
# 자동으로 한 행씩 추가되어, 지역별 학습 범위를 코드에서 명확히 확인할 수 있다.
TARGETS = (
    ("visitors", "명"),
    ("domestic_tourism_spend_thousand_krw", "천원"),
    ("overnight_ratio_pct", "%"),
    ("avg_stay_days", "일"),
)
SPLITS = {
    "validation": ("2025-07", "2025-12"),
    "test": ("2026-01", "2026-06"),
}


def _seasonal_lag(frame: pd.DataFrame, target: str) -> pd.DataFrame:
    """각 지역 안에서만 12개월 전 값을 만들며, 다른 지역 데이터는 섞지 않습니다."""
    working = frame[["region_code", "year_month", target]].copy()
    working[target] = pd.to_numeric(working[target], errors="coerce")
    working = working.sort_values(["region_code", "year_month"]).reset_index(drop=True)
    working["seasonal_naive"] = working.groupby("region_code", sort=False)[target].shift(12)
    return working.dropna(subset=[target, "seasonal_naive"])


def evaluate_region_baselines(frame: pd.DataFrame, readiness: pd.DataFrame) -> pd.DataFrame:
    """학습 가능 지역만 대상으로 validation/test 성능을 long format으로 반환합니다."""
    eligible_codes = set(
        readiness.loc[
            readiness["readiness"] == "eligible_for_time_split_evaluation", "region_code"
        ].astype(str)
    )
    records: list[dict[str, object]] = []
    for target, unit in TARGETS:
        if target not in frame.columns:
            continue
        lagged = _seasonal_lag(frame, target)
        for region_code, region_rows in lagged.groupby("region_code", sort=True):
            region_code = str(region_code)
            if region_code not in eligible_codes:
                continue
            for split_name, (start, end) in SPLITS.items():
                split_rows = region_rows[region_rows["year_month"].astype(str).between(start, end)]
                if split_rows.empty:
                    continue
                metrics = calculate_metrics(
                    split_rows[target].to_numpy(dtype=float),
                    split_rows["seasonal_naive"].to_numpy(dtype=float),
                )
                records.append({
                    "region_code": region_code,
                    "target": target,
                    "unit": unit,
                    "model_name": "seasonal_naive",
                    "decision_status": "baseline_only",
                    "split": split_name,
                    "period_start": start,
                    "period_end": end,
                    **metrics,
                    "note": "후보 모델은 이 지역·target·시간순 기준선보다 validation과 test에서 모두 좋아야 등록 가능",
                })
    return pd.DataFrame(records)


def main(argv: Sequence[str] | None = None) -> int:
    """CSV 입력·출력 경로를 받아 지역별 기준선 평가표를 재현 가능하게 생성합니다."""
    parser = argparse.ArgumentParser(description="전국 시군구 계절 기준선 평가")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    frame = pd.read_csv(args.input, dtype={"region_code": str, "year_month": str})
    readiness = pd.read_csv(args.readiness, dtype={"region_code": str})
    result = evaluate_region_baselines(frame, readiness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    print(result.groupby(["target", "split"]).size().to_json(force_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
