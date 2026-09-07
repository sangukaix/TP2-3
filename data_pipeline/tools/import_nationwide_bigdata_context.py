"""검증된 전국 빅데이터 보조 근거를 MySQL에 트랜잭션으로 적재한다.

기본은 dry-run이고 ``--apply``를 준 경우에만 DB를 변경한다. 기간합계/비중 표와
전국 월별 표만 적재하며, 월별 지역 fact와 ML artifact에는 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from .import_mysql_bundle import _batched, _connect, _execute_schema, _nullable, mysql_config_from_env
except ModuleNotFoundError:  # pragma: no cover - direct CLI execution
    from import_mysql_bundle import _batched, _connect, _execute_schema, _nullable, mysql_config_from_env


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGING_DIR = PROJECT_ROOT / "data" / "processed" / "nationwide_bigdata"
DEFAULT_REGION_CODES = PROJECT_ROOT / "data" / "processed" / "nationwide" / "materialized_region_reference" / "official_municipality_codes.csv"
DEFAULT_BASE_SCHEMA = PROJECT_ROOT / "database" / "mysql" / "001_nationwide_tourism_data.sql"
DEFAULT_SCHEMA = PROJECT_ROOT / "database" / "mysql" / "003_nationwide_bigdata_context.sql"

REQUIRED_FILES = {
    "source_records.csv": {"source_id", "file_name", "file_hash", "geographic_level", "review_status"},
    "municipal_period_metrics.csv": {"region_code", "metric_name", "audience", "period_start", "period_end", "source_id"},
    "national_monthly_context.csv": {"year_month", "metric_name", "audience", "category_name", "source_id"},
}


class BigdataBundleValidationError(ValueError):
    """staging의 계약·출처·공식 지역코드가 다르면 적재 전에 중단한다."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise BigdataBundleValidationError(f"헤더가 없습니다: {path.name}")
        return list(reader)


def _header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return next(csv.reader(stream), [])


