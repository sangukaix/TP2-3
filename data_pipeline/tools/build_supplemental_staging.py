"""팀 공유폴더의 보조 관광 CSV를 목적별 staging으로 표준화한다.

원본을 수정하지 않고 관광지 월별 방문객, 인기 관광지, 관광지 연결망,
외래객, 전국·지역 benchmark를 각각 분리한다. 모든 출력 행에는 source_id를 둔다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

try:
    from .data_inventory import decode_csv, normalize_month
except ModuleNotFoundError:  # pragma: no cover - tools 폴더 직접 실행
    from data_inventory import decode_csv, normalize_month


YEAR_RE = re.compile(r"^(20\d{2})$")
KOREAN_MONTH_RE = re.compile(r"^(20\d{2})년\s*(0?[1-9]|1[0-2])월$")


def source_id(file_hash: str, relative_path: str) -> str:
    """상위 저장소 inventory와 같은 안정적인 source ID를 사용한다."""

    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"team-repo:{path_hash}:{file_hash[:12]}"


def attraction_key(province: str, municipality: str, attraction: str) -> str:
    """공식 관광지 ID가 없는 방문객 표를 위한 추적 가능한 임시 자연키다."""

    raw_key = "|".join(part.strip() for part in (province, municipality, attraction))
    return f"name:{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:24]}"


def normalize_number(value: str) -> str:
    """과학 표기·쉼표를 보존 가능한 10진 문자열로 바꾼다."""

    cleaned = str(value or "").strip().replace(",", "")
    if not cleaned:
        return ""
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"숫자 변환 실패: {value}") from exc
    if not number.is_finite():
        raise ValueError(f"유한하지 않은 숫자: {value}")
    normalized = format(number, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def read_dict_rows(path: Path) -> list[dict[str, str]]:
    text, _ = decode_csv(path.read_bytes())
    return list(csv.DictReader(io.StringIO(text)))


def read_csv_rows(path: Path) -> list[list[str]]:
    text, _ = decode_csv(path.read_bytes())
    return list(csv.reader(io.StringIO(text)))


def extract_year(relative_path: str) -> str:
    for part in Path(relative_path).parts:
        if YEAR_RE.match(part):
            return part
    return ""


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_files(inventory_dir: Path) -> list[dict[str, str]]:
    with (inventory_dir / "files.csv").open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


# 같은 hash 파일은 한 번만 변환하되 명시적인 원본 섹션을 우선한다.
def deduplicate_files(files: list[dict[str, str]]) -> list[dict[str, str]]:
    priorities = {
        "지역별 관광지 관광객 현황표": 0,
        "전국 현황": 0,
        "지역별 관광현황": 1,
        "(root)": 9,
    }
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in files:
        grouped[row["sha256"]].append(row)
    return [
        sorted(group, key=lambda row: (priorities.get(row["section"], 0), row["relative_path"]))[0]
        for group in grouped.values()
    ]


def rejection(
    source: str,
    relative_path: str,
    row_number: int | str,
    code: str,
    detail: str,
) -> dict[str, object]:
    return {
        "source_id": source,
        "relative_path": relative_path,
        "row_number": row_number,
        "error_code": code,
        "detail": detail,
    }


# 2행 헤더의 관광지 방문객 표를 attraction + visitor_type + month 형태로 펼친다.
def transform_attraction_monthly(
    root: Path, file_row: dict[str, str]
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    path = root / Path(file_row["relative_path"])
    rows = read_csv_rows(path)
    source = source_id(file_row["sha256"], file_row["relative_path"])
    output: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    audit = Counter(raw_rows=max(0, len(rows) - 2))
    if len(rows) < 2:
        return output, [rejection(source, file_row["relative_path"], "", "missing_header", "2행 헤더 없음")], dict(audit)

    second_header = rows[1]
    month_by_index: dict[int, str] = {}
    for index, value in enumerate(second_header):
        match = KOREAN_MONTH_RE.match(str(value).strip())
        if match:
            month_by_index[index] = f"{match.group(1)}-{int(match.group(2)):02d}"

    if not month_by_index:
        rejected.append(rejection(source, file_row["relative_path"], 2, "month_header_missing", "월 컬럼 없음"))
        return output, rejected, dict(audit)

    for row_number, row in enumerate(rows[2:], start=3):
        padded = row + [""] * max(0, max(month_by_index) + 1 - len(row))
        province = padded[0].strip() if len(padded) > 0 else ""
        municipality = padded[1].strip() if len(padded) > 1 else ""
        attraction = padded[2].strip() if len(padded) > 2 else ""
        visitor_type = padded[3].strip() if len(padded) > 3 else ""
        # 합계는 내국인+외국인의 중복 요약값이므로 원본 행 감사에는 남기고 fact에는 넣지 않는다.
        if visitor_type == "합계":
            audit["filtered_summary_rows"] += 1
            continue
        if not province or not municipality or not attraction or visitor_type not in {"내국인", "외국인"}:
            audit["rejected_rows"] += 1
            rejected.append(
                rejection(source, file_row["relative_path"], row_number, "invalid_attraction_key", "시도·군구·관광지·내외국인 구분 확인 필요")
            )
            continue
        loaded_for_row = 0
        for column_index, year_month in month_by_index.items():
            raw_value = padded[column_index].strip()
            if not raw_value:
                continue
            try:
                visitors = normalize_number(raw_value)
            except ValueError:
                audit["rejected_values"] += 1
                rejected.append(
                    rejection(source, file_row["relative_path"], row_number, "invalid_attraction_visitors", f"{year_month}={raw_value}")
                )
                continue
            output.append(
                {
                    "province_name": province,
                    "municipality_name": municipality,
                    "attraction_key": attraction_key(province, municipality, attraction),
                    "attraction_name": attraction,
                    "visitor_type": visitor_type,
                    "year_month": year_month,
                    "visitors": visitors,
                    "source_id": source,
                }
            )
            loaded_for_row += 1
        audit["loaded_source_rows" if loaded_for_row else "empty_source_rows"] += 1
        audit["loaded_monthly_values"] += loaded_for_row
    return output, rejected, dict(audit)


# 중심 관광지 표로 관광지 ID→지역 lookup을 만든다.
def transform_attraction_network(
    root: Path, files: list[dict[str, str]]
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, tuple[str, str, str]]]:
    attractions: dict[str, dict[str, object]] = {}
    edges: list[dict[str, object]] = []
    lookup: dict[str, tuple[str, str, str]] = {}
    for file_row in files:
        source = source_id(file_row["sha256"], file_row["relative_path"])
        path = root / Path(file_row["relative_path"])
        for row in read_dict_rows(path):
            if "관광지ID" in row:
                attraction_id = row.get("관광지ID", "").strip()
                if not attraction_id:
                    continue
                record = {
                    "attraction_key": f"official:{attraction_id}",
                    "attraction_id": attraction_id,
                    "province_name": row.get("중심시도명", "").strip(),
                    "municipality_name": row.get("중심시군구명", "").strip(),
                    "attraction_name": row.get("중심관광지명", "").strip(),
                    "category_large": row.get("중심카테고리 명_대", "").strip(),
                    "category_middle": row.get("중심카테고리 명_중", "").strip(),
                    "rank": normalize_number(row.get("순위", "")),
                    "source_id": source,
                }
                attractions.setdefault(attraction_id, record)
                lookup[attraction_id] = (
                    str(record["province_name"]),
                    str(record["municipality_name"]),
                    str(record["attraction_name"]),
                )
            elif "연관관광지ID" in row:
                center_id = row.get("중심관광지ID", "").strip()
                related_id = row.get("연관관광지ID", "").strip()
                if not center_id or not related_id:
                    continue
                edges.append(
                    {
                        "center_attraction_key": f"official:{center_id}",
                        "center_attraction_id": center_id,
                        "center_attraction_name": row.get("중심관광지명", "").strip(),
                        "center_province_name": row.get("중심시도명", "").strip(),
                        "center_municipality_name": row.get("중심시군구명", "").strip(),
                        "related_attraction_key": f"official:{related_id}",
                        "related_attraction_id": related_id,
                        "related_attraction_name": row.get("연관관광지명", "").strip(),
                        "related_province_name": row.get("연관관광지시도명", "").strip(),
                        "related_municipality_name": row.get("연관관광지시군구명", "").strip(),
                        "related_category": row.get("구분", "").strip(),
                        "rank": normalize_number(row.get("순위", "")),
                        "source_id": source,
                    }
                )
                related_record = {
                    "attraction_key": f"official:{related_id}",
                    "attraction_id": related_id,
                    "province_name": row.get("연관관광지시도명", "").strip(),
                    "municipality_name": row.get("연관관광지시군구명", "").strip(),
                    "attraction_name": row.get("연관관광지명", "").strip(),
                    "category_large": "",
                    "category_middle": row.get("구분", "").strip(),
                    "rank": "",
                    "source_id": source,
                }
                attractions.setdefault(related_id, related_record)
                lookup.setdefault(
                    related_id,
                    (
                        str(related_record["province_name"]),
                        str(related_record["municipality_name"]),
                        str(related_record["attraction_name"]),
                    ),
                )
    return list(attractions.values()), edges, lookup


def transform_popularity(
    root: Path,
    files: list[dict[str, str]],
    attraction_lookup: dict[str, tuple[str, str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    output: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for file_row in files:
        path = root / Path(file_row["relative_path"])
        source = source_id(file_row["sha256"], file_row["relative_path"])
        snapshot_year = extract_year(file_row["relative_path"])
        is_hotplace = "핫플레이스" in file_row["relative_path"]
        for row_number, row in enumerate(read_dict_rows(path), start=2):
            attraction_id = row.get("관광지ID", "").strip()
            if not attraction_id:
                rejected.append(rejection(source, file_row["relative_path"], row_number, "missing_attraction_id", "관광지ID 없음"))
                continue
            mapped = attraction_lookup.get(attraction_id, ("", "", ""))
            output.append(
                {
                    "dataset_type": "hotplace_growth" if is_hotplace else "popular_attraction",
                    "snapshot_year": snapshot_year,
                    "year_month": normalize_month(row.get("기준년월", "")),
                    "province_name": row.get("시도명", "").strip() or mapped[0],
                    "municipality_name": row.get("시군구명", "").strip() or mapped[1],
                    "attraction_key": f"official:{attraction_id}",
                    "attraction_id": attraction_id,
                    "attraction_name": row.get("관심지점명", "").strip() or mapped[2],
                    "category": row.get("구분", "").strip(),
                    "age_group": row.get("연령대", "").strip(),
                    "rank": normalize_number(row.get("순위", "")),
                    "value": normalize_number(row.get("성장율", "") or row.get("비율", "")),
                    "value_unit": "growth_pct" if is_hotplace else "share_pct",
                    "region_mapping_status": "direct" if row.get("시도명", "").strip() else ("mapped_by_attraction_id" if mapped[0] else "unresolved"),
                    "source_id": source,
                }
            )
    return output, rejected


# 외래객 파일 8종을 값과 dimension을 보존하는 long format으로 통일한다.
def transform_foreign(
    root: Path, files: list[dict[str, str]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    output: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for file_row in files:
        path = root / Path(file_row["relative_path"])
        source = source_id(file_row["sha256"], file_row["relative_path"])
        snapshot_year = extract_year(file_row["relative_path"])
        name = path.name
        for row_number, row in enumerate(read_dict_rows(path), start=2):
            records: list[tuple[str, str, str, str, str, str, str]] = []
            if "외국인 방문자수" in name:
                records.append(("foreign_visitors", row.get("지역", ""), "", "", row.get("방문자 수", ""), "persons", row.get("기준년월일", "")))
            elif "외국인 관광소비 추이" in name:
                records.append(("foreign_spend", row.get("지역", ""), "", "", row.get("지역 관광소비액(백만원)", ""), "million_krw", row.get("기준년월일", "")))
            elif "국가별 외국인 방문 현황" in name:
                records.append(("foreign_country_visitor_share", "전국", "country", row.get("국가", ""), row.get("방문자 비율", ""), "pct", ""))
            elif "국가별 관광소비 유형" in name:
                records.append(("foreign_country_spend_share", "전국", "country", row.get("국가", ""), row.get("소비 비율", ""), "pct", ""))
            elif "간편결제 국적별" in name:
                records.append(("foreign_quickpay_country_share", "전국", "country", row.get("국적", ""), row.get("비율", ""), "pct", ""))
            elif "간편결제 업종별" in name:
                records.append(("foreign_quickpay_industry_spend", "전국", "industry", row.get("업종", ""), row.get("소비금액(천원)", ""), "thousand_krw", row.get("기준년월", "")))
            elif "업종별 관광소비 추이" in name:
                records.append(("foreign_industry_spend", "전국", "industry", row.get("업종별 구분", ""), row.get("소비액(천원)", ""), "thousand_krw", row.get("기준년월일", "")))
            elif "관광소비 유형" in name:
                records.extend(
                    [
                        ("foreign_category_large_share", "전국", "category_large", row.get("카테고리 대분류", ""), row.get("카테고리 대분류 소비 비율", ""), "pct", ""),
                        ("foreign_category_middle_share", "전국", "category_middle", row.get("카테고리 중분류", ""), row.get("카테고리 중분류 소비 비율", ""), "pct", ""),
                    ]
                )
            for metric, region, dimension_name, dimension_value, raw_value, unit, raw_month in records:
                try:
                    value = normalize_number(raw_value)
                except ValueError:
                    rejected.append(rejection(source, file_row["relative_path"], row_number, "invalid_foreign_metric", f"{metric}={raw_value}"))
                    continue
                output.append(
                    {
                        "snapshot_year": snapshot_year,
                        "year_month": normalize_month(raw_month),
                        "metric_name": metric,
                        "region_name": str(region).strip(),
                        "dimension_name": dimension_name,
                        "dimension_value": str(dimension_value).strip(),
                        "value": value,
                        "unit": unit,
                        "source_id": source,
                    }
                )
    return output, rejected


# 전국·지역 파일은 동일 hash를 제거한 뒤 원래 dimension/metric을 JSON으로 보존한다.
def transform_benchmarks(root: Path, files: list[dict[str, str]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for file_row in files:
        path = root / Path(file_row["relative_path"])
        source = source_id(file_row["sha256"], file_row["relative_path"])
        snapshot_year = extract_year(file_row["relative_path"])
        dataset_name = re.sub(r"^\d+_", "", path.stem)
        for row_number, row in enumerate(read_dict_rows(path), start=2):
            dimensions: dict[str, str] = {}
            metrics: dict[str, str] = {}
            for key, raw_value in row.items():
                value = str(raw_value or "").strip()
                try:
                    numeric = normalize_number(value)
                except ValueError:
                    numeric = ""
                if numeric and key not in {"기준연월", "기준년(월)"}:
                    metrics[key] = numeric
                else:
                    dimensions[key] = value
            output.append(
                {
                    "dataset_name": dataset_name,
                    "snapshot_year": snapshot_year,
                    "row_number": row_number,
                    "dimensions_json": json.dumps(dimensions, ensure_ascii=False, sort_keys=True),
                    "metrics_json": json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                    "source_id": source,
                }
            )
    return output


BENCHMARK_UNITS = {
    "방문자수": "persons",
    "전년동기 방문자수": "persons",
    "방문자수 증감률": "pct",
    "관광지출액 증감률": "pct",
    "증가율(%)": "pct",
    "남성 방문자 비율": "pct",
    "여성 방문자 비율": "pct",
    "관심도": "index",
    "검색건수": "searches",
    "평균 숙박일수": "days",
}


def flatten_benchmark_metrics(
    benchmark_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """JSON 보존본을 MySQL·비교 계산에 알맞은 numeric long format으로 펼친다.

    원본 헤더에 단위가 없는 값은 추정하지 않고 source_defined_unknown으로 남긴다.
    """

    output: list[dict[str, object]] = []
    for record in benchmark_records:
        dimensions = json.loads(str(record["dimensions_json"]))
        metrics = json.loads(str(record["metrics_json"]))
        raw_month = dimensions.get("기준연월", "") or dimensions.get("기준년(월)", "")
        month = normalize_month(str(raw_month))
        for metric_name, value in metrics.items():
            output.append(
                {
                    "dataset_name": record["dataset_name"],
                    "snapshot_year": record["snapshot_year"],
                    "year_month": month,
                    "province_name": dimensions.get("시도명", ""),
                    "municipality_name": dimensions.get("시군구명", ""),
                    "attraction_name": dimensions.get("관광지명", "")
                    or dimensions.get("방문집중지역", ""),
                    "age_group": dimensions.get("연령", ""),
                    "category_large": dimensions.get("중분류", ""),
                    "category_middle": dimensions.get("소분류", ""),
                    "metric_name": metric_name,
                    "metric_value": value,
                    "unit": BENCHMARK_UNITS.get(metric_name, "source_defined_unknown"),
                    "dimensions_json": record["dimensions_json"],
                    "source_id": record["source_id"],
                    "source_row_number": record["row_number"],
                }
            )
    return output


def build_supplemental_staging(root: Path, inventory_dir: Path, output_dir: Path) -> dict[str, object]:
    """보조 자료 전체를 변환하고 source별·행별 결과를 요약한다."""

    all_files = [row for row in load_files(inventory_dir) if row["extension"] == ".csv"]
    unique_files = deduplicate_files(all_files)
    by_section: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in unique_files:
        by_section[row["section"]].append(row)

    network_attractions, network_edges, lookup = transform_attraction_network(
        root, by_section["중심-연관 관광지 지도"]
    )
    popularity, popularity_rejections = transform_popularity(
        root, by_section["인기관광지 현황"], lookup
    )
    foreign, foreign_rejections = transform_foreign(root, by_section["외래객 지역별 방한현황"])

    attraction_monthly: list[dict[str, object]] = []
    attraction_rejections: list[dict[str, object]] = []
    attraction_audits: list[dict[str, object]] = []
    for row in by_section["지역별 관광지 관광객 현황표"]:
        transformed, rejected, audit = transform_attraction_monthly(root, row)
        attraction_monthly.extend(transformed)
        attraction_rejections.extend(rejected)
        attraction_audits.append(
            {
                "source_id": source_id(row["sha256"], row["relative_path"]),
                "relative_path": row["relative_path"],
                **audit,
            }
        )

    benchmark_files = by_section["전국 현황"] + by_section["지역별 관광현황"]
    benchmarks = transform_benchmarks(root, benchmark_files)
    benchmark_metrics = flatten_benchmark_metrics(benchmarks)
    rejections = attraction_rejections + popularity_rejections + foreign_rejections

    write_csv(
        output_dir / "attraction_monthly_visitors.csv",
        ["province_name", "municipality_name", "attraction_key", "attraction_name", "visitor_type", "year_month", "visitors", "source_id"],
        attraction_monthly,
    )
    write_csv(
        output_dir / "attraction_catalog.csv",
        ["attraction_key", "attraction_id", "province_name", "municipality_name", "attraction_name", "category_large", "category_middle", "rank", "source_id"],
        network_attractions,
    )
    write_csv(
        output_dir / "attraction_edges.csv",
        ["center_attraction_key", "center_attraction_id", "center_attraction_name", "center_province_name", "center_municipality_name", "related_attraction_key", "related_attraction_id", "related_attraction_name", "related_province_name", "related_municipality_name", "related_category", "rank", "source_id"],
        network_edges,
    )
    write_csv(
        output_dir / "attraction_popularity.csv",
        ["dataset_type", "snapshot_year", "year_month", "province_name", "municipality_name", "attraction_key", "attraction_id", "attraction_name", "category", "age_group", "rank", "value", "value_unit", "region_mapping_status", "source_id"],
        popularity,
    )
    write_csv(
        output_dir / "foreign_tourism_metrics.csv",
        ["snapshot_year", "year_month", "metric_name", "region_name", "dimension_name", "dimension_value", "value", "unit", "source_id"],
        foreign,
    )
    write_csv(
        output_dir / "benchmark_records.csv",
        ["dataset_name", "snapshot_year", "row_number", "dimensions_json", "metrics_json", "source_id"],
        benchmarks,
    )
    write_csv(
        output_dir / "benchmark_metrics.csv",
        [
            "dataset_name",
            "snapshot_year",
            "year_month",
            "province_name",
            "municipality_name",
            "attraction_name",
            "age_group",
            "category_large",
            "category_middle",
            "metric_name",
            "metric_value",
            "unit",
            "dimensions_json",
            "source_id",
            "source_row_number",
        ],
        benchmark_metrics,
    )
    write_csv(
        output_dir / "load_rejections.csv",
        ["source_id", "relative_path", "row_number", "error_code", "detail"],
        rejections,
    )
    write_csv(
        output_dir / "attraction_source_audit.csv",
        ["source_id", "relative_path", "raw_rows", "loaded_source_rows", "filtered_summary_rows", "empty_source_rows", "loaded_monthly_values", "rejected_rows", "rejected_values"],
        attraction_audits,
    )

    # 내용이 같은 복사본도 어떤 경로에서 왔는지 잃지 않도록 canonical/alias를 기록한다.
    canonical_by_hash = {row["sha256"]: row for row in unique_files}
    alias_rows = [
        {
            "canonical_source_id": source_id(
                canonical_by_hash[row["sha256"]]["sha256"],
                canonical_by_hash[row["sha256"]]["relative_path"],
            ),
            "canonical_relative_path": canonical_by_hash[row["sha256"]]["relative_path"],
            "alias_source_id": source_id(row["sha256"], row["relative_path"]),
            "alias_relative_path": row["relative_path"],
            "sha256": row["sha256"],
        }
        for row in all_files
        if row["relative_path"] != canonical_by_hash[row["sha256"]]["relative_path"]
    ]
    write_csv(
        output_dir / "duplicate_source_aliases.csv",
        ["canonical_source_id", "canonical_relative_path", "alias_source_id", "alias_relative_path", "sha256"],
        alias_rows,
    )

    summary: dict[str, object] = {
        "input_csv_count": len(all_files),
        "unique_csv_hash_count": len(unique_files),
        "duplicate_csv_count": len(all_files) - len(unique_files),
        "attraction_monthly_row_count": len(attraction_monthly),
        "attraction_catalog_count": len(network_attractions),
        "attraction_edge_count": len(network_edges),
        "attraction_popularity_count": len(popularity),
        "unresolved_popularity_region_count": sum(row["region_mapping_status"] == "unresolved" for row in popularity),
        "foreign_metric_count": len(foreign),
        "benchmark_record_count": len(benchmarks),
        "benchmark_metric_count": len(benchmark_metrics),
        "benchmark_unverified_unit_count": sum(
            row["unit"] == "source_defined_unknown" for row in benchmark_metrics
        ),
        "rejection_count": len(rejections),
        "rejection_code_counts": dict(Counter(str(row["error_code"]) for row in rejections)),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="보조 관광 CSV staging 생성")
    parser.add_argument("--repository-root", default=os.getenv("TOURISM_REPOSITORY_ROOT", ""))
    parser.add_argument("--inventory-dir", default="data/interim/source_repository_inventory")
    parser.add_argument("--output-dir", default="data/processed/supplemental_staging")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.repository_root)
    inventory_dir = Path(args.inventory_dir)
    if not args.repository_root or not root.is_dir():
        print("오류: 유효한 --repository-root 또는 TOURISM_REPOSITORY_ROOT가 필요합니다.", file=sys.stderr)
        return 2
    if not (inventory_dir / "files.csv").is_file():
        print("오류: 먼저 source_repository_inventory.py를 실행해야 합니다.", file=sys.stderr)
        return 2
    print(json.dumps(build_supplemental_staging(root, inventory_dir, Path(args.output_dir)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
