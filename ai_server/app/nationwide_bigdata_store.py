"""MySQL의 기간 집계 전국 빅데이터를 기획 Agent용 작은 읽기 전용 context로 제공한다.

이 자료는 시군구의 연/반기 합계·비중과 전국 월별 흐름이다. 지역 월별 수요 예측,
정책효과, 전국 평균으로 바꾸지 않고 범위와 한계를 그대로 붙인다.
"""

from __future__ import annotations

from typing import Any

from .nationwide_context_store import NationwideContextUnavailable, _connect


class NationwideBigdataUnavailable(NationwideContextUnavailable):
    """새 보조 테이블이 아직 적재되지 않았거나 MySQL을 읽을 수 없는 경우다."""


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None


def load_nationwide_bigdata_context(region_code: str, env_values: dict[str, Any]) -> dict[str, Any] | None:
    """선택 지역의 최신 연/반기 신호와 전국 최신 월별 배경만 가져온다.

    행 수를 의도적으로 작게 제한해 로컬 LLM 문맥을 늘리지 않으며, 원본 전체는 MySQL과
    processed CSV에 보존한다.
    """
    try:
        with _connect(env_values) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.metric_name, m.audience, m.dataset_group, m.period_start, m.period_end,
                           m.period_kind, m.metric_value, m.unit, m.share_pct, m.source_id,
                           s.source_name, s.file_name, s.source_page_url, s.review_status
                    FROM nationwide_municipal_period_metric m
                    JOIN data_source s ON s.source_id=m.source_id
                    WHERE m.region_code=%s
                    ORDER BY m.period_end DESC, m.period_start DESC,
                             FIELD(m.metric_name, 'visitors', 'tourism_spend', 'navigation_searches'),
                             FIELD(m.audience, 'domestic', 'foreign', 'all')
                    LIMIT 12
                    """,
                    (region_code,),
                )
                municipal = cursor.fetchall()
                if not municipal:
                    return None
                cursor.execute(
                    """
                    SELECT `year_month`, metric_name, audience, dataset_group, category_name, metric_value, unit, source_id
                    FROM nationwide_monthly_tourism_context
                    WHERE `year_month`=(SELECT MAX(`year_month`) FROM nationwide_monthly_tourism_context)
                    ORDER BY FIELD(metric_name, 'visitors', 'tourism_spend', 'navigation_searches'),
                             FIELD(audience, 'domestic', 'foreign', 'all'), metric_value DESC
                    LIMIT 10
                    """
                )
                national = cursor.fetchall()
    except Exception as exc:
        raise NationwideBigdataUnavailable(f"전국 빅데이터 MySQL 조회 불가: {type(exc).__name__}") from exc

    source_rows = []
    seen_sources = set()
    for row in municipal:
        source_id = str(row["source_id"])
        if source_id in seen_sources:
            continue
        seen_sources.add(source_id)
        source_rows.append({
            "source_id": source_id, "title": f"{row['source_name']} · {row['file_name']}" if row.get('file_name') else row['source_name'],
            "source_url": row["source_page_url"] or "https://datalab.visitkorea.or.kr/",
            "review_status": row["review_status"],
        })
    return {
        "available": True,
        "scope": "한국관광 데이터랩 팀 제공 다운로드의 시군구 기간합계·비중 및 전국 월별 추이",
        "municipal_period_metrics": [
            {
                "metric": row["metric_name"], "audience": row["audience"], "dataset_group": row["dataset_group"],
                "period": f"{row['period_start']} ~ {row['period_end']}", "period_kind": row["period_kind"],
                "value": _number(row["metric_value"]), "unit": row["unit"], "share_pct": _number(row["share_pct"]),
                "source_id": row["source_id"],
            }
            for row in municipal
        ],
        "national_monthly_context": [
            {
                "month": row["year_month"], "metric": row["metric_name"], "audience": row["audience"],
                "category": row["category_name"], "value": _number(row["metric_value"]), "unit": row["unit"],
                "source_id": row["source_id"],
            }
            for row in national
        ],
        "source_records": source_rows,
        "limitations": [
            "시군구 값은 월별 관측값이 아니라 해당 기간의 합계 또는 비중이다. 연간과 반기 값을 같은 기간처럼 비교하지 않는다.",
            "전국 월별 추이는 선택 지역의 실적이나 예측값이 아니다. 지역 요인·정책 효과·전국 평균으로 해석하지 않는다.",
            "다운로드 조건의 정확한 데이터랩 URL은 팀 원본에 기록되지 않아 source review_status=needs_exact_download_url이다. 원문 조건을 확인한 뒤에만 강한 근거로 승격한다.",
        ],
        "tool_usage": "선택 지역의 외국인·내국인·검색 관심도 범위를 보조적으로 확인한다. 지역 월별 ML, 정책효과, 1인당 소비 추정에는 사용하지 않는다.",
    }
