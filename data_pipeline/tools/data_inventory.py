"""관광데이터랩 원본 ZIP을 수정하지 않고 목록과 스키마를 검사한다.

이 도구는 네트워크 공유폴더를 운영 DB처럼 직접 조회하지 않는다. 원본 파일의
경로·해시·CSV 구조·기간을 먼저 기록해 누락과 중복을 확인하는 Phase 1 도구다.
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
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
PERIOD_COLUMN_NAMES = {"기준연월", "기준년월", "연월", "년월", "year_month"}
REGION_CODE_COLUMN_NAMES = {"지역코드", "시군구코드", "법정동코드", "region_code"}
REGION_NAME_COLUMN_NAMES = {
    "지역명",
    "기초지자체명",
    "시도(시군구) 명",
    "시군구명",
    "region_name",
}
KNOWN_PROVINCE_NAMES = (
    "강원특별자치도",
    "전북특별자치도",
    "제주특별자치도",
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원도",
    "충청북도",
    "충청남도",
    "전라북도",
    "전라남도",
    "경상북도",
    "경상남도",
)
ARCHIVE_PERIOD_RE = re.compile(r"^(?P<year>20\d{2})_(?P<start>0[1-9]|1[0-2])_(?P<end>0[1-9]|1[0-2])$")
MONTH_VALUE_RE = re.compile(r"^(20\d{2})[-./]?(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class CsvProfile:
    """ZIP 내부 CSV 한 개의 재현 가능한 검사 결과다."""

    entry_name: str
    entry_size: int
    encoding: str
    row_count: int
    columns: list[str]
    period_columns: list[str]
    region_code_columns: list[str]
    period_min: str
    period_max: str
    matched_region_codes: list[str]
    status: str
    issues: list[str]


@dataclass(frozen=True)
class ArchiveProfile:
    """원본 ZIP과 그 안의 CSV 검사 결과를 함께 보관한다."""

    region_folder: str
    province_name: str
    municipality_name: str
    local_hierarchy_name: str
    category: str
    archive_name: str
    archive_relative_path: str
    archive_size_bytes: int
    archive_modified_at: str
    archive_sha256: str
    archive_period_start: str
    archive_period_end: str
    archive_period_type: str
    csv_profiles: list[CsvProfile]
    status: str
    issues: list[str]


# 원본이 다시 다운로드돼도 같은 파일인지 검증할 수 있도록 SHA-256을 계산한다.
def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


# CSV 인코딩은 관광데이터랩 파일마다 다를 수 있어 안전한 후보 순서로 판별한다.
def decode_csv(raw: bytes) -> tuple[str, str]:
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", raw, 0, min(1, len(raw)), "지원 인코딩으로 해석할 수 없음")


# 폴더명은 표시용으로만 분리하며, 실제 조인 키로는 사용하지 않는다.
def split_region_folder(folder_name: str) -> tuple[str, str]:
    parts = [part.strip() for part in folder_name.split("_") if part.strip()]
    if len(parts) < 2:
        return "", parts[0] if parts else ""
    return parts[0], parts[-1]


# 일반 시와 행정구가 함께 있는 폴더는 고양시_덕양구처럼 전체 계층도 보존한다.
def local_hierarchy_name(folder_name: str) -> str:
    parts = [part.strip() for part in folder_name.split("_") if part.strip()]
    return "_".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else "")


# ZIP 이름의 2025_01_12 형식을 데이터 제공 범위로 변환한다.
def parse_archive_period(stem: str) -> tuple[str, str]:
    match = ARCHIVE_PERIOD_RE.match(stem)
    if not match:
        return "", ""
    year = match.group("year")
    return f"{year}-{match.group('start')}", f"{year}-{match.group('end')}"


# 월 표기를 YYYY-MM로 통일해 기간 비교와 누락 검사가 가능하게 만든다.
def normalize_month(value: str) -> str:
    cleaned = value.strip()
    if cleaned.endswith(".0"):
        cleaned = cleaned[:-2]
    match = MONTH_VALUE_RE.match(cleaned)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}"


# 공백과 시도 접두어 차이를 줄여 폴더의 시군구와 CSV 행을 보수적으로 대조한다.
def normalize_region_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def region_name_matches(value: str, province: str, municipality: str, hierarchy: str) -> bool:
    normalized = normalize_region_name(value)
    target = normalize_region_name(municipality)
    hierarchy_target = normalize_region_name(hierarchy.replace("_", ""))
    province_target = normalize_region_name(province)
    candidates = {target, hierarchy_target, f"{province_target}{hierarchy_target}"}

    # 남양주시를 양주시로 잘못 인식하지 않도록 endswith 비교는 사용하지 않는다.
    without_province = normalized
    for known_province in KNOWN_PROVINCE_NAMES:
        prefix = normalize_region_name(known_province)
        if without_province.startswith(prefix):
            without_province = without_province[len(prefix) :]
            break
    return normalized in candidates or without_province in {target, hierarchy_target}


# CSV 전체를 계산에 쓰지 않고 헤더·행 수·기간·지역코드 후보만 검사한다.
def profile_csv(
    entry_name: str,
    entry_size: int,
    raw: bytes,
    province: str,
    municipality: str,
    hierarchy: str,
) -> CsvProfile:
    issues: list[str] = []
    try:
        text, encoding = decode_csv(raw)
    except UnicodeDecodeError as exc:
        return CsvProfile(
            entry_name=entry_name,
            entry_size=entry_size,
            encoding="unknown",
            row_count=0,
            columns=[],
            period_columns=[],
            region_code_columns=[],
            period_min="",
            period_max="",
            matched_region_codes=[],
            status="error",
            issues=[str(exc)],
        )

    reader = csv.DictReader(io.StringIO(text))
    columns = [column.strip() for column in (reader.fieldnames or []) if column]
    if not columns:
        issues.append("CSV 헤더 없음")

    period_columns = [column for column in columns if column in PERIOD_COLUMN_NAMES]
    code_columns = [column for column in columns if column in REGION_CODE_COLUMN_NAMES]
    name_columns = [column for column in columns if column in REGION_NAME_COLUMN_NAMES]
    months: set[str] = set()
    matched_codes: set[str] = set()
    row_count = 0

    for row in reader:
        if not row or not any(str(value or "").strip() for value in row.values()):
            continue
        row_count += 1
        for column in period_columns:
            month = normalize_month(str(row.get(column, "")))
            if month:
                months.add(month)
        if code_columns and name_columns:
            if any(
                region_name_matches(str(row.get(column, "")), province, municipality, hierarchy)
                for column in name_columns
            ):
                for column in code_columns:
                    code = str(row.get(column, "")).strip()
                    if code.endswith(".0"):
                        code = code[:-2]
                    if code:
                        matched_codes.add(code)

    if row_count == 0:
        issues.append("데이터 행 없음")

    return CsvProfile(
        entry_name=entry_name,
        entry_size=entry_size,
        encoding=encoding,
        row_count=row_count,
        columns=columns,
        period_columns=period_columns,
        region_code_columns=code_columns,
        period_min=min(months) if months else "",
        period_max=max(months) if months else "",
        matched_region_codes=sorted(matched_codes),
        status="ok" if not issues else "warning",
        issues=issues,
    )


# ZIP은 압축 해제하지 않고 스트림으로 읽어 원본 보존과 재실행성을 지킨다.
def profile_archive(raw_root: Path, archive_path: Path) -> ArchiveProfile:
    relative = archive_path.relative_to(raw_root)
    region_folder = relative.parts[0]
    category = relative.parts[1] if len(relative.parts) > 2 else "(미분류)"
    province, municipality = split_region_folder(region_folder)
    hierarchy = local_hierarchy_name(region_folder)
    start, end = parse_archive_period(archive_path.stem)
    is_rolling_30_day = category == "지역 집중률" and "향후 30일" in archive_path.stem
    period_type = "rolling_30_day" if is_rolling_30_day else ("calendar_range" if start and end else "unknown")
    issues: list[str] = []
    profiles: list[CsvProfile] = []

    try:
        with zipfile.ZipFile(archive_path) as archive:
            csv_entries = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".csv")]
            if not csv_entries:
                issues.append("ZIP 내부 CSV 없음")
            for entry in csv_entries:
                profiles.append(
                    profile_csv(
                        entry.filename,
                        entry.file_size,
                        archive.read(entry),
                        province,
                        municipality,
                        hierarchy,
                    )
                )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        issues.append(f"ZIP 읽기 실패: {exc}")

    if (not start or not end) and not is_rolling_30_day:
        issues.append("ZIP 파일명 기간 형식 확인 필요")
    if any(profile.status == "error" for profile in profiles):
        issues.append("CSV 읽기 오류 포함")

    return ArchiveProfile(
        region_folder=region_folder,
        province_name=province,
        municipality_name=municipality,
        local_hierarchy_name=hierarchy,
        category=category,
        archive_name=archive_path.name,
        archive_relative_path=relative.as_posix(),
        archive_size_bytes=archive_path.stat().st_size,
        archive_modified_at=datetime.fromtimestamp(archive_path.stat().st_mtime, timezone.utc).isoformat(),
        archive_sha256=sha256_file(archive_path),
        archive_period_start=start,
        archive_period_end=end,
        archive_period_type=period_type,
        csv_profiles=profiles,
        status="ok" if not issues else "warning",
        issues=issues,
    )


# 결과 파일을 항상 같은 컬럼 순서로 저장해 diff와 MySQL 적재 검토를 쉽게 한다.
def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_inventory(raw_root: Path, output_dir: Path, max_regions: int | None = None) -> dict[str, object]:
    """공유폴더 전체를 스캔하고 검증 가능한 산출물을 생성한다."""

    region_dirs = sorted((path for path in raw_root.iterdir() if path.is_dir()), key=lambda path: path.name)
    if max_regions is not None:
        region_dirs = region_dirs[:max_regions]

    archives: list[ArchiveProfile] = []
    empty_categories: list[tuple[str, str]] = []
    for region_dir in region_dirs:
        for category_dir in sorted((path for path in region_dir.iterdir() if path.is_dir()), key=lambda path: path.name):
            zip_files = sorted(category_dir.glob("*.zip"))
            if not zip_files:
                empty_categories.append((region_dir.name, category_dir.name))
            for archive_path in zip_files:
                archives.append(profile_archive(raw_root, archive_path))

    inventory_rows: list[dict[str, object]] = []
    archive_rows: list[dict[str, object]] = []
    mapping_candidates: dict[str, set[str]] = defaultdict(set)
    issue_rows: list[dict[str, object]] = []

    for archive in archives:
        archive_rows.append(
            {
                "region_folder": archive.region_folder,
                "province_name": archive.province_name,
                "municipality_name": archive.municipality_name,
                "local_hierarchy_name": archive.local_hierarchy_name,
                "category": archive.category,
                "archive_name": archive.archive_name,
                "archive_relative_path": archive.archive_relative_path,
                "archive_size_bytes": archive.archive_size_bytes,
                "archive_modified_at": archive.archive_modified_at,
                "archive_sha256": archive.archive_sha256,
                "archive_period_start": archive.archive_period_start,
                "archive_period_end": archive.archive_period_end,
                "archive_period_type": archive.archive_period_type,
                "csv_entry_count": len(archive.csv_profiles),
                "status": archive.status,
                "issues": " | ".join(archive.issues),
            }
        )
        for issue in archive.issues:
            issue_rows.append(
                {
                    "severity": "warning",
                    "code": "archive_warning",
                    "region_folder": archive.region_folder,
                    "category": archive.category,
                    "archive": archive.archive_name,
                    "entry": "",
                    "detail": issue,
                }
            )
        for profile in archive.csv_profiles:
            mapping_candidates[archive.region_folder].update(profile.matched_region_codes)
            inventory_rows.append(
                {
                    "region_folder": archive.region_folder,
                    "province_name": archive.province_name,
                    "municipality_name": archive.municipality_name,
                    "local_hierarchy_name": archive.local_hierarchy_name,
                    "category": archive.category,
                    "archive_name": archive.archive_name,
                    "archive_relative_path": archive.archive_relative_path,
                    "archive_size_bytes": archive.archive_size_bytes,
                    "archive_modified_at": archive.archive_modified_at,
                    "archive_sha256": archive.archive_sha256,
                    "archive_period_start": archive.archive_period_start,
                    "archive_period_end": archive.archive_period_end,
                    "archive_period_type": archive.archive_period_type,
                    "entry_name": profile.entry_name,
                    "entry_size": profile.entry_size,
                    "encoding": profile.encoding,
                    "row_count": profile.row_count,
                    "columns_json": json.dumps(profile.columns, ensure_ascii=False),
                    "period_columns_json": json.dumps(profile.period_columns, ensure_ascii=False),
                    "region_code_columns_json": json.dumps(profile.region_code_columns, ensure_ascii=False),
                    "period_min": profile.period_min,
                    "period_max": profile.period_max,
                    "matched_region_codes_json": json.dumps(profile.matched_region_codes, ensure_ascii=False),
                    "status": profile.status,
                    "issues": " | ".join(profile.issues),
                }
            )
            for issue in profile.issues:
                issue_rows.append(
                    {
                        "severity": "error" if profile.status == "error" else "warning",
                        "code": "csv_warning",
                        "region_folder": archive.region_folder,
                        "category": archive.category,
                        "archive": archive.archive_name,
                        "entry": profile.entry_name,
                        "detail": issue,
                    }
                )

    for region_folder, category in empty_categories:
        issue_rows.append(
            {
                "severity": "info",
                "code": "empty_category",
                "region_folder": region_folder,
                "category": category,
                "archive": "",
                "entry": "",
                "detail": "카테고리 폴더에 ZIP 파일이 없음",
            }
        )

    local_name_groups: dict[str, list[str]] = defaultdict(list)
    for region_dir in region_dirs:
        _, municipality = split_region_folder(region_dir.name)
        local_name_groups[municipality].append(region_dir.name)
    for municipality, folders in sorted(local_name_groups.items()):
        if len(folders) > 1:
            issue_rows.append(
                {
                    "severity": "warning",
                    "code": "duplicate_municipality_name",
                    "region_folder": " | ".join(folders),
                    "category": "",
                    "archive": "",
                    "entry": "",
                    "detail": f"'{municipality}' 명칭만으로 조인 금지",
                }
            )

    region_rows: list[dict[str, object]] = []
    for region_dir in region_dirs:
        province, municipality = split_region_folder(region_dir.name)
        hierarchy = local_hierarchy_name(region_dir.name)
        candidates = sorted(mapping_candidates.get(region_dir.name, set()))
        status = "resolved_from_data" if len(candidates) == 1 else ("ambiguous" if candidates else "unresolved")
        region_rows.append(
            {
                "region_folder": region_dir.name,
                "province_name": province,
                "municipality_name": municipality,
                "local_hierarchy_name": hierarchy,
                "region_code_candidates_json": json.dumps(candidates, ensure_ascii=False),
                "mapping_status": status,
                "official_region_code": candidates[0] if len(candidates) == 1 else "",
                "review_note": "자동 후보는 공식 코드표와 대조 후 승인해야 함",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "archives.csv", list(archive_rows[0].keys()) if archive_rows else [], archive_rows)
    write_csv(output_dir / "csv_schema_inventory.csv", list(inventory_rows[0].keys()) if inventory_rows else [], inventory_rows)
    write_csv(output_dir / "region_code_candidates.csv", list(region_rows[0].keys()) if region_rows else [], region_rows)
    write_csv(
        output_dir / "validation_issues.csv",
        ["severity", "code", "region_folder", "category", "archive", "entry", "detail"],
        issue_rows,
    )

    source_rows: list[dict[str, object]] = []
    for archive in archives:
        stable_path_hash = hashlib.sha256(archive.archive_relative_path.encode("utf-8")).hexdigest()[:12]
        source_rows.append(
            {
                "source_id": f"datalab:{stable_path_hash}:{archive.archive_sha256[:12]}",
                "source_name": "한국관광 데이터랩 공식 다운로드",
                "source_page_url": "",
                "downloaded_at": "2026-08-31",
                "file_name": archive.archive_relative_path,
                "file_hash": archive.archive_sha256,
                "date_range": f"{archive.archive_period_start}~{archive.archive_period_end}".strip("~"),
                "geographic_level": "시군구",
                "unit": "CSV별 상이",
                "filters": f"지역={archive.region_folder};카테고리={archive.category}",
                "license_or_usage_note": "공식 다운로드 페이지의 이용조건 확인 필요",
                "methodology_notes": "CSV별 정의·단위 검토 필요",
                "status": "needs_review",
            }
        )
    write_csv(
        output_dir / "source_registry_generated.csv",
        list(source_rows[0].keys()) if source_rows else [],
        source_rows,
    )

    categories = Counter(archive.category for archive in archives)
    mapping_statuses = Counter(str(row["mapping_status"]) for row in region_rows)
    summary: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root),
        "region_count": len(region_dirs),
        "archive_count": len(archives),
        "archive_total_size_bytes": sum(archive.archive_size_bytes for archive in archives),
        "csv_entry_count": len(inventory_rows),
        "archive_status_counts": dict(Counter(archive.status for archive in archives)),
        "region_mapping_status_counts": dict(mapping_statuses),
        "category_archive_counts": dict(sorted(categories.items())),
        "issue_counts": dict(Counter(str(row["code"]) for row in issue_rows)),
        "outputs": {
            "archives": "archives.csv",
            "csv_schema_inventory": "csv_schema_inventory.csv",
            "region_code_candidates": "region_code_candidates.csv",
            "validation_issues": "validation_issues.csv",
            "source_registry_generated": "source_registry_generated.csv",
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


# 경로는 코드에 고정하지 않고 CLI 또는 환경변수로 받아 팀·AWS 환경에 대응한다.
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="관광데이터랩 공유폴더 읽기 전용 인벤토리")
    parser.add_argument(
        "--raw-root",
        default=os.getenv("TOURISM_RAW_ROOT", ""),
        help="원본 지역 폴더의 루트. 미지정 시 TOURISM_RAW_ROOT 사용",
    )
    parser.add_argument(
        "--output-dir",
        default="data/interim/nationwide_inventory",
        help="검사 결과 저장 폴더(기본: data/interim/nationwide_inventory)",
    )
    parser.add_argument("--max-regions", type=int, default=None, help="개발 확인용 지역 수 제한")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.raw_root:
        print("오류: --raw-root 또는 TOURISM_RAW_ROOT가 필요합니다.", file=sys.stderr)
        return 2
    raw_root = Path(args.raw_root)
    if not raw_root.is_dir():
        print(f"오류: 원본 폴더를 찾을 수 없습니다: {raw_root}", file=sys.stderr)
        return 2

    summary = build_inventory(raw_root, Path(args.output_dir), args.max_regions)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
