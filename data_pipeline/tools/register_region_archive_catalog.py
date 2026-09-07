"""검증된 서울·강원 원본 snapshot을 지역 ML 카탈로그에 안전하게 등록한다.

이 도구는 학습이나 MySQL 적재를 실행하지 않는다. 원본 내부의 지역 코드 후보와
행정안전부 기준 코드표를 대조하고, 실제 ``data/raw`` 경로가 있는 지역만
``region_data_registry.csv``에 추가한다. 정확한 다운로드 화면 URL이 아직 없으면
출처 상태는 의도적으로 ``needs_exact_download_url``로 남긴다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence


CATALOG_FIELDS = [
    "region_code",
    "region_name",
    "short_name",
    "raw_relative_path",
    "adapter_type",
    "source_name",
    "source_url",
    "downloaded_at",
    "provenance_status",
    "enabled",
]


def _normalize(value: str) -> str:
    return re.sub(r"[\s_]", "", value or "")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _official_by_code(path: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(path)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        code = str(row.get("region_code") or "").strip()
        if code:
            result[code] = row
    return result


def _candidate_rows(inventory_dirs: Sequence[Path]) -> Iterable[dict[str, str]]:
    for directory in inventory_dirs:
        candidate_path = directory / "region_code_candidates.csv"
        if not candidate_path.is_file():
            raise FileNotFoundError(f"REGION_INVENTORY_MISSING: {candidate_path}")
        yield from _read_csv(candidate_path)


def build_catalog_rows(
    *,
    catalog_path: Path,
    inventory_dirs: Sequence[Path],
    official_codes_path: Path,
    raw_root: Path,
    downloaded_at: str,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """기존 카탈로그를 보존하고 코드·명칭·경로가 모두 맞는 새 행만 준비한다."""

    existing = _read_csv(catalog_path) if catalog_path.is_file() else []
    by_code = {str(row["region_code"]).strip(): row for row in existing}
    official = _official_by_code(official_codes_path)
    additions: list[dict[str, str]] = []
    skipped_existing: list[str] = []
    rejected: list[dict[str, str]] = []

    for candidate in _candidate_rows(inventory_dirs):
        code = str(candidate.get("official_region_code") or "").strip()
        province = str(candidate.get("province_name") or "").strip()
        municipality = str(candidate.get("municipality_name") or "").strip()
        # 고양시_덕양구처럼 시 아래 행정구가 있는 경우, ``municipality_name``에는
        # 마지막 행정구명만 있고 공식 코드표에는 ``고양시 덕양구`` 전체가 기록된다.
        # 원본 폴더의 계층명을 공백으로 정규화해 전체 행정구역명까지 대조한다.
        hierarchy = str(candidate.get("local_hierarchy_name") or municipality).replace("_", " ").strip()
        region_folder = str(candidate.get("region_folder") or "").strip()
        if candidate.get("mapping_status") != "resolved_from_data" or not code:
            rejected.append({"region_folder": region_folder, "reason": "RAW_REGION_CODE_UNRESOLVED"})
            continue
        official_row = official.get(code)
        if (
            not official_row
            or _normalize(official_row.get("province_name", "")) != _normalize(province)
            or _normalize(official_row.get("municipality_name", "")) != _normalize(hierarchy)
        ):
            rejected.append({"region_folder": region_folder, "reason": "OFFICIAL_CODE_NAME_MISMATCH"})
            continue
        raw_path = raw_root / province / region_folder
        if not raw_path.is_dir():
            rejected.append({"region_folder": region_folder, "reason": "MATERIALIZED_RAW_MISSING"})
            continue
        row = {
            "region_code": code,
            # 화면·MySQL·문서에는 코드표의 정식 표기를 쓰고, CSV 행 필터에는
            # 원본의 마지막 행정구명(short_name)을 계속 사용한다.
            "region_name": f"{province} {official_row['municipality_name']}",
            "short_name": municipality,
            "raw_relative_path": raw_path.relative_to(raw_root.parents[1]).as_posix(),
            "adapter_type": "standard_datalab_archive",
            "source_name": "한국관광 데이터랩",
            "source_url": "https://datalab.visitkorea.or.kr/",
            "downloaded_at": downloaded_at,
            "provenance_status": "needs_exact_download_url",
            # 원본·코드 검증을 통과한 뒤 등록한다. ML artifact가 아직 없으면 학습 페이지가 준비 중으로 표시한다.
            "enabled": "true",
        }
        prior = by_code.get(code)
        if prior:
            # 강남구는 최신월 보완 원본을 포함한 전용 legacy adapter가 이미 있으므로,
            # 같은 지역의 일반 archive snapshot은 비교·원본 보관용으로만 남긴다.
            if code == "11680" and prior.get("adapter_type") == "legacy_gangnam_zip":
                skipped_existing.append(code)
                continue
            if any(str(prior.get(key) or "") != row[key] for key in ("region_name", "raw_relative_path", "adapter_type")):
                rejected.append({"region_folder": region_folder, "reason": "CATALOG_CODE_CONFLICT"})
            continue
        by_code[code] = row
        additions.append(row)

    merged = [*existing, *sorted(additions, key=lambda row: row["region_code"])]
    summary = {
        "existing_count": len(existing),
        "added_count": len(additions),
        "skipped_existing_codes": skipped_existing,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "total_count": len(merged),
    }
    return merged, summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검증된 지역 archive snapshot을 ML 카탈로그에 등록")
    parser.add_argument("--catalog", default="data/catalog/region_data_registry.csv")
    parser.add_argument("--inventory-dir", action="append", required=True)
    parser.add_argument("--official-codes", required=True)
    parser.add_argument("--raw-root", default="data/source_snapshots")
    parser.add_argument("--downloaded-at", default="2026-08-31")
    parser.add_argument("--write", action="store_true", help="검증 결과를 실제 카탈로그에 추가")
    parser.add_argument(
        "--write-valid",
        action="store_true",
        help="코드 미확정 후보는 보류하고, 검증을 통과한 지역만 실제 카탈로그에 추가",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    catalog = Path(args.catalog)
    try:
        rows, summary = build_catalog_rows(
            catalog_path=catalog,
            inventory_dirs=[Path(item) for item in args.inventory_dir],
            official_codes_path=Path(args.official_codes),
            raw_root=Path(args.raw_root),
            downloaded_at=args.downloaded_at,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    if args.write and args.write_valid:
        print("오류: --write와 --write-valid는 함께 사용할 수 없습니다.", file=sys.stderr)
        return 2
    if args.write and not summary["rejected_count"]:
        _write_csv(catalog, rows)
        summary["status"] = "written"
    elif args.write_valid:
        # 각 additions는 원본 내부 코드, 공식 코드표, snapshot 경로를 모두 통과했다.
        # 코드가 없는 다른 후보는 결과에 섞지 않고 명시적으로 보류한다.
        _write_csv(catalog, rows)
        summary["status"] = "written_validated_subset"
    elif args.write:
        summary["status"] = "not_written_due_to_rejections"
    else:
        summary["status"] = "preview"
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
