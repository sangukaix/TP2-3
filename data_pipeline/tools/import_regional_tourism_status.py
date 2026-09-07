"""정규화한 지역별 관광 현황 근거를 MySQL에 트랜잭션으로 적재한다.

기본은 dry-run이며 ``--apply``가 있을 때만 DB를 바꾼다. 기존 월별 수요 사실과
분리된 보조 테이블에만 적재해, 인기 순위·30일 집중 신호가 ML target으로 섞이지 않게 한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from .import_mysql_bundle import _batched, _connect, _execute_schema, _nullable, mysql_config_from_env
except ModuleNotFoundError:  # pragma: no cover - tools 폴더 직접 실행
    from import_mysql_bundle import _batched, _connect, _execute_schema, _nullable, mysql_config_from_env


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGING_DIR = PROJECT_ROOT / "data" / "processed" / "regional_tourism_status"
DEFAULT_REGION_CODES = (
    PROJECT_ROOT / "data" / "processed" / "nationwide" / "materialized_region_reference" / "official_municipality_codes.csv"
)
DEFAULT_BASE_SCHEMA = PROJECT_ROOT / "database" / "mysql" / "001_nationwide_tourism_data.sql"
DEFAULT_STATUS_SCHEMA = PROJECT_ROOT / "database" / "mysql" / "002_regional_tourism_status.sql"

REQUIRED_FILES = {
    "source_records.csv": {"source_id", "file_name", "file_hash", "geographic_level", "review_status"},
    "source_lineage.csv": {"parent_source_id", "child_source_id", "relation_type"},
    "flow_distribution.csv": {"region_code", "source_period", "direction", "related_region_name", "ratio_pct", "rank_no", "source_id"},
    "flow_destination_types.csv": {"region_code", "source_period", "direction", "dataset_type", "category_group", "share_pct", "source_id"},
    "place_records.csv": {"region_code", "source_period", "dataset_type", "audience", "place_name", "metric_name", "metric_unit", "source_id"},
    "concentration_records.csv": {"region_code", "signal_date", "visit_ratio_pct", "source_id"},
}


class StatusBundleValidationError(ValueError):
    """staging 파일·요약·공식 지역 코드가 불일치할 때 사용한다."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise StatusBundleValidationError(f"헤더가 없습니다: {path.name}")
        return list(reader)


