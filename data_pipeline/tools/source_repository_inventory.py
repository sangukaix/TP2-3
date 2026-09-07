"""팀 공유폴더 전체의 새 파일·변경 파일·삭제 파일을 추적한다.

세부 지역 ZIP 전처리 전에 상위 자료 보관소의 모든 파일을 source registry로
관리한다. 이전 목록과 크기·수정시각이 같으면 hash와 CSV profile을 재사용한다.
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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

try:
    from .data_inventory import decode_csv, sha256_file
except ModuleNotFoundError:  # pragma: no cover - tools 폴더 직접 실행
    from data_inventory import decode_csv, sha256_file


FILE_FIELDS = [
    "relative_path",
    "section",
    "extension",
    "size_bytes",
    "modified_at_utc",
    "sha256",
    "zip_entry_count",
    "zip_csv_entry_count",
    "change_status",
    "scan_status",
    "issues",
]
CSV_FIELDS = [
    "relative_path",
    "encoding",
    "row_count",
    "columns_json",
    "likely_multi_header",
    "status",
    "issues",
]
SECTION_USAGE_ROLES = {
    "전국데이타_20260831": "core_monthly_fact_and_ml",
    "전국 현황": "national_benchmark",
    "지역별 관광현황": "regional_benchmark",
    "외래객 지역별 방한현황": "foreign_market_diagnostic",
    "인기관광지 현황": "attraction_audience_diagnostic",
    "중심-연관 관광지 지도": "attraction_network_evidence",
    "지역별 관광지 관광객 현황표": "attraction_monthly_fact",
    "방문자기준지역방문현황": "pending_source_data",
    "(root)": "deduplication_review",
}


def make_source_id(relative_path: str, file_hash: str) -> str:
    """내용이 같아도 원본 경로가 다르면 구분되는 안정적 source ID를 만든다."""

    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"team-repo:{path_hash}:{file_hash[:12]}"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# 직접 CSV는 헤더·행 수와 2행 헤더 가능성만 검사하고 원본 값은 수정하지 않는다.
def profile_direct_csv(path: Path, relative_path: str) -> dict[str, object]:
    issues: list[str] = []
    try:
        text, encoding = decode_csv(path.read_bytes())
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        row_count = sum(1 for row in reader if any(str(value).strip() for value in row))
        likely_multi_header = any(
            not str(column).strip() or str(column).strip().startswith("Unnamed") for column in header
        )
        if likely_multi_header:
            issues.append("다중 헤더 또는 병합 셀 형식 가능성")
        if not header:
            issues.append("CSV 헤더 없음")
        return {
            "relative_path": relative_path,
            "encoding": encoding,
            "row_count": row_count,
            "columns_json": json.dumps([str(column).strip() for column in header], ensure_ascii=False),
            "likely_multi_header": likely_multi_header,
            "status": "ok" if not issues else "warning",
            "issues": " | ".join(issues),
        }
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return {
            "relative_path": relative_path,
            "encoding": "unknown",
            "row_count": 0,
            "columns_json": "[]",
            "likely_multi_header": False,
            "status": "error",
            "issues": str(exc),
        }


def load_previous(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {row[key]: row for row in csv.DictReader(source)}


def build_repository_inventory(
    root: Path, output_dir: Path, *, full_hash: bool = False
) -> dict[str, object]:
    """상위 저장소 전체 파일을 증분 검사하고 source 목록을 만든다."""

    previous_files = load_previous(output_dir / "files.csv", "relative_path")
    previous_csv = load_previous(output_dir / "direct_csv_schemas.csv", "relative_path")
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: str(path))
    file_rows: list[dict[str, object]] = []
    csv_rows: list[dict[str, object]] = []
    current_paths: set[str] = set()

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        current_paths.add(relative_path)
        section = relative_path.split("/", 1)[0] if "/" in relative_path else "(root)"
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        previous = previous_files.get(relative_path)
        metadata_unchanged = bool(
            previous
            and previous.get("size_bytes") == str(stat.st_size)
            and previous.get("modified_at_utc") == modified_at
        )
        # 일반 증분 실행은 크기·수정시각이 같은 파일의 hash를 재사용한다. 정기 감사에서는
        # --full-hash로 모든 파일을 다시 읽어 같은 메타데이터로 교체된 원본도 찾는다.
        unchanged = metadata_unchanged and not full_hash
        issues: list[str] = []
        zip_entry_count = 0
        zip_csv_entry_count = 0

        if unchanged:
            digest = previous.get("sha256", "")
            zip_entry_count = int(previous.get("zip_entry_count") or 0)
            zip_csv_entry_count = int(previous.get("zip_csv_entry_count") or 0)
            scan_status = previous.get("scan_status", "ok")
            previous_issues = previous.get("issues", "")
            if previous_issues:
                issues.append(previous_issues)
        else:
            digest = sha256_file(path)
            scan_status = "ok"
            if path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(path) as archive:
                        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                        zip_entry_count = len(entries)
                        zip_csv_entry_count = sum(
                            entry.filename.lower().endswith(".csv") for entry in entries
                        )
                        if not entries:
                            scan_status = "warning"
                            issues.append("빈 ZIP")
                except (OSError, zipfile.BadZipFile) as exc:
                    scan_status = "error"
                    issues.append(f"ZIP 읽기 실패: {exc}")

        if previous and digest != previous.get("sha256", ""):
            change_status = "changed"
        elif previous:
            change_status = "verified_unchanged" if full_hash else "unchanged"
        else:
            change_status = "new"
        file_rows.append(
            {
                "relative_path": relative_path,
                "section": section,
                "extension": path.suffix.lower() or "(none)",
                "size_bytes": stat.st_size,
                "modified_at_utc": modified_at,
                "sha256": digest,
                "zip_entry_count": zip_entry_count,
                "zip_csv_entry_count": zip_csv_entry_count,
                "change_status": change_status,
                "scan_status": scan_status,
                "issues": " | ".join(issues),
            }
        )

        if path.suffix.lower() == ".csv":
            if unchanged and relative_path in previous_csv:
                csv_rows.append(dict(previous_csv[relative_path]))
            else:
                csv_rows.append(profile_direct_csv(path, relative_path))

    deleted_rows = [
        {
            "relative_path": relative_path,
            "section": previous.get("section", ""),
            "extension": previous.get("extension", ""),
            "size_bytes": previous.get("size_bytes", ""),
            "modified_at_utc": previous.get("modified_at_utc", ""),
            "sha256": previous.get("sha256", ""),
            "zip_entry_count": previous.get("zip_entry_count", ""),
            "zip_csv_entry_count": previous.get("zip_csv_entry_count", ""),
            "change_status": "deleted",
            "scan_status": "warning",
            "issues": "이전 inventory에는 있으나 현재 공유폴더에서 찾을 수 없음",
        }
        for relative_path, previous in previous_files.items()
        if relative_path not in current_paths
    ]

    write_csv(output_dir / "files.csv", FILE_FIELDS, file_rows)
    write_csv(output_dir / "direct_csv_schemas.csv", CSV_FIELDS, csv_rows)
    write_csv(output_dir / "deleted_files.csv", FILE_FIELDS, deleted_rows)

    source_rows: list[dict[str, object]] = []
    for row in file_rows:
        source_rows.append(
            {
                "source_id": make_source_id(str(row["relative_path"]), str(row["sha256"])),
                "relative_path": row["relative_path"],
                "section": row["section"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "review_status": "needs_review",
                "usage_role": SECTION_USAGE_ROLES.get(str(row["section"]), "unclassified"),
            }
        )
    write_csv(
        output_dir / "source_registry_generated.csv",
        [
            "source_id",
            "relative_path",
            "section",
            "sha256",
            "size_bytes",
            "review_status",
            "usage_role",
        ],
        source_rows,
    )

    summary: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(root),
        "file_count": len(file_rows),
        "total_size_bytes": sum(int(row["size_bytes"]) for row in file_rows),
        "section_counts": dict(Counter(str(row["section"]) for row in file_rows)),
        "extension_counts": dict(Counter(str(row["extension"]) for row in file_rows)),
        "change_counts": dict(Counter(str(row["change_status"]) for row in file_rows + deleted_rows)),
        "scan_status_counts": dict(Counter(str(row["scan_status"]) for row in file_rows)),
        "direct_csv_count": len(csv_rows),
        "multi_header_csv_count": sum(str(row["likely_multi_header"]).lower() == "true" for row in csv_rows),
        "deleted_file_count": len(deleted_rows),
        "hash_mode": "full" if full_hash else "incremental",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="팀 관광 데이터 저장소 증분 inventory")
    parser.add_argument("--repository-root", default=os.getenv("TOURISM_REPOSITORY_ROOT", ""))
    parser.add_argument("--output-dir", default="data/interim/source_repository_inventory")
    parser.add_argument(
        "--full-hash",
        action="store_true",
        help="크기·수정시각과 무관하게 모든 원본의 SHA-256을 다시 계산합니다.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.repository_root)
    if not args.repository_root or not root.is_dir():
        print("오류: 유효한 --repository-root 또는 TOURISM_REPOSITORY_ROOT가 필요합니다.", file=sys.stderr)
        return 2
    summary = build_repository_inventory(root, Path(args.output_dir), full_hash=args.full_hash)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
