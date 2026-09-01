"""검증 완료된 전국 관광 CSV 묶음을 MySQL에 트랜잭션으로 적재한다.

원본 ZIP을 읽지 않으며 기본값은 dry-run이다. ``--apply``를 명시해야만 DB를
변경하고, 기존 행은 지역코드·기준월 같은 자연키 기준으로 upsert한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE_DIR = PROJECT_ROOT / "data" / "processed" / "nationwide" / "mysql_load_bundle"
DEFAULT_CONTEXT_DIR = PROJECT_ROOT / "data" / "processed" / "nationwide" / "merged_planning_context"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "database" / "mysql" / "001_nationwide_tourism_data.sql"


REQUIRED_FILES = {
    "dim_region.csv": {"region_code", "province_name", "municipality_name", "local_hierarchy_name"},
    "data_source.csv": {"source_id", "file_name", "file_hash", "geographic_level", "review_status"},
    "fact_tourism_monthly.csv": {"region_code", "year_month", "visitors", "data_status"},
    "fact_tourism_metric_source.csv": {"region_code", "year_month", "metric_name", "source_id"},
}


@dataclass(frozen=True)
class MysqlConfig:
    """서버 전용 환경변수에서 읽는 MySQL 접속 정보입니다."""

    host: str
    port: int
    user: str
    password: str
    database: str


class BundleValidationError(ValueError):
    """CSV 묶음의 열·행 수·요약 정보가 맞지 않을 때 발생합니다."""


def _load_dotenv_if_available() -> None:
    """CLI가 루트에서 실행되지 않아도 TP2-3의 서버 환경변수를 읽습니다."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - 설치 스크립트가 누락된 개발 환경
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def mysql_config_from_env() -> MysqlConfig:
    """비밀값을 출력하지 않고, 실제 적재 전 필수 설정만 검증합니다."""
    _load_dotenv_if_available()
    config = MysqlConfig(
        host=os.getenv("MYSQL_HOST", "127.0.0.1").strip(),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "tourism_app").strip(),
        password=os.getenv("MYSQL_PASSWORD", "").strip(),
        database=os.getenv("MYSQL_DATABASE", "tourism_strategy").strip(),
    )
    if not config.password:
        raise RuntimeError("MYSQL_PASSWORD가 설정되지 않았습니다. .env에만 추가하세요.")
    return config


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """UTF-8/BOM CSV를 읽고, 헤더가 없는 파일은 즉시 중단합니다."""
    # Excel·Windows에서 만든 CSV 첫 헤더의 BOM까지 제거해야 region_code를 정확히 검증할 수 있습니다.
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise BundleValidationError(f"헤더가 없습니다: {path.name}")
        return list(reader)


def validate_bundle(bundle_dir: Path) -> dict[str, list[dict[str, str]]]:
    """DB 연결 전에 필수 CSV와 summary 행 수가 정확한지 검사합니다."""
    if not bundle_dir.is_dir():
        raise BundleValidationError(f"적재 묶음 폴더가 없습니다: {bundle_dir}")
    rows_by_file: dict[str, list[dict[str, str]]] = {}
    for file_name, required_columns in REQUIRED_FILES.items():
        path = bundle_dir / file_name
        if not path.is_file():
            raise BundleValidationError(f"필수 파일이 없습니다: {file_name}")
        rows = read_csv_rows(path)
        available = set(rows[0]) if rows else set(next(csv.reader(path.open(encoding="utf-8")), []))
        missing = required_columns - available
        if missing:
            raise BundleValidationError(f"{file_name} 필수 열 누락: {', '.join(sorted(missing))}")
        rows_by_file[file_name] = rows

    summary_path = bundle_dir / "summary.json"
    if not summary_path.is_file():
        raise BundleValidationError("summary.json이 없습니다.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected = {
        "dim_region.csv": "dim_region_count",
        "data_source.csv": "data_source_count",
        "fact_tourism_monthly.csv": "fact_tourism_monthly_count",
        "fact_tourism_metric_source.csv": "fact_tourism_metric_source_count",
    }
    for file_name, summary_key in expected.items():
        if int(summary.get(summary_key, -1)) != len(rows_by_file[file_name]):
            raise BundleValidationError(f"summary 행 수 불일치: {file_name}")
    if summary.get("status") != "ready_for_transactional_mysql_import":
        raise BundleValidationError("MySQL 적재 승인 상태가 아닙니다.")
    return rows_by_file


