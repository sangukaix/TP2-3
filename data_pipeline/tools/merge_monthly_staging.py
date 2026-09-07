"""서로 다른 공식 Data Lab snapshot의 월별 staging을 충돌 없이 병합한다.

같은 지역·월의 수치가 완전히 동일하면 기준 snapshot을 하나만 남기고 alias audit에
기록한다. 값이 다르면 최신이라고 추정해 덮어쓰지 않고 conflict audit에 남긴다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence


KEY_COLUMNS = ("region_code", "year_month")
OBSERVATION_COLUMNS = (
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
    "missing_metrics",
    "data_status",
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def key_for(row: dict[str, str]) -> tuple[str, str]:
    return tuple(row[column] for column in KEY_COLUMNS)  # type: ignore[return-value]


def conflicts_between(primary: dict[str, str], secondary: dict[str, str]) -> list[str]:
    """출처 ID가 아닌 실제 관측값만 비교한다."""

    return [
        column
        for column in OBSERVATION_COLUMNS
        if str(primary.get(column, "")) != str(secondary.get(column, ""))
    ]


def merge_staging(
    primary_path: Path, secondary_path: Path, output_dir: Path
) -> dict[str, object]:
    """primary 우선 병합과 duplicate/conflict audit을 함께 생성한다."""

    primary_fields, primary_rows = read_csv(primary_path)
    secondary_fields, secondary_rows = read_csv(secondary_path)
    if primary_fields != secondary_fields:
        raise ValueError("두 staging CSV의 schema가 다릅니다.")
    required = set(KEY_COLUMNS + OBSERVATION_COLUMNS)
    if not required.issubset(primary_fields):
        raise ValueError("월별 staging 필수 컬럼이 없습니다.")

    primary_by_key = {key_for(row): row for row in primary_rows}
    if len(primary_by_key) != len(primary_rows):
        raise ValueError("primary에 중복 region_code + year_month가 있습니다.")
    merged = dict(primary_by_key)
    aliases: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    secondary_only = 0

    for row in secondary_rows:
        key = key_for(row)
        current = merged.get(key)
        if current is None:
            merged[key] = row
            secondary_only += 1
            continue
        differences = conflicts_between(current, row)
        source_fields = [field for field in primary_fields if field.endswith("_source_id")]
        if differences:
            conflicts.append(
                {
                    "region_code": key[0],
                    "year_month": key[1],
                    "conflicting_columns_json": json.dumps(differences, ensure_ascii=False),
                    "primary_sources_json": json.dumps(
                        {field: current.get(field, "") for field in source_fields}, ensure_ascii=False
                    ),
                    "secondary_sources_json": json.dumps(
                        {field: row.get(field, "") for field in source_fields}, ensure_ascii=False
                    ),
                    "resolution": "primary_retained_pending_source_review",
                }
            )
        else:
            aliases.append(
                {
                    "region_code": key[0],
                    "year_month": key[1],
                    "primary_sources_json": json.dumps(
                        {field: current.get(field, "") for field in source_fields}, ensure_ascii=False
                    ),
                    "duplicate_sources_json": json.dumps(
                        {field: row.get(field, "") for field in source_fields}, ensure_ascii=False
                    ),
                    "reason": "same_observed_values_different_snapshot_lineage",
                }
            )

    merged_rows = [merged[key] for key in sorted(merged)]
    write_csv(output_dir / "tourism_monthly_staging.csv", primary_fields, merged_rows)
    write_csv(
        output_dir / "duplicate_snapshot_aliases.csv",
        [
            "region_code",
            "year_month",
            "primary_sources_json",
            "duplicate_sources_json",
            "reason",
        ],
        aliases,
    )
    write_csv(
        output_dir / "snapshot_conflicts.csv",
        [
            "region_code",
            "year_month",
            "conflicting_columns_json",
            "primary_sources_json",
            "secondary_sources_json",
            "resolution",
        ],
        conflicts,
    )
    summary: dict[str, object] = {
        "primary_row_count": len(primary_rows),
        "secondary_row_count": len(secondary_rows),
        "secondary_only_row_count": secondary_only,
        "same_value_duplicate_count": len(aliases),
        "conflict_count": len(conflicts),
        "merged_row_count": len(merged_rows),
        "merged_region_count": len({row["region_code"] for row in merged_rows}),
        "status": "validated" if not conflicts else "conflicts_require_review",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "merge_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공식 월별 staging snapshot 병합")
    parser.add_argument(
        "--primary", default="data/processed/nationwide_staging/tourism_monthly_staging.csv"
    )
    parser.add_argument(
        "--secondary", default="data/processed/materialized_staging/tourism_monthly_staging.csv"
    )
    parser.add_argument("--output-dir", default="data/processed/merged_nationwide_staging")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    primary, secondary = Path(args.primary), Path(args.secondary)
    if not primary.is_file() or not secondary.is_file():
        print("오류: primary·secondary staging CSV가 필요합니다.", file=sys.stderr)
        return 2
    print(
        json.dumps(
            merge_staging(primary, secondary, Path(args.output_dir)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
