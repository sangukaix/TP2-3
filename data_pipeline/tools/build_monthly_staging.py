"""검사된 관광데이터랩 ZIP에서 월별 MySQL 적재 후보를 만든다.

공식 코드가 미확정된 지역과 잘못된 월·수치는 버리지 않고 rejection 파일에
기록한다. 결과 파일은 staging 용도이며 공식 코드 승인 전 production 적재 금지다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Sequence

# 패키지 실행과 tools 폴더의 직접 CLI 실행을 모두 지원한다.
try:
    from .data_inventory import decode_csv, normalize_month, region_name_matches
except ModuleNotFoundError:  # pragma: no cover - 직접 CLI 실행 경로
    from data_inventory import decode_csv, normalize_month, region_name_matches


MetricSelector = Callable[[dict[str, str], dict[str, str]], bool]


# 각 지표는 원본 파일, 월 컬럼, 값 컬럼, 행 선택 규칙을 명시한다.
DATASET_SPECS: dict[str, dict[str, object]] = {
    "방문자 수(연인원) 추이.csv": {
        "month_column": "기준년월",
        "metrics": {
            "visitors": "방문자수",
            "visitors_previous_year": "전년동월방문자수",
            "visitors_yoy_pct": "방문자수증감률",
        },
        "selector": lambda row, context: True,
    },
    "관광소비 추이_내국인.csv": {
        "month_column": "기준연월",
        "metrics": {"domestic_tourism_spend_thousand_krw": "소비액(천원)"},
        "selector": lambda row, context: row.get("업종대분류명", "").strip() == "전체",
    },
    "관광소비 추이_외지인.csv": {
        "month_column": "기준연월",
        "metrics": {"nonlocal_tourism_spend_thousand_krw": "소비액(천원)"},
        "selector": lambda row, context: row.get("업종대분류명", "").strip() == "전체",
    },
    "순 방문자 수 및 숙박 비율.csv": {
        "month_column": "기준연월",
        "metrics": {
            "unique_visitors": "순 방문자수",
            "overnight_ratio_pct": "숙박자 비율",
        },
        "selector": lambda row, context: True,
    },
    "평균 숙박일.csv": {
        "month_column": "기준연월",
        "metrics": {"avg_stay_days": "평균 숙박일수"},
        "selector": lambda row, context: True,
    },
    "평균 체류시간 추이.csv": {
        "month_column": "기준연월",
        "metrics": {"avg_stay_minutes": "체류시간(분)"},
        "selector": lambda row, context: region_name_matches(
            row.get("지역명", ""),
            context["province_name"],
            context["municipality_name"],
            context["local_hierarchy_name"],
        ),
    },
}


METRIC_COLUMNS = [
    metric
    for spec in DATASET_SPECS.values()
    for metric in dict(spec["metrics"]).keys()
]


# CSV 숫자는 과학 표기와 소수점을 보존하기 위해 Decimal로 검증한다.
def normalize_number(value: str) -> str:
    cleaned = str(value or "").strip().replace(",", "")
    if not cleaned:
        raise InvalidOperation("빈 값")
    number = Decimal(cleaned)
    if not number.is_finite():
        raise InvalidOperation("유한한 숫자가 아님")
    normalized = format(number, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


# inventory가 만든 후보 중 단일 코드만 staging에 허용한다.
def load_region_mapping(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    return {
        row["region_folder"]: row
        for row in rows
        if row.get("mapping_status")
        in {"resolved_from_data", "validated_from_datalab", "validated_from_mois"}
        and row.get("official_region_code")
    }


# source ID는 원본 상대경로와 파일 hash에 고정돼 재실행해도 동일하다.
def make_source_id(relative_path: str, archive_sha256: str) -> str:
    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"datalab:{path_hash}:{archive_sha256[:12]}"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_staging(
    raw_root: Path,
    inventory_dir: Path,
    output_dir: Path,
    region_mapping_path: Path | None = None,
) -> dict[str, object]:
    """핵심 월간 지표를 표준 key로 병합하고 모든 제외 사유를 기록한다."""

    mapping = load_region_mapping(
        region_mapping_path or inventory_dir / "region_code_candidates.csv"
    )
    with (inventory_dir / "archives.csv").open(encoding="utf-8-sig", newline="") as source:
        archives = list(csv.DictReader(source))

    records: dict[tuple[str, str], dict[str, object]] = {}
    rejections: list[dict[str, object]] = []
    audits: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    for archive in archives:
        archive_path = raw_root / Path(archive["archive_relative_path"])
        region_folder = archive["region_folder"]
        region = mapping.get(region_folder)
        source_id = make_source_id(archive["archive_relative_path"], archive["archive_sha256"])
        audit_key = (source_id, archive["archive_relative_path"])

        try:
            with zipfile.ZipFile(archive_path) as zip_source:
                for entry in zip_source.infolist():
                    entry_name = Path(entry.filename).name
                    spec = DATASET_SPECS.get(entry_name)
                    if not spec:
                        continue
                    raw = zip_source.read(entry)
                    text, _ = decode_csv(raw)
                    reader = csv.DictReader(io.StringIO(text))
                    context = {
                        "province_name": archive["province_name"],
                        "municipality_name": archive["municipality_name"],
                        "local_hierarchy_name": archive["local_hierarchy_name"],
                    }
                    selector = spec["selector"]
                    assert callable(selector)
                    metric_map = dict(spec["metrics"])
                    month_column = str(spec["month_column"])

                    for row_number, row in enumerate(reader, start=2):
                        if not row or not any(str(value or "").strip() for value in row.values()):
                            continue
                        audits[audit_key]["raw_rows"] += 1
                        if not selector(row, context):
                            audits[audit_key]["filtered_rows"] += 1
                            continue
                        if not region:
                            audits[audit_key]["rejected_rows"] += 1
                            rejections.append(
                                {
                                    "source_id": source_id,
                                    "archive_relative_path": archive["archive_relative_path"],
                                    "entry_name": entry_name,
                                    "row_number": row_number,
                                    "region_folder": region_folder,
                                    "raw_month": row.get(month_column, ""),
                                    "error_code": "region_code_unresolved",
                                    "detail": "공식 지역코드 승인 전 staging 제외",
                                }
                            )
                            continue

                        month = normalize_month(row.get(month_column, ""))
                        if not month:
                            audits[audit_key]["rejected_rows"] += 1
                            rejections.append(
                                {
                                    "source_id": source_id,
                                    "archive_relative_path": archive["archive_relative_path"],
                                    "entry_name": entry_name,
                                    "row_number": row_number,
                                    "region_folder": region_folder,
                                    "raw_month": row.get(month_column, ""),
                                    "error_code": "invalid_year_month",
                                    "detail": "YYYYMM 또는 YYYY-MM 형식이 아님",
                                }
                            )
                            continue

                        key = (region["official_region_code"], month)
                        record = records.setdefault(
                            key,
                            {
                                "region_code": region["official_region_code"],
                                "year_month": month,
                                "province_name": region["province_name"],
                                "municipality_name": region["municipality_name"],
                                "local_hierarchy_name": region["local_hierarchy_name"],
                                **{metric: "" for metric in METRIC_COLUMNS},
                                **{f"{metric}_source_id": "" for metric in METRIC_COLUMNS},
                            },
                        )

                        row_failed = False
                        for metric, source_column in metric_map.items():
                            try:
                                value = normalize_number(row.get(source_column, ""))
                            except (InvalidOperation, ValueError):
                                row_failed = True
                                rejections.append(
                                    {
                                        "source_id": source_id,
                                        "archive_relative_path": archive["archive_relative_path"],
                                        "entry_name": entry_name,
                                        "row_number": row_number,
                                        "region_folder": region_folder,
                                        "raw_month": row.get(month_column, ""),
                                        "error_code": "invalid_numeric_value",
                                        "detail": f"{source_column}={row.get(source_column, '')}",
                                    }
                                )
                                continue

                            existing = str(record.get(metric, ""))
                            if existing and existing != value:
                                row_failed = True
                                rejections.append(
                                    {
                                        "source_id": source_id,
                                        "archive_relative_path": archive["archive_relative_path"],
                                        "entry_name": entry_name,
                                        "row_number": row_number,
                                        "region_folder": region_folder,
                                        "raw_month": row.get(month_column, ""),
                                        "error_code": "conflicting_duplicate_metric",
                                        "detail": f"{metric}: 기존={existing}, 신규={value}",
                                    }
                                )
                                continue
                            record[metric] = value
                            record[f"{metric}_source_id"] = source_id
                        audits[audit_key]["rejected_rows" if row_failed else "loaded_rows"] += 1
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
            audits[audit_key]["archive_errors"] += 1
            rejections.append(
                {
                    "source_id": source_id,
                    "archive_relative_path": archive["archive_relative_path"],
                    "entry_name": "",
                    "row_number": "",
                    "region_folder": region_folder,
                    "raw_month": "",
                    "error_code": "archive_read_error",
                    "detail": str(exc),
                }
            )

    staging_rows: list[dict[str, object]] = []
    for key in sorted(records):
        record = records[key]
        missing = [metric for metric in METRIC_COLUMNS if not record.get(metric)]
        record["missing_metrics"] = " | ".join(missing)
        record["data_status"] = "complete" if not missing else "partial"
        staging_rows.append(record)

    audit_rows: list[dict[str, object]] = []
    for (source_id, relative_path), counts in sorted(audits.items()):
        audit_rows.append(
            {
                "source_id": source_id,
                "archive_relative_path": relative_path,
                "raw_rows": counts["raw_rows"],
                "loaded_rows": counts["loaded_rows"],
                "filtered_rows": counts["filtered_rows"],
                "rejected_rows": counts["rejected_rows"],
                "archive_errors": counts["archive_errors"],
                "row_accounting_ok": counts["raw_rows"]
                == counts["loaded_rows"] + counts["filtered_rows"] + counts["rejected_rows"],
            }
        )

    staging_fields = [
        "region_code",
        "year_month",
        "province_name",
        "municipality_name",
        "local_hierarchy_name",
        *METRIC_COLUMNS,
        *(f"{metric}_source_id" for metric in METRIC_COLUMNS),
        "missing_metrics",
        "data_status",
    ]
    rejection_fields = [
        "source_id",
        "archive_relative_path",
        "entry_name",
        "row_number",
        "region_folder",
        "raw_month",
        "error_code",
        "detail",
    ]
    write_csv(output_dir / "tourism_monthly_staging.csv", staging_fields, staging_rows)
    write_csv(output_dir / "load_rejections.csv", rejection_fields, rejections)
    write_csv(
        output_dir / "source_row_audit.csv",
        [
            "source_id",
            "archive_relative_path",
            "raw_rows",
            "loaded_rows",
            "filtered_rows",
            "rejected_rows",
            "archive_errors",
            "row_accounting_ok",
        ],
        audit_rows,
    )

    summary: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root),
        "supported_region_count": len({row["region_code"] for row in staging_rows}),
        "monthly_row_count": len(staging_rows),
        "complete_row_count": sum(row["data_status"] == "complete" for row in staging_rows),
        "partial_row_count": sum(row["data_status"] == "partial" for row in staging_rows),
        "rejection_count": len(rejections),
        "rejection_code_counts": dict(Counter(str(row["error_code"]) for row in rejections)),
        "audited_source_count": len(audit_rows),
        "row_accounting_failure_count": sum(row["row_accounting_ok"] != True for row in audit_rows),
        "status": (
            "validated_staging"
            if region_mapping_path
            else "staging_only_region_codes_require_official_approval"
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "transform_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


# 공유폴더 경로는 환경마다 달라 CLI 또는 환경변수로 주입한다.
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전국 관광 월별 staging 생성")
    parser.add_argument("--raw-root", default=os.getenv("TOURISM_RAW_ROOT", ""))
    parser.add_argument("--inventory-dir", default="data/interim/nationwide_inventory")
    parser.add_argument("--output-dir", default="data/processed/nationwide_staging")
    parser.add_argument(
        "--region-mapping",
        default="",
        help="공식 검증된 region_mapping_validated.csv 경로입니다.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    raw_root = Path(args.raw_root)
    inventory_dir = Path(args.inventory_dir)
    if not args.raw_root or not raw_root.is_dir():
        print("오류: 유효한 --raw-root 또는 TOURISM_RAW_ROOT가 필요합니다.", file=sys.stderr)
        return 2
    if not (inventory_dir / "archives.csv").is_file():
        print("오류: 먼저 tools/data_inventory.py를 실행해야 합니다.", file=sys.stderr)
        return 2
    mapping_path = Path(args.region_mapping) if args.region_mapping else None
    summary = build_staging(raw_root, inventory_dir, Path(args.output_dir), mapping_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
