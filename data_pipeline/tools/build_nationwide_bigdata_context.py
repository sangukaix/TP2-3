"""전국 빅데이터 다운로드를 비교 근거와 전국 월별 맥락으로 분리해 정규화한다.

시군구 표는 기간 합계/비중만 있으므로 ``fact_tourism_monthly`` 및 ML target에 넣지
않는다. 전국 월별 추이도 지역별 수치가 아니므로 지역 수요 예측의 feature로 자동 사용하지
않는다. 두 결과는 기획서의 범위가 명확한 보조 근거다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from .data_inventory import decode_csv
except ModuleNotFoundError:  # pragma: no cover - direct CLI execution
    from data_inventory import decode_csv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAPPING = PROJECT_ROOT / "data" / "processed" / "nationwide" / "materialized_region_reference" / "official_municipality_codes.csv"
PERIOD_RE = re.compile(r"(?P<start_year>20\d{2})(?P<start_month>0[1-9]|1[0-2])?-(?P<end_year>20\d{2})(?P<end_month>0[1-9]|1[0-2])?")
YEAR_MONTH_RE = re.compile(r"^(20\d{2})[-./년\s]*(0?[1-9]|1[0-2])(?:월)?$")
PROVINCE_ALIASES = {
    "강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도",
    "세종시": "세종특별자치시", "서울시": "서울특별시", "부산시": "부산광역시",
    "대구시": "대구광역시", "인천시": "인천광역시", "광주시": "광주광역시",
    "대전시": "대전광역시", "울산시": "울산광역시",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_id(file_hash: str, relative_path: str) -> str:
    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"team-bigdata:{path_hash}:{file_hash[:12]}"


def normal_number(value: Any) -> str:
    cleaned = str(value or "").strip().replace(",", "")
    if not cleaned:
        return ""
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"NUMBER_INVALID: {value}") from exc
    if not number.is_finite():
        raise ValueError(f"NUMBER_NOT_FINITE: {value}")
    normalized = format(number, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def normalize_province(value: str) -> str:
    name = str(value or "").strip()
    return PROVINCE_ALIASES.get(name, name)


def normalize_year_month(value: Any) -> str | None:
    cleaned = str(value or "").strip().replace(" ", "")
    if re.fullmatch(r"20\d{4}", cleaned):
        return f"{cleaned[:4]}-{cleaned[4:]}"
    match = YEAR_MONTH_RE.match(cleaned)
    return f"{match.group(1)}-{int(match.group(2)):02d}" if match else None


def parse_period(relative_path: str) -> tuple[str, str, str]:
    match = PERIOD_RE.search(relative_path)
    if not match:
        raise ValueError(f"PERIOD_NOT_FOUND: {relative_path}")
    start_month = match.group("start_month") or "01"
    end_month = match.group("end_month") or "12"
    start = f"{match.group('start_year')}-{start_month}"
    end = f"{match.group('end_year')}-{end_month}"
    kind = "annual" if start_month == "01" and end_month == "12" and match.group("start_year") == match.group("end_year") else "partial_period"
    return start, end, kind


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _rows_from_zip(path: Path) -> list[tuple[str, list[dict[str, str]]]]:
    rows: list[tuple[str, list[dict[str, str]]]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".csv"):
                continue
            text, _ = decode_csv(archive.read(info))
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                raise ValueError(f"CSV_HEADER_MISSING: {path.name}/{info.filename}")
            rows.append((Path(info.filename).name, list(reader)))
    if not rows:
        raise ValueError(f"ZIP_CSV_MISSING: {path.name}")
    return rows


def _dataset_context(relative_path: str) -> tuple[str, str]:
    lowered = relative_path.replace("\\", "/")
    audience = "foreign" if "/외국인/" in lowered else "domestic" if "/내국인/" in lowered else "all"
    if "네비게이션" in lowered:
        return "navigation", audience
    if "신용카드" in lowered:
        return "credit_card", audience
    if "이동통신" in lowered:
        return "mobile", audience
    raise ValueError(f"DATASET_GROUP_UNKNOWN: {relative_path}")


def load_region_map(path: Path) -> dict[tuple[str, str], str]:
    if not path.is_file():
        raise FileNotFoundError(f"OFFICIAL_REGION_MAPPING_MISSING: {path}")
    mapping: dict[tuple[str, str], str] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            province, municipality = normalize_province(row.get("province_name", "")), str(row.get("municipality_name") or "").strip()
            region_code = str(row.get("region_code") or "").strip()
            if province and municipality and region_code:
                key = (province, municipality)
                if key in mapping and mapping[key] != region_code:
                    raise ValueError(f"OFFICIAL_REGION_MAPPING_CONFLICT: {key}")
                mapping[key] = region_code
    return mapping


def _municipal_rows(
    rows: list[dict[str, str]], *, relative_path: str, source: str, period_start: str, period_end: str,
    period_kind: str, region_map: dict[tuple[str, str], str], csv_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    group, audience = _dataset_context(relative_path)
    if "검색건수" in csv_name:
        metric, value_key, share_key, unit = "navigation_searches", "기초지자체 검색건수", "기초지자체 검색건수 비율", "건"
    elif "방문자 수" in csv_name or "방문자수" in csv_name:
        metric, value_key, share_key, unit = "visitors", "기초지자체 방문자 수", "기초지자체 방문자 비율", "명"
    elif "지출액" in csv_name:
        metric, value_key, share_key, unit = "tourism_spend", "", "기초지자체 지출액 비율(%)", "비율"
    else:
        return [], []
    output: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for row_no, row in enumerate(rows, start=2):
        province = normalize_province(_first(row, "광역지자체명", "광역지자체 명", "광역지자체"))
        municipality = _first(row, "기초지자체명", "기초지자체 명", "기초지자체")
        if not province or not municipality:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "REGION_NAME_MISSING", "detail": "광역/기초지자체명이 없습니다."})
            continue
        region_code = region_map.get((province, municipality))
        if not region_code:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "OFFICIAL_REGION_CODE_UNMAPPED", "detail": f"{province} {municipality}"})
            continue
        try:
            value = normal_number(row.get(value_key, "")) if value_key else ""
            share = normal_number(_first(row, share_key, share_key.replace("(%)", ""), "기초지자체 지출액 비율"))
        except ValueError as exc:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "METRIC_NUMBER_INVALID", "detail": str(exc)})
            continue
        if not value and not share:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "METRIC_VALUE_MISSING", "detail": metric})
            continue
        output.append({
            "region_code": region_code, "province_name": province, "municipality_name": municipality,
            "metric_name": metric, "audience": audience, "dataset_group": group,
            "period_start": period_start, "period_end": period_end, "period_kind": period_kind,
            "metric_value": value, "unit": unit, "share_pct": share,
            "source_id": source, "source_row_number": row_no,
        })
    return output, rejected


def _monthly_rows(
    rows: list[dict[str, str]], *, relative_path: str, source: str, as_of_month: str, csv_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    group, audience = _dataset_context(relative_path)
    if "검색건수 추이" in csv_name:
        metric, value_key, category_key, unit = "navigation_searches", "광역지자체 검색건수", "카테고리중분류명", "건"
    elif "관광소비 추이" in csv_name:
        metric, value_key, category_key, unit = "tourism_spend", "지출액(천원)", "중분류", "천원"
    elif "외국인 방문자 수 추이" in csv_name:
        metric, value_key, category_key, unit, audience = "visitors", "외국인 방문자수", "", "명", "foreign"
    elif "방문자 수 추이" in csv_name:
        metric, value_key, category_key, unit = "visitors", "방문자 수", "방문자 구분", "명"
    else:
        return [], []
    output: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for row_no, row in enumerate(rows, start=2):
        year_month = normalize_year_month(_first(row, "기준년월", "날짜", "년월"))
        if not year_month:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "YEAR_MONTH_INVALID", "detail": str(row)[:180]})
            continue
        # 이 snapshot은 2026-06 관측분까지라는 팀 제공 범위로 고정한다. 미래/후속 값은 명시적 재검증 전 제외한다.
        if year_month > as_of_month:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "AFTER_AS_OF_MONTH_EXCLUDED", "detail": year_month})
            continue
        national_name = _first(row, "광역지자체", "지역")
        if national_name and national_name not in {"전국", "대한민국"}:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "NOT_NATIONWIDE_MONTHLY_CONTEXT", "detail": national_name})
            continue
        try:
            value = normal_number(row.get(value_key, ""))
        except ValueError as exc:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "METRIC_NUMBER_INVALID", "detail": str(exc)})
            continue
        if not value:
            rejected.append({"source_id": source, "source_row_number": row_no, "error_code": "METRIC_VALUE_MISSING", "detail": metric})
            continue
        output.append({
            "year_month": year_month, "metric_name": metric, "audience": audience,
            "dataset_group": group, "category_name": _first(row, category_key) if category_key else "전체",
            "metric_value": value, "unit": unit, "source_id": source, "source_row_number": row_no,
        })
    return output, rejected


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_nationwide_bigdata_context(*, snapshot_root: Path, mapping_path: Path, output_dir: Path, as_of_month: str = "2026-06") -> dict[str, object]:
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", as_of_month):
        raise ValueError("AS_OF_MONTH_INVALID")
    archives = sorted(snapshot_root.rglob("*.zip"), key=lambda item: item.as_posix())
    if not archives:
        raise FileNotFoundError(f"NATIONWIDE_BIGDATA_SNAPSHOT_MISSING: {snapshot_root}")
    region_map = load_region_map(mapping_path)
    source_records: list[dict[str, object]] = []
    municipal: list[dict[str, object]] = []
    national: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for archive in archives:
        relative = archive.relative_to(snapshot_root).as_posix()
        digest, source = sha256_file(archive), source_id(sha256_file(archive), relative)
        period_start, period_end, period_kind = parse_period(relative)
        source_records.append({
            "source_id": source, "source_name": "한국관광 데이터랩 전국 빅데이터 다운로드",
            "source_page_url": "https://datalab.visitkorea.or.kr/", "downloaded_at": "2026-08-20",
            "file_name": relative, "file_hash": digest, "date_range": f"{period_start}~{period_end}",
            "geographic_level": "시군구 기간집계 및 전국 월별추이",
            "filters_json": json.dumps({"team_snapshot": "20260820", "as_of_month": as_of_month}, ensure_ascii=False),
            "methodology_notes": "팀 제공 다운로드 ZIP. 정확한 데이터랩 다운로드 조건 URL은 아직 기록되지 않아, 기간·단위·집계 수준을 원본 CSV 헤더로 검증했다.",
            "review_status": "needs_exact_download_url",
        })
        for csv_name, rows in _rows_from_zip(archive):
            # 동일 ZIP의 광역시도별·히트맵·거주지 표는 시군구 비교값이 아니다.
            has_municipality_columns = bool(rows and any("기초지자체" in str(column) for column in rows[0]))
            if has_municipality_columns and ("지역별 검색건수" in csv_name or "지역별 방문자" in csv_name or "지역별 지출액" in csv_name):
                values, errors = _municipal_rows(rows, relative_path=relative, source=source, period_start=period_start, period_end=period_end, period_kind=period_kind, region_map=region_map, csv_name=csv_name)
                municipal.extend(values); rejected.extend(errors)
            elif "추이" in csv_name:
                values, errors = _monthly_rows(rows, relative_path=relative, source=source, as_of_month=as_of_month, csv_name=csv_name)
                national.extend(values); rejected.extend(errors)
    if not municipal or not national:
        raise ValueError("NATIONWIDE_BIGDATA_EXPECTED_TABLES_MISSING")
    # 한 source/행은 한 지표여야 한다. 중복은 조용히 덮어쓰지 않는다.
    for label, rows, keys in (
        ("municipal", municipal, ("region_code", "metric_name", "audience", "period_start", "period_end", "source_id")),
        ("national", national, ("year_month", "metric_name", "audience", "category_name", "source_id")),
    ):
        observed = set()
        for row in rows:
            key = tuple(str(row.get(column, "")) for column in keys)
            if key in observed:
                raise ValueError(f"NATIONWIDE_BIGDATA_DUPLICATE_{label.upper()}: {key}")
            observed.add(key)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "source_records.csv", list(source_records[0]), source_records)
    _write_csv(output_dir / "municipal_period_metrics.csv", list(municipal[0]), municipal)
    _write_csv(output_dir / "national_monthly_context.csv", list(national[0]), national)
    _write_csv(output_dir / "rejections.csv", ("source_id", "source_row_number", "error_code", "detail"), rejected)
    blocking_rejections = [
        row for row in rejected
        if row["error_code"] != "OFFICIAL_REGION_CODE_UNMAPPED" or row["detail"] != "세종특별자치시 세종특별자치시"
    ]
    summary = {
        "snapshot_root": str(snapshot_root), "snapshot_archive_count": len(archives), "mapping_file": str(mapping_path),
        "mapping_sha256": sha256_file(mapping_path), "as_of_month": as_of_month,
        "source_record_count": len(source_records), "municipal_period_metric_count": len(municipal),
        "national_monthly_context_count": len(national), "rejection_count": len(rejected),
        "blocking_rejection_count": len(blocking_rejections),
        "excluded_unmapped_region": "세종특별자치시 세종특별자치시 (기존 공식 시군구 코드 참조표에 행이 없어 보조층에서만 제외)",
        "municipal_region_count": len({row["region_code"] for row in municipal}),
        "municipal_metric_counts": dict(Counter(row["metric_name"] for row in municipal)),
        "national_metric_counts": dict(Counter(row["metric_name"] for row in national)),
        "ml_training_usage": "excluded_period_aggregate_and_national_context",
        "rag_usage": "excluded_numeric_tables",
        "status": "ready_for_nationwide_bigdata_mysql_import" if not blocking_rejections else "requires_rejection_review",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전국 빅데이터를 비교/전국 맥락 staging으로 정규화")
    parser.add_argument("--snapshot-root", default="data/source_snapshots/nationwide_bigdata/20260820")
    parser.add_argument("--mapping-path", default=str(DEFAULT_MAPPING))
    parser.add_argument("--output-dir", default="data/processed/nationwide_bigdata")
    parser.add_argument("--as-of-month", default="2026-06")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_nationwide_bigdata_context(snapshot_root=Path(args.snapshot_root), mapping_path=Path(args.mapping_path), output_dir=Path(args.output_dir), as_of_month=args.as_of_month)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
