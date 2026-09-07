"""행정안전부 법정동 코드 ZIP으로 Data Lab 지역 폴더를 검증한다.

공식 코드의 유효시점과 원본 hash를 보존하며, Data Lab 내부에서 직접 확인된
코드는 유지하고 미해결 지역만 보수적으로 보완한다. 후보가 하나가 아니면 자동
선택하지 않고 review 상태로 남긴다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Sequence


# 행정안전부 고정폭 TEXT의 byte 시작 위치다. 한글 byte 폭 때문에 문자열 index로
# 자르지 않고 원본 byte를 자른 뒤 CP949로 해석한다.
FIELD_SLICES = {
    "legal_dong_code": (0, 10),
    "province_name": (11, 41),
    "municipality_name": (42, 72),
    "town_name": (73, 103),
    "village_name": (104, 134),
    "created_date": (135, 143),
    "abolished_date": (144, 152),
}

PROVINCE_ALIASES = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}


def normalize_name(value: str) -> str:
    """공백·구분자만 제거하고 행정구역 명칭 자체는 바꾸지 않는다."""

    return re.sub(r"[\s_]", "", value or "")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_official_legal_dong_zip(path: Path) -> list[dict[str, str]]:
    """법정동 코드 중 현재 유효한 시도·시군구 level만 반환한다."""

    with zipfile.ZipFile(path) as archive:
        entry = next(
            (
                item
                for item in archive.infolist()
                if Path(item.filename).name.startswith("KIKcd_B.")
                and not item.filename.lower().endswith(".xlsx")
            ),
            None,
        )
        if entry is None:
            raise ValueError("KIKcd_B 법정동 코드 파일을 찾을 수 없습니다.")
        lines = archive.read(entry).splitlines()

    records: list[dict[str, str]] = []
    for raw_line in lines[1:]:
        if len(raw_line) < FIELD_SLICES["abolished_date"][1]:
            continue
        values = {
            field: raw_line[start:end].decode("cp949").strip()
            for field, (start, end) in FIELD_SLICES.items()
        }
        code = values["legal_dong_code"]
        # 시군구 row는 읍면동·리가 비어 있고, 현재 유효하며, 10자리 코드가 필요하다.
        if (
            len(code) == 10
            and values["province_name"]
            and values["municipality_name"]
            and not values["town_name"]
            and not values["village_name"]
            and not values["abolished_date"]
        ):
            records.append(
                {
                    **values,
                    "region_code": code[:5],
                    "official_full_name": f"{values['province_name']} {values['municipality_name']}",
                }
            )
    return records


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_region_mapping(
    candidate_rows: list[dict[str, str]], official_rows: list[dict[str, str]]
) -> list[dict[str, object]]:
    """Data Lab 자체 코드 우선, 공식 명칭 exact match 차선으로 지역코드를 정한다."""

    official_by_name: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in official_rows:
        key = (normalize_name(row["province_name"]), normalize_name(row["municipality_name"]))
        official_by_name.setdefault(key, []).append(row)
    official_by_code: dict[str, list[dict[str, str]]] = {}
    for row in official_rows:
        official_by_code.setdefault(row["region_code"], []).append(row)

    output: list[dict[str, object]] = []
    for candidate in candidate_rows:
        existing_code = candidate.get("official_region_code", "").strip()
        if existing_code and candidate.get("mapping_status") == "resolved_from_data":
            canonical_matches = official_by_code.get(existing_code, [])
            canonical = canonical_matches[0] if len(canonical_matches) == 1 else None
            output.append(
                {
                    **candidate,
                    "mapping_status": "validated_from_datalab",
                    "mapping_method": "datalab_region_code_crosschecked_with_mois",
                    "official_reference_name": canonical["official_full_name"] if canonical else "",
                    "canonical_province_name": canonical["province_name"] if canonical else candidate.get("province_name", ""),
                    "canonical_municipality_name": canonical["municipality_name"] if canonical else candidate.get("municipality_name", ""),
                    "canonical_local_hierarchy_name": canonical["municipality_name"] if canonical else candidate.get("local_hierarchy_name", ""),
                }
            )
            continue

        province = PROVINCE_ALIASES.get(candidate.get("province_name", ""), candidate.get("province_name", ""))
        hierarchy = candidate.get("local_hierarchy_name", "").replace("_", " ")
        matches = official_by_name.get((normalize_name(province), normalize_name(hierarchy)), [])
        unique_codes = sorted({row["region_code"] for row in matches})
        if len(unique_codes) == 1:
            output.append(
                {
                    **candidate,
                    "official_region_code": unique_codes[0],
                    "mapping_status": "validated_from_mois",
                    "mapping_method": "official_name_exact_match",
                    "official_reference_name": matches[0]["official_full_name"],
                    "canonical_province_name": matches[0]["province_name"],
                    "canonical_municipality_name": matches[0]["municipality_name"],
                    "canonical_local_hierarchy_name": matches[0]["municipality_name"],
                }
            )
        else:
            output.append(
                {
                    **candidate,
                    "mapping_status": "needs_review",
                    "mapping_method": "no_unique_official_match",
                    "official_reference_name": " | ".join(row["official_full_name"] for row in matches),
                    "canonical_province_name": "",
                    "canonical_municipality_name": "",
                    "canonical_local_hierarchy_name": "",
                }
            )
    return output


def build_reference(
    official_zip: Path,
    candidates_path: Path,
    output_dir: Path,
    effective_date: str,
) -> dict[str, object]:
    official_rows = parse_official_legal_dong_zip(official_zip)
    candidate_rows = read_csv(candidates_path)
    mappings = resolve_region_mapping(candidate_rows, official_rows)

    write_csv(
        output_dir / "official_municipality_codes.csv",
        [
            "region_code",
            "legal_dong_code",
            "province_name",
            "municipality_name",
            "town_name",
            "village_name",
            "official_full_name",
            "created_date",
            "abolished_date",
        ],
        official_rows,
    )
    mapping_fields = list(candidate_rows[0].keys()) + [
        "mapping_method",
        "official_reference_name",
        "canonical_province_name",
        "canonical_municipality_name",
        "canonical_local_hierarchy_name",
    ]
    write_csv(output_dir / "region_mapping_validated.csv", mapping_fields, mappings)

    status_counts = Counter(str(row["mapping_status"]) for row in mappings)
    summary: dict[str, object] = {
        "official_source_file": official_zip.name,
        "official_source_sha256": sha256_file(official_zip),
        "official_effective_date": effective_date,
        "official_municipality_count": len(official_rows),
        "region_candidate_count": len(mappings),
        "mapping_status_counts": dict(status_counts),
        "production_ready_mapping_count": sum(
            status in {"validated_from_datalab", "validated_from_mois"}
            for status in (row["mapping_status"] for row in mappings)
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공식 행정구역 코드 기준 지역 mapping 검증")
    parser.add_argument("--official-zip", required=True)
    parser.add_argument(
        "--candidates",
        default="data/interim/nationwide_inventory/region_code_candidates.csv",
    )
    parser.add_argument("--output-dir", default="data/processed/region_reference")
    parser.add_argument("--effective-date", default="2026-02-01")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    official_zip = Path(args.official_zip)
    candidates = Path(args.candidates)
    if not official_zip.is_file() or not candidates.is_file():
        print("오류: 공식 코드 ZIP과 region 후보 CSV가 모두 필요합니다.", file=sys.stderr)
        return 2
    summary = build_reference(
        official_zip, candidates, Path(args.output_dir), args.effective_date
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
