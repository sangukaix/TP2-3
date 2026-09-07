"""전국 월별 관측값에서 지역별 ML 학습 가능 여부를 자동 점검한다.

이 도구는 모델을 학습·등록하지 않는다. 최소 기간·연속 월·필수 target을 통과한
지역만 이후 지역별 시간순 평가 후보로 표시해, 강남 모델을 다른 지역에 복사하는
실수를 막는다.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "nationwide" / "merged_nationwide_staging" / "tourism_monthly_staging.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "nationwide" / "region_ml_readiness.csv"
REQUIRED_TARGETS = ("visitors", "domestic_tourism_spend_thousand_krw", "overnight_ratio_pct", "avg_stay_days")


def _expected_months(start: str, end: str) -> list[str]:
    """시작·종료월 사이의 빠진 월을 검증하기 위한 YYYY-MM 목록을 만듭니다."""
    start_date = datetime.strptime(start, "%Y-%m").date().replace(day=1)
    end_date = datetime.strptime(end, "%Y-%m").date().replace(day=1)
    months: list[str] = []
    current = start_date
    while current <= end_date:
        months.append(current.strftime("%Y-%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return months


def assess_readiness(frame: pd.DataFrame, *, min_months: int = 24) -> pd.DataFrame:
    """지역별 기간·연속성·핵심 target 결측을 계산해 등록 후보만 명시합니다."""
    required_columns = {"region_code", "year_month", *REQUIRED_TARGETS}
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"필수 열 누락: {', '.join(sorted(missing))}")
    working = frame.copy()
    working["region_code"] = working["region_code"].astype(str)
    working["year_month"] = working["year_month"].astype(str)
    records: list[dict[str, object]] = []
    for region_code, group in working.groupby("region_code", sort=True):
        group = group.sort_values("year_month").drop_duplicates("year_month", keep="last")
        months = group["year_month"].tolist()
        expected = _expected_months(months[0], months[-1]) if months else []
        missing_month_count = len(set(expected) - set(months))
        target_complete = all(group[target].notna().all() for target in REQUIRED_TARGETS)
        target_missing = [target for target in REQUIRED_TARGETS if not group[target].notna().all()]
        eligible = len(group) >= min_months and missing_month_count == 0 and target_complete
        records.append({
            "region_code": region_code,
            "period_start": months[0] if months else "",
            "period_end": months[-1] if months else "",
            "observed_month_count": len(group),
            "missing_month_count": missing_month_count,
            "missing_targets": ";".join(target_missing),
            "readiness": "eligible_for_time_split_evaluation" if eligible else "not_ready",
            "reason": "24개월 이상·월 연속·핵심 target 충족" if eligible else "기간·월 연속성·핵심 target을 확인하세요",
        })
    return pd.DataFrame(records)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="전국 지역별 ML 학습 가능성 점검")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-months", type=int, default=24)
    args = parser.parse_args(argv)
    frame = pd.read_csv(args.input, dtype={"region_code": str, "year_month": str})
    result = assess_readiness(frame, min_months=args.min_months)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    print(result["readiness"].value_counts().to_json(force_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