def _nullable(value: str | None) -> str | None:
    """빈 CSV 값만 NULL로 바꾸며 숫자·날짜 형식은 MySQL이 검증하게 둡니다."""
    value = (value or "").strip()
    return value or None


def _execute_schema(cursor: Any, schema_path: Path) -> None:
    """프로시저 없는 프로젝트 스키마를 문장 단위로 실행합니다."""
    if not schema_path.is_file():
        raise FileNotFoundError(f"스키마 파일이 없습니다: {schema_path}")
    statements = [statement.strip() for statement in schema_path.read_text(encoding="utf-8").split(";")]
    for statement in statements:
        if statement:
            cursor.execute(statement)


def _connect(config: MysqlConfig) -> Any:
    """PyMySQL DictCursor 연결을 만들며, 연결 실패는 호출자에게 그대로 알립니다."""
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - requirements 설치 누락
        raise RuntimeError("PyMySQL이 설치되지 않았습니다. requirements.txt를 설치하세요.") from exc
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _summary_hash(bundle_dir: Path) -> str:
    return hashlib.sha256((bundle_dir / "summary.json").read_bytes()).hexdigest()


def _batched(rows: Iterable[tuple[Any, ...]], size: int = 500) -> Iterable[list[tuple[Any, ...]]]:
    batch: list[tuple[Any, ...]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _read_optional_rows(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path) if path.is_file() else []


def import_bundle(
    *,
    bundle_dir: Path,
    context_dir: Path,
    schema_path: Path,
    apply_schema: bool,
) -> dict[str, int]:
    """검증 후 모든 핵심 사실·출처·비교요약을 하나의 DB transaction으로 적재합니다."""
    rows = validate_bundle(bundle_dir)
    planning_rows = _read_optional_rows(context_dir / "regional_planning_context.csv")
    peer_rows = _read_optional_rows(context_dir / "peer_comparisons.csv")
    config = mysql_config_from_env()

    with _connect(config) as connection:
        with connection.cursor() as cursor:
            if apply_schema:
                _execute_schema(cursor, schema_path)
            cursor.execute(
                """
                INSERT INTO data_load_run (raw_snapshot, inventory_hash, started_at, status, source_file_count, raw_row_count)
                VALUES (%s, %s, %s, 'running', %s, %s)
                """,
                (
                    f"nationwide_bundle_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                    _summary_hash(bundle_dir),
                    datetime.now(timezone.utc),
                    len(rows["data_source.csv"]),
                    len(rows["fact_tourism_monthly.csv"]),
                ),
            )
            load_run_id = int(cursor.lastrowid)

            region_sql = """
                INSERT INTO dim_region (region_code, province_name, municipality_name, local_hierarchy_name, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON DUPLICATE KEY UPDATE province_name=VALUES(province_name), municipality_name=VALUES(municipality_name),
                    local_hierarchy_name=VALUES(local_hierarchy_name), is_active=TRUE
            """
            for batch in _batched((
                (row["region_code"], row["province_name"], row["municipality_name"], row["local_hierarchy_name"])
                for row in rows["dim_region.csv"]
            )):
                cursor.executemany(region_sql, batch)

            source_sql = """
                INSERT INTO data_source (source_id, source_name, source_page_url, downloaded_at, file_name, file_hash,
                    date_range, geographic_level, filters_json, methodology_notes, review_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE source_name=VALUES(source_name), source_page_url=VALUES(source_page_url),
                    downloaded_at=VALUES(downloaded_at), date_range=VALUES(date_range), filters_json=VALUES(filters_json),
                    methodology_notes=VALUES(methodology_notes), review_status=VALUES(review_status)
            """
            for batch in _batched((
                tuple(_nullable(row.get(column)) for column in (
                    "source_id", "source_name", "source_page_url", "downloaded_at", "file_name", "file_hash",
                    "date_range", "geographic_level", "filters_json", "methodology_notes", "review_status",
                ))
                for row in rows["data_source.csv"]
            )):
                cursor.executemany(source_sql, batch)

            monthly_sql = """
                INSERT INTO fact_tourism_monthly (region_code, `year_month`, visitors, visitors_previous_year, visitors_yoy_pct,
                    domestic_tourism_spend_thousand_krw, nonlocal_tourism_spend_thousand_krw, unique_visitors,
                    overnight_ratio_pct, avg_stay_days, avg_stay_minutes, data_status, load_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE visitors=VALUES(visitors), visitors_previous_year=VALUES(visitors_previous_year),
                    visitors_yoy_pct=VALUES(visitors_yoy_pct), domestic_tourism_spend_thousand_krw=VALUES(domestic_tourism_spend_thousand_krw),
                    nonlocal_tourism_spend_thousand_krw=VALUES(nonlocal_tourism_spend_thousand_krw), unique_visitors=VALUES(unique_visitors),
                    overnight_ratio_pct=VALUES(overnight_ratio_pct), avg_stay_days=VALUES(avg_stay_days),
                    avg_stay_minutes=VALUES(avg_stay_minutes), data_status=VALUES(data_status), load_run_id=VALUES(load_run_id)
            """
            monthly_columns = (
                "region_code", "year_month", "visitors", "visitors_previous_year", "visitors_yoy_pct",
                "domestic_tourism_spend_thousand_krw", "nonlocal_tourism_spend_thousand_krw", "unique_visitors",
                "overnight_ratio_pct", "avg_stay_days", "avg_stay_minutes", "data_status",
            )
            for batch in _batched((
                tuple(_nullable(row.get(column)) for column in monthly_columns) + (load_run_id,)
                for row in rows["fact_tourism_monthly.csv"]
            )):
                cursor.executemany(monthly_sql, batch)

            metric_source_sql = """
                INSERT INTO fact_tourism_metric_source (region_code, `year_month`, metric_name, source_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE source_id=VALUES(source_id)
            """
            for batch in _batched((
                (row["region_code"], row["year_month"], row["metric_name"], row["source_id"])
                for row in rows["fact_tourism_metric_source.csv"]
            )):
                cursor.executemany(metric_source_sql, batch)

            context_sql = """
                INSERT INTO regional_planning_context (
                    region_code, period_start, period_end, comparison_period_start, comparison_period_end, visitors_12m,
                    visitors_yoy_pct, domestic_spend_12m_thousand_krw, domestic_spend_yoy_pct, spend_per_visitor_krw,
                    overnight_ratio_avg_pct, avg_stay_days, avg_stay_minutes, peak_calendar_month, observed_month_count,
                    data_quality_status, source_ids_json, visitors_12m_percentile, spend_per_visitor_krw_percentile,
                    overnight_ratio_avg_pct_percentile, avg_stay_days_percentile
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE period_start=VALUES(period_start), period_end=VALUES(period_end),
                    comparison_period_start=VALUES(comparison_period_start), comparison_period_end=VALUES(comparison_period_end),
                    visitors_12m=VALUES(visitors_12m), visitors_yoy_pct=VALUES(visitors_yoy_pct),
                    domestic_spend_12m_thousand_krw=VALUES(domestic_spend_12m_thousand_krw), domestic_spend_yoy_pct=VALUES(domestic_spend_yoy_pct),
                    spend_per_visitor_krw=VALUES(spend_per_visitor_krw), overnight_ratio_avg_pct=VALUES(overnight_ratio_avg_pct),
                    avg_stay_days=VALUES(avg_stay_days), avg_stay_minutes=VALUES(avg_stay_minutes), peak_calendar_month=VALUES(peak_calendar_month),
                    observed_month_count=VALUES(observed_month_count), data_quality_status=VALUES(data_quality_status),
                    source_ids_json=VALUES(source_ids_json), visitors_12m_percentile=VALUES(visitors_12m_percentile),
                    spend_per_visitor_krw_percentile=VALUES(spend_per_visitor_krw_percentile),
                    overnight_ratio_avg_pct_percentile=VALUES(overnight_ratio_avg_pct_percentile), avg_stay_days_percentile=VALUES(avg_stay_days_percentile)
            """
            context_columns = (
                "region_code", "period_start", "period_end", "comparison_period_start", "comparison_period_end", "visitors_12m",
                "visitors_yoy_pct", "domestic_spend_12m_thousand_krw", "domestic_spend_yoy_pct", "spend_per_visitor_krw",
                "overnight_ratio_avg_pct", "avg_stay_days", "avg_stay_minutes", "peak_calendar_month", "observed_month_count",
                "data_quality_status", "source_ids_json", "visitors_12m_percentile", "spend_per_visitor_krw_percentile",
                "overnight_ratio_avg_pct_percentile", "avg_stay_days_percentile",
            )
            for batch in _batched((
                tuple(_nullable(row.get(column)) for column in context_columns) for row in planning_rows
            )):
                cursor.executemany(context_sql, batch)

            peer_sql = """
                INSERT INTO regional_peer_comparison (
                    region_code, peer_rank, peer_region_code, distance, visitors_gap_pct, spend_per_visitor_gap_krw,
                    overnight_ratio_gap_pct_point, comparison_period_end, method
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE peer_region_code=VALUES(peer_region_code), distance=VALUES(distance),
                    visitors_gap_pct=VALUES(visitors_gap_pct), spend_per_visitor_gap_krw=VALUES(spend_per_visitor_gap_krw),
                    overnight_ratio_gap_pct_point=VALUES(overnight_ratio_gap_pct_point), comparison_period_end=VALUES(comparison_period_end), method=VALUES(method)
            """
            peer_columns = (
                "region_code", "peer_rank", "peer_region_code", "distance", "visitors_gap_pct", "spend_per_visitor_gap_krw",
                "overnight_ratio_gap_pct_point", "comparison_period_end", "method",
            )
            for batch in _batched((
                tuple(_nullable(row.get(column)) for column in peer_columns) for row in peer_rows
            )):
                cursor.executemany(peer_sql, batch)

            cursor.execute(
                """UPDATE data_load_run SET status='validated', completed_at=%s, loaded_row_count=%s,
                filtered_row_count=0, rejected_row_count=0 WHERE load_run_id=%s""",
                (datetime.now(timezone.utc), len(rows["fact_tourism_monthly.csv"]), load_run_id),
            )
        connection.commit()
    return {
        "load_run_id": load_run_id,
        "regions": len(rows["dim_region.csv"]),
        "sources": len(rows["data_source.csv"]),
        "monthly_rows": len(rows["fact_tourism_monthly.csv"]),
        "metric_source_rows": len(rows["fact_tourism_metric_source.csv"]),
        "planning_context_rows": len(planning_rows),
        "peer_rows": len(peer_rows),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전국 관광 MySQL 적재 묶음 검증·적재")
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--context-dir", type=Path, default=DEFAULT_CONTEXT_DIR)
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--apply", action="store_true", help="명시할 때만 MySQL에 upsert합니다.")
    parser.add_argument("--apply-schema", action="store_true", help="--apply와 함께 schema CREATE TABLE을 실행합니다.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = validate_bundle(args.bundle_dir)
        if not args.apply:
            print(json.dumps({"status": "dry_run_ok", **{name: len(items) for name, items in rows.items()}}, ensure_ascii=False))
            return 0
        result = import_bundle(
            bundle_dir=args.bundle_dir,
            context_dir=args.context_dir,
            schema_path=args.schema_path,
            apply_schema=args.apply_schema,
        )
    except (BundleValidationError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "imported", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
