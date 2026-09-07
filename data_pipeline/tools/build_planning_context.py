"""월별 관측값을 기획서가 바로 사용할 수 있는 지역 비교 근거로 만든다.

LLM이 원자료에서 비율·순위·유사 지역을 즉석 계산하지 않게 하고, 동일 기간의
관측 사실을 Python이 결정적으로 계산한다. 인과관계나 정책효과는 생성하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


NUMERIC_COLUMNS = [
    "visitors",
    "domestic_tourism_spend_thousand_krw",
    "nonlocal_tourism_spend_thousand_krw",
    "overnight_ratio_pct",
    "avg_stay_days",
    "avg_stay_minutes",
]
PEER_FEATURES = [
    "log_visitors_12m",
    "spend_per_visitor_krw",
    "overnight_ratio_avg_pct",
    "avg_stay_days",
]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_growth(current: float, previous: float) -> float | None:
    if not math.isfinite(current) or not math.isfinite(previous) or previous <= 0:
        return None
    return (current / previous - 1) * 100


def summarize_region(
    region: pd.DataFrame,
    latest_month: pd.Timestamp,
) -> dict[str, object] | None:
    """한 지역의 같은 12개월 구간과 전년 동기를 요약한다."""

    current_start = latest_month - pd.DateOffset(months=11)
    previous_end = current_start - pd.DateOffset(months=1)
    previous_start = previous_end - pd.DateOffset(months=11)
    current = region[(region["month"] >= current_start) & (region["month"] <= latest_month)]
    previous = region[(region["month"] >= previous_start) & (region["month"] <= previous_end)]

    current_visitor_months = int(current["visitors"].notna().sum())
    previous_visitor_months = int(previous["visitors"].notna().sum())
    if current_visitor_months < 12 or previous_visitor_months < 12:
        return None

    visitors_current = float(current["visitors"].sum())
    visitors_previous = float(previous["visitors"].sum())
    spend_current = float(current["domestic_tourism_spend_thousand_krw"].sum())
    spend_previous = float(previous["domestic_tourism_spend_thousand_krw"].sum())
    spend_per_visitor = spend_current * 1000 / visitors_current if visitors_current > 0 else np.nan

    season = (
        region.dropna(subset=["visitors"])
        .assign(calendar_month=lambda frame: frame["month"].dt.month)
        .groupby("calendar_month", as_index=False)["visitors"]
        .mean()
        .sort_values(["visitors", "calendar_month"], ascending=[False, True])
    )
    peak_month = int(season.iloc[0]["calendar_month"]) if not season.empty else None
    source_columns = [column for column in region.columns if column.endswith("_source_id")]
    source_ids = sorted(
        {
            str(value)
            for column in source_columns
            for value in current[column].dropna().tolist()
            if str(value).strip()
        }
    )
    first = region.iloc[0]
    return {
        "region_code": str(first["region_code"]),
        "province_name": first["province_name"],
        "municipality_name": first["municipality_name"],
        "local_hierarchy_name": first["local_hierarchy_name"],
        "period_start": current_start.strftime("%Y-%m"),
        "period_end": latest_month.strftime("%Y-%m"),
        "comparison_period_start": previous_start.strftime("%Y-%m"),
        "comparison_period_end": previous_end.strftime("%Y-%m"),
        "visitors_12m": round(visitors_current),
        "visitors_yoy_pct": safe_growth(visitors_current, visitors_previous),
        "domestic_spend_12m_thousand_krw": round(spend_current, 3),
        "domestic_spend_yoy_pct": safe_growth(spend_current, spend_previous),
        "spend_per_visitor_krw": round(spend_per_visitor, 2),
        "overnight_ratio_avg_pct": round(float(current["overnight_ratio_pct"].mean()), 4),
        "avg_stay_days": round(float(current["avg_stay_days"].mean()), 4),
        "avg_stay_minutes": round(float(current["avg_stay_minutes"].mean()), 4),
        "peak_calendar_month": peak_month,
        "observed_month_count": current_visitor_months,
        "data_quality_status": "complete_12m_comparison",
        "source_ids_json": json.dumps(source_ids, ensure_ascii=False),
    }


def add_percentiles(profile: pd.DataFrame) -> pd.DataFrame:
    """전국 지원 지역 내 상대 위치를 0~100 percentile로 계산한다."""

    for column in (
        "visitors_12m",
        "spend_per_visitor_krw",
        "overnight_ratio_avg_pct",
        "avg_stay_days",
    ):
        profile[f"{column}_percentile"] = (
            profile[column].rank(method="average", pct=True) * 100
        ).round(2)
    return profile


def build_peer_rows(profile: pd.DataFrame, peer_count: int = 5) -> list[dict[str, object]]:
    """규모·소비·체류가 비슷한 지역을 표준화 거리로 찾는다."""

    features = profile.copy()
    features["log_visitors_12m"] = np.log1p(features["visitors_12m"])
    matrix = features[PEER_FEATURES].astype(float)
    standard_deviation = matrix.std(ddof=0).replace(0, 1)
    standardized = (matrix - matrix.mean()) / standard_deviation

    peers: list[dict[str, object]] = []
    for index, region in features.iterrows():
        distances = np.sqrt(((standardized - standardized.loc[index]) ** 2).sum(axis=1))
        ranked = distances[distances.index != index].sort_values().head(peer_count)
        for rank_no, (peer_index, distance) in enumerate(ranked.items(), start=1):
            peer = features.loc[peer_index]
            peers.append(
                {
                    "region_code": region["region_code"],
                    "peer_rank": rank_no,
                    "peer_region_code": peer["region_code"],
                    "peer_province_name": peer["province_name"],
                    "peer_local_hierarchy_name": peer["local_hierarchy_name"],
                    "distance": round(float(distance), 6),
                    "visitors_gap_pct": safe_growth(
                        float(region["visitors_12m"]), float(peer["visitors_12m"])
                    ),
                    "spend_per_visitor_gap_krw": round(
                        float(region["spend_per_visitor_krw"])
                        - float(peer["spend_per_visitor_krw"]),
                        2,
                    ),
                    "overnight_ratio_gap_pct_point": round(
                        float(region["overnight_ratio_avg_pct"])
                        - float(peer["overnight_ratio_avg_pct"]),
                        4,
                    ),
                    "comparison_period_end": region["period_end"],
                    "method": "standardized_euclidean_v1",
                }
            )
    return peers


def build_planning_context(input_csv: Path, output_dir: Path) -> dict[str, object]:
    """전체 지역 profile·peer 비교표와 재현 metadata를 생성한다."""

    data = pd.read_csv(input_csv, dtype={"region_code": str, "year_month": str})
    data["month"] = pd.to_datetime(data["year_month"], format="%Y-%m", errors="coerce")
    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data["month"].isna().any():
        raise ValueError("유효하지 않은 year_month가 있습니다.")
    latest_month = data["month"].max()

    summaries = [
        summary
        for _, region in data.groupby("region_code", sort=True)
        if (summary := summarize_region(region.sort_values("month"), latest_month)) is not None
    ]
    if not summaries:
        raise ValueError("연속 24개월이 확보된 지역이 없어 비교 context를 만들 수 없습니다.")
    profile = add_percentiles(pd.DataFrame(summaries))
    peers = build_peer_rows(profile)

    output_dir.mkdir(parents=True, exist_ok=True)
    profile.sort_values("region_code").to_csv(
        output_dir / "regional_planning_context.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(peers).sort_values(["region_code", "peer_rank"]).to_csv(
        output_dir / "peer_comparisons.csv", index=False, encoding="utf-8-sig"
    )
    summary: dict[str, object] = {
        "input_file": input_csv.name,
        "input_sha256": file_sha256(input_csv),
        "latest_observed_month": latest_month.strftime("%Y-%m"),
        "eligible_region_count": len(profile),
        "excluded_region_count": int(data["region_code"].nunique() - len(profile)),
        "peer_count_per_region": 5,
        "peer_method": "standardized_euclidean_v1",
        "causal_claims_generated": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="기획서용 지역 관측·비교 context 생성")
    parser.add_argument(
        "--input-csv",
        default="data/processed/merged_nationwide_staging/tourism_monthly_staging.csv",
    )
    parser.add_argument("--output-dir", default="data/processed/merged_planning_context")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_csv = Path(args.input_csv)
    if not input_csv.is_file():
        print(f"오류: 입력 staging을 찾을 수 없습니다: {input_csv}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            build_planning_context(input_csv, Path(args.output_dir)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
