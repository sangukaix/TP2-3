"""검증된 staging을 MySQL 적재용 CSV 묶음으로 준비한다.

DB 접속·DDL 실행은 이 도구가 하지 않는다. 먼저 source_id 참조 무결성과 region
mapping을 검증해, transaction import가 가능한 dim/fact CSV만 생성한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence


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
ALLOWED_REGION_STATUSES = {"validated_from_datalab", "validated_from_mois"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_load_bundle(
    staging_path: Path,
    mapping_paths: list[Path],
    source_registry_paths: list[Path],
    output_dir: Path,
) -> dict[str, object]:
    """모든 fact source가 data_source에 존재하는지 확인하고 load 파일을 만든다."""

    staging = read_csv(staging_path)
    regions: dict[str, dict[str, str]] = {}
    for mapping_path in mapping_paths:
        for row in read_csv(mapping_path):
            if row.get("mapping_status") not in ALLOWED_REGION_STATUSES:
                continue
            code = row.get("official_region_code", "")
            if not code:
                continue
            payload = {
                "region_code": code,
                "province_name": row.get("canonical_province_name") or row.get("province_name", ""),
                "municipality_name": row.get("canonical_municipality_name") or row.get("municipality_name", ""),
                "local_hierarchy_name": row.get("canonical_local_hierarchy_name") or row.get("local_hierarchy_name", ""),
                "valid_from": "",
                "valid_to": "",
                "is_active": "1",
            }
            previous = regions.get(code)
            if previous and previous != payload:
                raise ValueError(f"공식 지역코드 mapping 충돌: {code}")
            regions[code] = payload

    source_records: dict[str, dict[str, str]] = {}
    for source_path in source_registry_paths:
        for row in read_csv(source_path):
            source = row.get("source_id", "")
            if not source:
                continue
            payload = {
                "source_id": source,
                "source_name": row.get("source_name", "한국관광 데이터랩 공식 다운로드"),
                "source_page_url": row.get("source_page_url", ""),
                "downloaded_at": row.get("downloaded_at", ""),
                "file_name": row.get("file_name", ""),
                "file_hash": row.get("file_hash", ""),
                "date_range": row.get("date_range", ""),
                "geographic_level": row.get("geographic_level", "시군구"),
                "filters_json": json.dumps({"filters": row.get("filters", "")}, ensure_ascii=False),
                "methodology_notes": row.get("methodology_notes", ""),
                "review_status": "reviewed",
            }
            previous = source_records.get(source)
            if previous and previous != payload:
                raise ValueError(f"source_id registry 충돌: {source}")
            source_records[source] = payload

    fact_rows: list[dict[str, object]] = []
    metric_sources: list[dict[str, str]] = []
    expected_sources: set[str] = set()
    for row in staging:
        region_code = row.get("region_code", "")
        if region_code not in regions:
            raise ValueError(f"검증된 dim_region이 없는 fact region_code: {region_code}")
        fact_rows.append(
            {
                "region_code": region_code,
                "year_month": row.get("year_month", ""),
                **{metric: row.get(metric, "") for metric in METRICS},
                "data_status": row.get("data_status", ""),
            }
        )
        for metric in METRICS:
            source = row.get(f"{metric}_source_id", "")
            if source:
                expected_sources.add(source)
                metric_sources.append(
                    {
                        "region_code": region_code,
                        "year_month": row.get("year_month", ""),
                        "metric_name": metric,
                        "source_id": source,
                    }
                )

    missing_sources = sorted(expected_sources - set(source_records))
    if missing_sources:
        raise ValueError(
            f"data_source registry에 없는 fact source_id {len(missing_sources)}개: {missing_sources[:5]}"
        )

    used_sources = [source_records[source] for source in sorted(expected_sources)]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "dim_region.csv",
        [
            "region_code",
            "province_name",
            "municipality_name",
            "local_hierarchy_name",
            "valid_from",
            "valid_to",
            "is_active",
        ],
        [regions[code] for code in sorted(regions)],
    )
    write_csv(
        output_dir / "data_source.csv",
        [
            "source_id",
            "source_name",
            "source_page_url",
            "downloaded_at",
            "file_name",
            "file_hash",
            "date_range",
            "geographic_level",
            "filters_json",
            "methodology_notes",
            "review_status",
        ],
        used_sources,
    )
    write_csv(
        output_dir / "fact_tourism_monthly.csv",
        ["region_code", "year_month", *METRICS, "data_status"],
        fact_rows,
    )
    write_csv(
        output_dir / "fact_tourism_metric_source.csv",
        ["region_code", "year_month", "metric_name", "source_id"],
        metric_sources,
    )

    summary: dict[str, object] = {
        "dim_region_count": len(regions),
        "data_source_count": len(used_sources),
        "fact_tourism_monthly_count": len(fact_rows),
        "fact_tourism_metric_source_count": len(metric_sources),
        "data_status_counts": dict(Counter(row["data_status"] for row in fact_rows)),
        "status": "ready_for_transactional_mysql_import",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MySQL tourism monthly load bundle 준비")
    parser.add_argument(
        "--staging", default="data/processed/merged_nationwide_staging/tourism_monthly_staging.csv"
    )
    parser.add_argument(
        "--mappings",
        nargs="+",
        default=[
            "data/processed/region_reference/region_mapping_validated.csv",
            "data/processed/materialized_region_reference/region_mapping_validated.csv",
        ],
    )
    parser.add_argument(
        "--source-registries",
        nargs="+",
        default=[
            "data/interim/nationwide_inventory/source_registry_generated.csv",
            "data/interim/materialized_inventory/source_registry_generated.csv",
        ],
    )
    parser.add_argument("--output-dir", default="data/processed/mysql_load_bundle")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    required = [Path(args.staging), *map(Path, args.mappings), *map(Path, args.source_registries)]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print(f"오류: 필요한 입력 파일이 없습니다: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            build_load_bundle(
                Path(args.staging),
                [Path(path) for path in args.mappings],
                [Path(path) for path in args.source_registries],
                Path(args.output_dir),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
