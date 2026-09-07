"""Hash-verified direct Data Lab CSV snapshots into monthly comparison staging.

The nationwide ZIP pipeline and the local direct-CSV snapshots use the same
official Data Lab tables but differ in their packaging.  This module keeps the
metric definitions identical to :mod:`build_monthly_staging`, validates every
file against a materialization manifest, and emits the same staging schema.

It intentionally does *not* use the ML-ready table as a shortcut: ML's
``visitors`` target is the unique visitor count, while the nationwide comparison
layer uses visitor headcount (연인원).  Re-reading the official source tables
prevents that semantic mix-up.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

STAGING_FIELDS = [
    "region_code",
    "year_month",
    "province_name",
    "municipality_name",
    "local_hierarchy_name",
    "visitors",
    "visitors_previous_year",
    "visitors_yoy_pct",
    "domestic_tourism_spend_thousand_krw",
    "nonlocal_tourism_spend_thousand_krw",
    "unique_visitors",
    "overnight_ratio_pct",
    "avg_stay_days",
    "avg_stay_minutes",
    "visitors_source_id",
    "visitors_previous_year_source_id",
    "visitors_yoy_pct_source_id",
    "domestic_tourism_spend_thousand_krw_source_id",
    "nonlocal_tourism_spend_thousand_krw_source_id",
    "unique_visitors_source_id",
    "overnight_ratio_pct_source_id",
    "avg_stay_days_source_id",
    "avg_stay_minutes_source_id",
    "missing_metrics",
    "data_status",
]

METRICS = (
    "visitors",
    "visitors_previous_year",
    "visitors_yoy_pct",
    "domestic_tourism_spend_thousand_krw",
    "nonlocal_tourism_spend_thousand_krw",
    "unique_visitors",
    "overnight_ratio_pct",
    "avg_stay_days",
    "avg_stay_minutes",
)


def _compact(value: str) -> str:
    return "".join(str(value).split())


def _read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"DIRECT_CSV_ENCODING: {path}")


def _number(value: object) -> str:
    raw = str(value or "").replace(",", "").strip()
    if not raw:
        raise InvalidOperation("빈 수치")
    number = Decimal(raw)
    if not number.is_finite():
        raise InvalidOperation("유한하지 않은 수치")
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _month(value: object) -> str:
    raw = str(value or "").strip().replace("-", "")
    if len(raw) != 6 or not raw.isdigit():
        raise ValueError(f"DIRECT_CSV_INVALID_MONTH: {value}")
    return f"{raw[:4]}-{raw[4:]}"


def _month_column(frame: pd.DataFrame) -> str:
    for candidate in ("기준연월", "기준년월"):
        if candidate in frame.columns:
            return candidate
    raise ValueError("DIRECT_CSV_MONTH_COLUMN_MISSING")


def _value_column(frame: pd.DataFrame, *candidates: str) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    raise ValueError(f"DIRECT_CSV_VALUE_COLUMN_MISSING: {candidates}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _find_table(folder: Path, title: str) -> Path:
    normalized = _compact(title)
    matches = [
        path
        for path in folder.glob("*.csv")
        if normalized in _compact(path.name) and "전국대비" not in _compact(path.name)
    ]
    if not matches:
        raise FileNotFoundError(f"DIRECT_CSV_TABLE_MISSING: {folder}/{title}")
    if len(matches) != 1:
        raise ValueError(f"DIRECT_CSV_TABLE_AMBIGUOUS: {folder}/{title}: {[path.name for path in matches]}")
    return matches[0]


def _source_id(relative_path: str, content_hash: str) -> str:
    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"datalab-snapshot:{path_hash}:{content_hash[:12]}"


def _load_catalog_entry(catalog_path: Path, region_code: str) -> dict[str, str]:
    with catalog_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    matches = [
        row
        for row in rows
        if row.get("region_code") == region_code
        and str(row.get("enabled", "")).strip().lower() == "true"
        and row.get("adapter_type") == "standard_datalab_csv"
    ]
    if len(matches) != 1:
        raise ValueError(f"DIRECT_CSV_ACTIVE_CATALOG_ENTRY_REQUIRED: {region_code}")
    return matches[0]


def _load_manifest(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    result: dict[str, str] = {}
    for row in rows:
        relative = str(row.get("materialized_relative_path", "")).replace("\\", "/")
        digest = str(row.get("materialized_sha256", "")).lower()
        if relative and digest:
            result[relative] = digest
    if not result:
        raise ValueError("DIRECT_CSV_SNAPSHOT_MANIFEST_EMPTY")
    return result


def _administrative_names(region_name: str) -> tuple[str, str, str]:
    parts = region_name.split()
    if len(parts) < 2:
        raise ValueError(f"DIRECT_CSV_REGION_NAME_INVALID: {region_name}")
    province = parts[0]
    hierarchy = " ".join(parts[1:])
    municipality = parts[1] if len(parts) > 2 and parts[1].endswith("시") else hierarchy
    return province, municipality, hierarchy


def _is_target_region(row: dict[str, object], entry: dict[str, str]) -> bool:
    name = str(row.get("지역명", "")).strip()
    if not name:
        return True
    source_name = " ".join(entry["region_name"].split(maxsplit=1)[1:])
    return name in {entry["short_name"], source_name, entry["region_name"]}


def _put_values(
    records: dict[str, dict[str, str]],
    frame: pd.DataFrame,
    source_path: Path,
    entry: dict[str, str],
    metric_columns: dict[str, str],
    predicate: Callable[[dict[str, object]], bool],
    source_rows: dict[str, dict[str, str]],
) -> None:
    month_column = _month_column(frame)
    relative = source_path.relative_to(PROJECT_ROOT).as_posix()
    content_hash = _sha256(source_path)
    source = _source_id(relative, content_hash)
    selected_months: set[str] = set()

    for raw_row in frame.to_dict("records"):
        if not predicate(raw_row):
            continue
        month = _month(raw_row.get(month_column))
        record = records.setdefault(month, {})
        for metric, column in metric_columns.items():
            value = _number(raw_row.get(column))
            previous = record.get(metric)
            if previous is not None and previous != value:
                raise ValueError(f"DIRECT_CSV_CONFLICTING_METRIC: {entry['region_code']} {month} {metric}")
            record[metric] = value
            record[f"{metric}_source_id"] = source
        selected_months.add(month)

    if not selected_months:
        raise ValueError(f"DIRECT_CSV_TARGET_ROW_MISSING: {source_path}")
    source_rows[source] = {
        "source_id": source,
        "source_name": f"{entry['source_name']} 공식 다운로드 (hash 검증 snapshot)",
        "source_page_url": entry["source_url"],
        "downloaded_at": entry["downloaded_at"],
        "file_name": relative,
        "file_hash": content_hash,
        "date_range": f"{min(selected_months)} ~ {max(selected_months)}",
        "geographic_level": "시군구",
        "filters": json.dumps(
            {"region_code": entry["region_code"], "metrics": sorted(metric_columns)},
            ensure_ascii=False,
        ),
        "methodology_notes": (
            "원본 CSV를 수정하지 않고 hash 검증 snapshot에서 직접 표준화. "
            f"provenance_status={entry['provenance_status']}"
        ),
    }


def build_direct_csv_staging(
    *,
    catalog_path: Path,
    region_code: str,
    snapshot_manifest_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Build a source-traceable staging delta for one active direct-CSV region."""

    entry = _load_catalog_entry(catalog_path, region_code)
    raw_root = PROJECT_ROOT / entry["raw_relative_path"]
    if not raw_root.is_dir():
        raise FileNotFoundError(f"DIRECT_CSV_SNAPSHOT_ROOT_MISSING: {raw_root}")
    manifest = _load_manifest(snapshot_manifest_path)
    records: dict[str, dict[str, str]] = {}
    source_rows: dict[str, dict[str, str]] = {}

    table_specs = [
        (
            "방문자",
            "방문자 수(연인원) 추이",
            lambda frame: {
                "visitors": _value_column(frame, "방문자수"),
                "visitors_previous_year": _value_column(frame, "전년동월방문자수"),
                "visitors_yoy_pct": _value_column(frame, "방문자수증감률"),
            },
            lambda _: True,
        ),
        (
            "관광소비",
            "관광소비 추이_내국인",
            lambda frame: {"domestic_tourism_spend_thousand_krw": _value_column(frame, "소비액(천원)")},
            lambda row: str(row.get("업종대분류명", "")).strip() == "전체",
        ),
        (
            "관광소비",
            "관광소비 추이_외지인",
            lambda frame: {"nonlocal_tourism_spend_thousand_krw": _value_column(frame, "소비액(천원)")},
            lambda row: str(row.get("업종대분류명", "")).strip() == "전체",
        ),
        (
            "숙박_체류시간",
            "순 방문자 수 및 숙박 비율",
            lambda frame: {
                "unique_visitors": _value_column(frame, "순 방문자수"),
                "overnight_ratio_pct": _value_column(frame, "숙박자 비율"),
            },
            lambda _: True,
        ),
        (
            "숙박_체류시간",
            "평균 숙박일",
            lambda frame: {"avg_stay_days": _value_column(frame, "평균 숙박일수")},
            lambda _: True,
        ),
        (
            "숙박_체류시간",
            "평균 체류시간 추이",
            lambda frame: {"avg_stay_minutes": _value_column(frame, "체류시간(분)")},
            lambda row: _is_target_region(row, entry),
        ),
    ]

    # Direct snapshots are grouped by observation year; every metric must exist
    # for a month before it is admitted to the fact table.
    year_sets = [
        {path.name for path in (raw_root / category).iterdir() if path.is_dir() and path.name.isdigit() and len(path.name) == 4}
        for category, *_ in table_specs
    ]
    years = sorted(set.intersection(*year_sets)) if year_sets else []
    if not years:
        raise ValueError(f"DIRECT_CSV_COMMON_YEARS_MISSING: {region_code}")

    for year in years:
        for category, title, column_selector, predicate in table_specs:
            source_path = _find_table(raw_root / category / year, title)
            relative_snapshot = source_path.relative_to(PROJECT_ROOT / "data" / "source_snapshots").as_posix()
            expected_hash = manifest.get(relative_snapshot)
            actual_hash = _sha256(source_path)
            if not expected_hash:
                raise ValueError(f"DIRECT_CSV_MANIFEST_ENTRY_MISSING: {relative_snapshot}")
            if actual_hash.lower() != expected_hash.lower():
                raise ValueError(f"DIRECT_CSV_MANIFEST_HASH_MISMATCH: {relative_snapshot}")
            frame = _read_csv(source_path)
            metric_columns = column_selector(frame)
            _put_values(records, frame, source_path, entry, metric_columns, predicate, source_rows)

    province, municipality, hierarchy = _administrative_names(entry["region_name"])
    staging_rows: list[dict[str, object]] = []
    for month in sorted(records):
        values = records[month]
        missing = [metric for metric in METRICS if not values.get(metric)]
        if missing:
            continue
        staging_rows.append(
            {
                "region_code": region_code,
                "year_month": month,
                "province_name": province,
                "municipality_name": municipality,
                "local_hierarchy_name": hierarchy,
                **{metric: values[metric] for metric in METRICS},
                **{f"{metric}_source_id": values[f"{metric}_source_id"] for metric in METRICS},
                "missing_metrics": "",
                "data_status": "complete",
            }
        )
    if len(staging_rows) < 24:
        raise ValueError(f"DIRECT_CSV_COMMON_MONTHS_INSUFFICIENT: {region_code}={len(staging_rows)}")

    mapping_row = {
        "region_folder": entry["raw_relative_path"].replace("/", "_"),
        "province_name": province,
        "municipality_name": municipality,
        "local_hierarchy_name": hierarchy,
        "region_code_candidates_json": json.dumps([region_code]),
        "mapping_status": "validated_from_datalab",
        "official_region_code": region_code,
        "review_note": "활성 서비스 카탈로그의 한국관광 데이터랩 지역코드를 재사용; exact download URL은 추후 보강 필요",
        "mapping_method": "active_service_catalog_with_snapshot_hash_validation",
        "official_reference_name": entry["region_name"],
        "canonical_province_name": province,
        "canonical_municipality_name": municipality,
        "canonical_local_hierarchy_name": hierarchy,
    }
    mapping_fields = list(mapping_row)
    source_fields = [
        "source_id", "source_name", "source_page_url", "downloaded_at", "file_name", "file_hash",
        "date_range", "geographic_level", "filters", "methodology_notes",
    ]
    _write_csv(output_dir / "tourism_monthly_staging.csv", STAGING_FIELDS, staging_rows)
    _write_csv(output_dir / "region_mapping_validated.csv", mapping_fields, [mapping_row])
    _write_csv(output_dir / "source_registry_generated.csv", source_fields, [source_rows[key] for key in sorted(source_rows)])

    summary: dict[str, object] = {
        "region_code": region_code,
        "region_name": entry["region_name"],
        "monthly_row_count": len(staging_rows),
        "period_start": staging_rows[0]["year_month"],
        "period_end": staging_rows[-1]["year_month"],
        "source_file_count": len(source_rows),
        "snapshot_manifest_verified": True,
        "provenance_status": entry["provenance_status"],
        "status": "ready_for_merge",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="직접 CSV snapshot의 전국 비교용 월별 staging 생성")
    parser.add_argument("--region-code", required=True)
    parser.add_argument("--catalog", type=Path, default=PROJECT_ROOT / "data" / "catalog" / "region_data_registry.csv")
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_direct_csv_staging(
            catalog_path=args.catalog,
            region_code=args.region_code,
            snapshot_manifest_path=args.snapshot_manifest,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, InvalidOperation, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