def read_bundle(staging_dir: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    summary_path = staging_dir / "summary.json"
    if not summary_path.is_file():
        raise BigdataBundleValidationError("summary.json이 없습니다.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "ready_for_nationwide_bigdata_mysql_import":
        raise BigdataBundleValidationError("거절 행 또는 검토 미완료 항목이 있어 전국 빅데이터 적재를 중단합니다.")
    if int(summary.get("blocking_rejection_count", 0)):
        raise BigdataBundleValidationError("차단 대상 거절 행이 남아 있어 전국 빅데이터 적재를 중단합니다.")
    rows_by_file: dict[str, list[dict[str, str]]] = {}
    for file_name, required_columns in REQUIRED_FILES.items():
        path = staging_dir / file_name
        if not path.is_file():
            raise BigdataBundleValidationError(f"필수 파일이 없습니다: {file_name}")
        rows = _read_csv(path)
        missing = required_columns - (set(rows[0]) if rows else set(_header(path)))
        if missing:
            raise BigdataBundleValidationError(f"{file_name} 필수 열 누락: {', '.join(sorted(missing))}")
        rows_by_file[file_name] = rows
    expected = {
        "source_records.csv": "source_record_count",
        "municipal_period_metrics.csv": "municipal_period_metric_count",
        "national_monthly_context.csv": "national_monthly_context_count",
    }
    for file_name, key in expected.items():
        if int(summary.get(key, -1)) != len(rows_by_file[file_name]):
            raise BigdataBundleValidationError(f"summary 행 수 불일치: {file_name}")
    return rows_by_file, summary


def _official_regions(path: Path, used_codes: set[str]) -> list[dict[str, str]]:
    rows = _read_csv(path)
    result = []
    for row in rows:
        code = str(row.get("region_code") or "")
        if code not in used_codes:
            continue
        province, municipality = str(row.get("province_name") or ""), str(row.get("municipality_name") or "")
        if not province or not municipality:
            raise BigdataBundleValidationError(f"공식 지역코드 정보가 부족합니다: {code}")
        result.append({"region_code": code, "province_name": province, "municipality_name": municipality, "local_hierarchy_name": municipality})
    missing = used_codes - {row["region_code"] for row in result}
    if missing:
        raise BigdataBundleValidationError(f"공식 지역코드표에 없는 코드: {', '.join(sorted(missing))}")
    return result


def _bundle_hash(staging_dir: Path) -> str:
    return hashlib.sha256((staging_dir / "summary.json").read_bytes()).hexdigest()


def import_nationwide_bigdata_context(*, staging_dir: Path, region_codes_path: Path, base_schema: Path, schema_path: Path, apply_schema: bool) -> dict[str, int]:
    rows, summary = read_bundle(staging_dir)
    municipal = rows["municipal_period_metrics.csv"]
    national = rows["national_monthly_context.csv"]
    used_codes = {row["region_code"] for row in municipal}
    regions = _official_regions(region_codes_path, used_codes)
    source_ids = {row["source_id"] for row in municipal} | {row["source_id"] for row in national}
    source_records = {row["source_id"]: row for row in rows["source_records.csv"]}
    if source_ids - set(source_records):
        raise BigdataBundleValidationError("source_records에 없는 source_id가 있습니다.")
    config = mysql_config_from_env()
    with _connect(config) as connection:
        with connection.cursor() as cursor:
            if apply_schema:
                _execute_schema(cursor, base_schema)
                _execute_schema(cursor, schema_path)
            cursor.execute(
                """INSERT INTO data_load_run (raw_snapshot, inventory_hash, started_at, status, source_file_count, raw_row_count)
                   VALUES (%s, %s, %s, 'running', %s, %s)""",
                (f"nationwide_bigdata_{_bundle_hash(staging_dir)[:16]}", _bundle_hash(staging_dir), datetime.now(timezone.utc), len(source_ids), len(municipal) + len(national)),
            )
            load_run_id = int(cursor.lastrowid)
            region_sql = """
                INSERT INTO dim_region (region_code, province_name, municipality_name, local_hierarchy_name, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON DUPLICATE KEY UPDATE province_name=VALUES(province_name), municipality_name=VALUES(municipality_name),
                    local_hierarchy_name=VALUES(local_hierarchy_name), is_active=TRUE
            """
            for batch in _batched(((row["region_code"], row["province_name"], row["municipality_name"], row["local_hierarchy_name"]) for row in regions)):
                cursor.executemany(region_sql, batch)
            source_sql = """
                INSERT INTO data_source (source_id, source_name, source_page_url, downloaded_at, file_name, file_hash,
                    date_range, geographic_level, filters_json, methodology_notes, review_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE source_name=VALUES(source_name), source_page_url=VALUES(source_page_url),
                    downloaded_at=VALUES(downloaded_at), date_range=VALUES(date_range), filters_json=VALUES(filters_json),
                    methodology_notes=VALUES(methodology_notes), review_status=VALUES(review_status)
            """
            source_columns = ("source_id", "source_name", "source_page_url", "downloaded_at", "file_name", "file_hash", "date_range", "geographic_level", "filters_json", "methodology_notes", "review_status")
            for batch in _batched((tuple(_nullable(source_records[source_id].get(column)) for column in source_columns) for source_id in sorted(source_ids))):
                cursor.executemany(source_sql, batch)
            period_sql = """
                INSERT INTO nationwide_municipal_period_metric
                (region_code, metric_name, audience, dataset_group, period_start, period_end, period_kind, metric_value, unit, share_pct, source_id, source_row_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE dataset_group=VALUES(dataset_group), period_kind=VALUES(period_kind),
                    metric_value=VALUES(metric_value), unit=VALUES(unit), share_pct=VALUES(share_pct), source_row_number=VALUES(source_row_number)
            """
            period_columns = ("region_code", "metric_name", "audience", "dataset_group", "period_start", "period_end", "period_kind", "metric_value", "unit", "share_pct", "source_id", "source_row_number")
            for batch in _batched((tuple(_nullable(row.get(column)) for column in period_columns) for row in municipal)):
                cursor.executemany(period_sql, batch)
            monthly_sql = """
                INSERT INTO nationwide_monthly_tourism_context
                (`year_month`, metric_name, audience, dataset_group, category_name, metric_value, unit, source_id, source_row_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE dataset_group=VALUES(dataset_group), metric_value=VALUES(metric_value),
                    unit=VALUES(unit), source_row_number=VALUES(source_row_number)
            """
            monthly_columns = ("year_month", "metric_name", "audience", "dataset_group", "category_name", "metric_value", "unit", "source_id", "source_row_number")
            for batch in _batched((tuple(_nullable(row.get(column)) for column in monthly_columns) for row in national)):
                cursor.executemany(monthly_sql, batch)
            cursor.execute(
                """UPDATE data_load_run SET status='validated', completed_at=%s, loaded_row_count=%s,
                   filtered_row_count=%s, rejected_row_count=0 WHERE load_run_id=%s""",
                (datetime.now(timezone.utc), len(municipal) + len(national), int(summary.get("rejection_count", 0)), load_run_id),
            )
        connection.commit()
    return {"load_run_id": load_run_id, "region_count": len(regions), "source_count": len(source_ids), "municipal_period_metric_count": len(municipal), "national_monthly_context_count": len(national), "filtered_unmapped_count": int(summary.get("rejection_count", 0))}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전국 빅데이터 보조 근거 MySQL 적재")
    parser.add_argument("--staging-dir", default=str(DEFAULT_STAGING_DIR))
    parser.add_argument("--region-codes", default=str(DEFAULT_REGION_CODES))
    parser.add_argument("--base-schema", default=str(DEFAULT_BASE_SCHEMA))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--apply", action="store_true", help="명시할 때만 MySQL을 변경합니다.")
    parser.add_argument("--apply-schema", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows, _ = read_bundle(Path(args.staging_dir))
        if not args.apply:
            print(json.dumps({"status": "dry_run_ok", **{name: len(value) for name, value in rows.items()}}, ensure_ascii=False))
            return 0
        result = import_nationwide_bigdata_context(staging_dir=Path(args.staging_dir), region_codes_path=Path(args.region_codes), base_schema=Path(args.base_schema), schema_path=Path(args.schema), apply_schema=args.apply_schema)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "imported", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