def _read_bundle(staging_dir: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    summary_path = staging_dir / "summary.json"
    if not summary_path.is_file():
        raise StatusBundleValidationError("summary.json이 없습니다.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "ready_for_regional_tourism_status_import":
        raise StatusBundleValidationError("지역별 관광 현황 staging이 적재 준비 상태가 아닙니다.")
    rows_by_file: dict[str, list[dict[str, str]]] = {}
    for file_name, required_columns in REQUIRED_FILES.items():
        path = staging_dir / file_name
        if not path.is_file():
            raise StatusBundleValidationError(f"필수 파일이 없습니다: {file_name}")
        rows = _read_csv(path)
        available = set(rows[0]) if rows else set(_read_csv_header(path))
        missing = required_columns - available
        if missing:
            raise StatusBundleValidationError(f"{file_name} 필수 열 누락: {', '.join(sorted(missing))}")
        rows_by_file[file_name] = rows
    expected_counts = {
        "source_records.csv": "source_record_count",
        "flow_distribution.csv": "flow_distribution_count",
        "flow_destination_types.csv": "flow_destination_type_count",
        "place_records.csv": "place_record_count",
        "concentration_records.csv": "concentration_record_count",
    }
    for file_name, summary_key in expected_counts.items():
        if int(summary.get(summary_key, -1)) != len(rows_by_file[file_name]):
            raise StatusBundleValidationError(f"summary 행 수 불일치: {file_name}")
    return rows_by_file, summary


def _read_csv_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return next(csv.reader(stream), [])


def _load_regions(path: Path, used_codes: set[str]) -> list[dict[str, str]]:
    rows = _read_csv(path)
    result = []
    for row in rows:
        code = str(row.get("region_code") or "")
        if code not in used_codes:
            continue
        province = str(row.get("province_name") or "")
        full_name = str(row.get("official_full_name") or "")
        municipality = str(row.get("municipality_name") or "")
        hierarchy = full_name.removeprefix(province).strip() or municipality
        if not province or not municipality or not hierarchy:
            raise StatusBundleValidationError(f"공식 지역 코드 정보가 부족합니다: {code}")
        result.append({
            "region_code": code,
            "province_name": province,
            "municipality_name": municipality,
            "local_hierarchy_name": hierarchy,
        })
    missing = used_codes - {row["region_code"] for row in result}
    if missing:
        raise StatusBundleValidationError(f"공식 지역 코드표에 없는 코드: {', '.join(sorted(missing))}")
    return result


def _bundle_hash(staging_dir: Path) -> str:
    return hashlib.sha256((staging_dir / "summary.json").read_bytes()).hexdigest()


def _execute_schemas(cursor: Any, base_schema: Path, status_schema: Path) -> None:
    """상태 테이블의 FK가 기존 기본 테이블을 참조하므로 순서대로 적용한다."""

    _execute_schema(cursor, base_schema)
    _execute_schema(cursor, status_schema)


def _empty_to_none(value: str | None) -> str | None:
    return _nullable(value)


def import_regional_tourism_status(
    *, staging_dir: Path, region_codes_path: Path, base_schema: Path, status_schema: Path, apply_schema: bool
) -> dict[str, int]:
    """검증된 결과만 한 트랜잭션에서 source→facts 순서로 upsert한다."""

    rows, summary = _read_bundle(staging_dir)
    used_codes = {
        row["region_code"]
        for file_name in ("flow_distribution.csv", "flow_destination_types.csv", "place_records.csv", "concentration_records.csv")
        for row in rows[file_name]
    }
    regions = _load_regions(region_codes_path, used_codes)
    config = mysql_config_from_env()
    raw_row_count = sum(len(rows[name]) for name in REQUIRED_FILES if name != "source_records.csv")

    with _connect(config) as connection:
        with connection.cursor() as cursor:
            if apply_schema:
                _execute_schemas(cursor, base_schema, status_schema)
            cursor.execute(
                """
                INSERT INTO data_load_run (raw_snapshot, inventory_hash, started_at, status, source_file_count, raw_row_count)
                VALUES (%s, %s, %s, 'running', %s, %s)
                """,
                (
                    f"regional_tourism_status_{summary.get('snapshot_sha256', '')[:16]}",
                    _bundle_hash(staging_dir),
                    datetime.now(timezone.utc),
                    len(rows["source_records.csv"]),
                    raw_row_count,
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
                for row in regions
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
            source_columns = ("source_id", "source_name", "source_page_url", "downloaded_at", "file_name", "file_hash", "date_range", "geographic_level", "filters_json", "methodology_notes", "review_status")
            for batch in _batched((tuple(_empty_to_none(row.get(column)) for column in source_columns) for row in rows["source_records.csv"])):
                cursor.executemany(source_sql, batch)

            lineage_sql = """
                INSERT INTO data_source_lineage (parent_source_id, child_source_id, relation_type)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE relation_type=VALUES(relation_type)
            """
            for batch in _batched((
                (row["parent_source_id"], row["child_source_id"], row["relation_type"])
                for row in rows["source_lineage.csv"]
            )):
                cursor.executemany(lineage_sql, batch)

            flow_sql = """
                INSERT INTO regional_tourism_status_flow
                (region_code, source_period, direction, related_region_name, ratio_pct, rank_no, source_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE ratio_pct=VALUES(ratio_pct), rank_no=VALUES(rank_no)
            """
            for batch in _batched((
                (row["region_code"], row["source_period"], row["direction"], row["related_region_name"], row["ratio_pct"], row["rank_no"], row["source_id"])
                for row in rows["flow_distribution.csv"]
            )):
                cursor.executemany(flow_sql, batch)

            type_sql = """
                INSERT INTO regional_tourism_status_flow_category
                (region_code, source_period, direction, dataset_type, category_group, category_detail, share_pct, group_share_pct, source_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE share_pct=VALUES(share_pct), group_share_pct=VALUES(group_share_pct)
            """
            for batch in _batched((
                (row["region_code"], row["source_period"], row["direction"], row["dataset_type"], row["category_group"], row.get("category_detail") or "", row["share_pct"], _empty_to_none(row.get("group_share_pct")), row["source_id"])
                for row in rows["flow_destination_types.csv"]
            ), size=1000):
                cursor.executemany(type_sql, batch)

            place_sql = """
                INSERT INTO regional_tourism_status_place
                (region_code, source_period, dataset_type, audience, language, place_id, place_name, classification,
                 rank_no, observation_month, metric_name, metric_value, metric_unit, source_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE classification=VALUES(classification), rank_no=VALUES(rank_no),
                    metric_name=VALUES(metric_name), metric_value=VALUES(metric_value), metric_unit=VALUES(metric_unit)
            """
            for batch in _batched((
                (row["region_code"], row["source_period"], row["dataset_type"], row["audience"], row.get("language") or "", row.get("place_id") or "", row["place_name"], row.get("classification") or "", _empty_to_none(row.get("rank_no")), row.get("observation_month") or "", row["metric_name"], _empty_to_none(row.get("metric_value")), row["metric_unit"], row["source_id"])
                for row in rows["place_records.csv"]
            ), size=1000):
                cursor.executemany(place_sql, batch)

            concentration_sql = """
                INSERT INTO regional_tourism_status_concentration (region_code, signal_date, visit_ratio_pct, source_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE visit_ratio_pct=VALUES(visit_ratio_pct)
            """
            for batch in _batched((
                (row["region_code"], row["signal_date"], row["visit_ratio_pct"], row["source_id"])
                for row in rows["concentration_records.csv"]
            )):
                cursor.executemany(concentration_sql, batch)

            loaded = raw_row_count
            cursor.execute(
                """
                UPDATE data_load_run
                SET completed_at=%s, status='validated', loaded_row_count=%s, filtered_row_count=%s, rejected_row_count=0
                WHERE load_run_id=%s
                """,
                (datetime.now(timezone.utc), loaded, 0, load_run_id),
            )
        connection.commit()
    return {
        "load_run_id": load_run_id,
        "region_count": len(regions),
        "source_count": len(rows["source_records.csv"]),
        "flow_count": len(rows["flow_distribution.csv"]),
        "flow_category_count": len(rows["flow_destination_types.csv"]),
        "place_count": len(rows["place_records.csv"]),
        "concentration_count": len(rows["concentration_records.csv"]),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지역별 관광 현황 MySQL 적재")
    parser.add_argument("--staging-dir", default=str(DEFAULT_STAGING_DIR))
    parser.add_argument("--region-codes", default=str(DEFAULT_REGION_CODES))
    parser.add_argument("--base-schema", default=str(DEFAULT_BASE_SCHEMA))
    parser.add_argument("--status-schema", default=str(DEFAULT_STATUS_SCHEMA))
    parser.add_argument("--apply", action="store_true", help="명시할 때만 MySQL을 변경합니다.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows, _ = _read_bundle(Path(args.staging_dir))
        if not args.apply:
            print(json.dumps({"status": "dry_run_ok", "files": {name: len(value) for name, value in rows.items()}}, ensure_ascii=False, indent=2))
            return 0
        result = import_regional_tourism_status(
            staging_dir=Path(args.staging_dir),
            region_codes_path=Path(args.region_codes),
            base_schema=Path(args.base_schema),
            status_schema=Path(args.status_schema),
            apply_schema=True,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
