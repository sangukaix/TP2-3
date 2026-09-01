"""MySQL의 검증된 전국 비교 요약을 AI snapshot에 읽기 전용으로 붙입니다.

원본 ZIP이나 LLM을 호출하지 않습니다. DB가 아직 준비되지 않으면 상위 호출부가
기존 지역 원자료 기반 기획안을 계속 만들 수 있도록 명확한 오류만 반환합니다.
"""

from __future__ import annotations

import json
from typing import Any


class NationwideContextUnavailable(RuntimeError):
    """MySQL 설정·연결·적재 데이터가 준비되지 않았을 때 사용하는 안전한 오류입니다."""


def _connect(env_values: dict[str, Any]) -> Any:
    """전국 비교 조회 전용 MySQL 연결을 만들고 비밀값은 오류·로그에 출력하지 않습니다."""
    password = str(env_values.get("MYSQL_PASSWORD") or "").strip()
    if not password:
        raise NationwideContextUnavailable("MYSQL_PASSWORD 미설정")
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - requirements 설치 누락
        raise NationwideContextUnavailable("PyMySQL 미설치") from exc
    try:
        return pymysql.connect(
            host=str(env_values.get("MYSQL_HOST") or "127.0.0.1"),
            port=int(env_values.get("MYSQL_PORT") or 3306),
            user=str(env_values.get("MYSQL_USER") or "tourism_app"),
            password=password,
            database=str(env_values.get("MYSQL_DATABASE") or "tourism_strategy"),
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as exc:
        raise NationwideContextUnavailable(f"MySQL 연결 불가: {type(exc).__name__}") from exc


def _source_ids(value: Any) -> list[str]:
    """JSON 컬럼의 원본 출처 ID만 보존하고, 형식 오류는 빈 목록으로 안전하게 처리합니다."""
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def load_nationwide_comparison(region_code: str, env_values: dict[str, Any]) -> dict[str, Any] | None:
    """선택 지역의 12개월 관측 비교와 검증된 peer 목록을 반환합니다.

    반환 값은 인과효과·정책 성과·전국 평균을 포함하지 않습니다. MySQL에 해당 지역이
    없으면 ``None``을 돌려 기존 동일 시도 원본 비교를 그대로 사용하게 합니다.
    """
    with _connect(env_values) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rpc.*, dr.province_name, dr.local_hierarchy_name
                FROM regional_planning_context rpc
                JOIN dim_region dr ON dr.region_code = rpc.region_code
                WHERE rpc.region_code=%s
                """,
                (region_code,),
            )
            context = cursor.fetchone()
            if not context:
                return None
            cursor.execute(
                """
                SELECT peer.peer_rank, peer.peer_region_code, peer.distance, peer.visitors_gap_pct,
                    peer.spend_per_visitor_gap_krw, peer.overnight_ratio_gap_pct_point,
                    peer.comparison_period_end, peer.method, dr.province_name, dr.local_hierarchy_name
                FROM regional_peer_comparison peer
                JOIN dim_region dr ON dr.region_code = peer.peer_region_code
                WHERE peer.region_code=%s ORDER BY peer.peer_rank
                """,
                (region_code,),
            )
            peers = cursor.fetchall()
            source_ids = _source_ids(context.get("source_ids_json"))
            source_rows: list[dict[str, Any]] = []
            if source_ids:
                placeholders = ",".join(["%s"] * len(source_ids))
                cursor.execute(
                    f"SELECT source_id, source_name, source_page_url, date_range FROM data_source WHERE source_id IN ({placeholders})",
                    source_ids,
                )
                source_rows = cursor.fetchall()

    return {
        "available": True,
        "scope": "전국에서 동일한 12개월 관측값이 검증된 지역과의 비교",
        "period": f"{context['period_start']} ~ {context['period_end']}",
        "comparison_period": f"{context['comparison_period_start']} ~ {context['comparison_period_end']}",
        "method": peers[0]["method"] if peers else "standardized_euclidean_v1",
        "selected_region": {
            "region_code": region_code,
            "region_name": f"{context['province_name']} {context['local_hierarchy_name']}",
            "visitors_12m": int(context["visitors_12m"]),
            "visitors_yoy_pct": float(context["visitors_yoy_pct"]) if context["visitors_yoy_pct"] is not None else None,
            "domestic_spend_12m_thousand_krw": float(context["domestic_spend_12m_thousand_krw"]) if context["domestic_spend_12m_thousand_krw"] is not None else None,
            "domestic_spend_yoy_pct": float(context["domestic_spend_yoy_pct"]) if context["domestic_spend_yoy_pct"] is not None else None,
            "spend_per_visitor_krw": float(context["spend_per_visitor_krw"]) if context["spend_per_visitor_krw"] is not None else None,
            "overnight_ratio_avg_pct": float(context["overnight_ratio_avg_pct"]) if context["overnight_ratio_avg_pct"] is not None else None,
            "avg_stay_days": float(context["avg_stay_days"]) if context["avg_stay_days"] is not None else None,
            "percentiles": {
                "visitors_12m": float(context["visitors_12m_percentile"]) if context["visitors_12m_percentile"] is not None else None,
                "spend_per_visitor_krw": float(context["spend_per_visitor_krw_percentile"]) if context["spend_per_visitor_krw_percentile"] is not None else None,
                "overnight_ratio_avg_pct": float(context["overnight_ratio_avg_pct_percentile"]) if context["overnight_ratio_avg_pct_percentile"] is not None else None,
                "avg_stay_days": float(context["avg_stay_days_percentile"]) if context["avg_stay_days_percentile"] is not None else None,
            },
        },
        "peer_regions": [
            {
                "rank": int(row["peer_rank"]),
                "region_code": row["peer_region_code"],
                "region_name": f"{row['province_name']} {row['local_hierarchy_name']}",
                "distance": float(row["distance"]),
                "visitors_gap_pct": float(row["visitors_gap_pct"]) if row["visitors_gap_pct"] is not None else None,
                "spend_per_visitor_gap_krw": float(row["spend_per_visitor_gap_krw"]) if row["spend_per_visitor_gap_krw"] is not None else None,
                "overnight_ratio_gap_pct_point": float(row["overnight_ratio_gap_pct_point"]) if row["overnight_ratio_gap_pct_point"] is not None else None,
            }
            for row in peers
        ],
        "source_ids": source_ids,
        "source_records": [
            {
                "source_id": row["source_id"],
                "title": row["source_name"],
                "source_url": row["source_page_url"] or "https://datalab.visitkorea.or.kr/",
                "date_range": row["date_range"] or "",
            }
            for row in source_rows
        ],
        "limitation": "관측된 12개월 비교와 유사 지표 거리다. 정책 실행 효과·전국 평균·인과관계를 뜻하지 않는다.",
    }
