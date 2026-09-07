"""팀 공유폴더의 중첩 ZIP을 검증된 지역별 ZIP snapshot으로 펼친다.

Google Drive 일괄 다운로드처럼 바깥 ZIP 안에 Data Lab ZIP이 다시 들어 있는 경우를
처리한다. 바깥 원본은 수정하지 않으며, 각 안쪽 ZIP의 hash와 부모 원본을 manifest로
남겨 전체 lineage를 보존한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Sequence


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_id(prefix: str, relative_path: str, digest: str) -> str:
    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{path_hash}:{digest[:12]}"


def repair_member_name(name: str) -> str:
    """UTF-8 flag 없이 CP949로 저장돼 CP437로 잘못 읽힌 파일명을 복원한다."""

    try:
        repaired = name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        repaired = name
    return unicodedata.normalize("NFC", repaired).replace("\\", "/")


def safe_relative_member(name: str) -> Path:
    """절대경로와 ..를 거부하고 바깥 ZIP의 최상위 묶음 폴더를 제거한다."""

    path = PurePosixPath(repair_member_name(name))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"안전하지 않은 ZIP 경로: {name}")
    parts = [part for part in path.parts if part not in {"", "."}]
    # 바깥 ZIP의 '서울특별시/서울특별시_강남구/...' 같은 첫 묶음 폴더만 제거한다.
    if len(parts) >= 2 and "_" not in parts[0] and parts[1].startswith(f"{parts[0]}_"):
        parts = parts[1:]
    if not parts:
        raise ValueError(f"비어 있는 ZIP 경로: {name}")
    return Path(*parts)


def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "outer_source_id",
        "outer_relative_path",
        "outer_sha256",
        "inner_source_id",
        "inner_original_name",
        "materialized_relative_path",
        "inner_sha256",
        "inner_size_bytes",
        "status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def materialize_nested_archives(
    repository_root: Path,
    inventory_csv: Path,
    output_root: Path,
    manifest_dir: Path,
) -> dict[str, object]:
    """지역별 관광현황의 중첩 ZIP 전체를 로컬 immutable snapshot으로 만든다."""

    candidates = [
        row
        for row in read_inventory(inventory_csv)
        if row.get("section") == "지역별 관광현황"
        and row.get("extension") == ".zip"
        and int(row.get("zip_csv_entry_count") or 0) == 0
    ]
    manifest: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for outer in candidates:
        outer_path = repository_root / Path(outer["relative_path"])
        outer_source = source_id("team-repo", outer["relative_path"], outer["sha256"])
        try:
            with zipfile.ZipFile(outer_path) as archive:
                for member in archive.infolist():
                    if member.is_dir() or not member.filename.lower().endswith(".zip"):
                        continue
                    try:
                        relative = safe_relative_member(member.filename)
                        raw = archive.read(member)
                        # 중첩 항목도 실제 ZIP인지 확인한 뒤에만 snapshot에 기록한다.
                        if not zipfile.is_zipfile(io.BytesIO(raw)):
                            raise ValueError("내부 항목이 유효한 ZIP이 아님")
                        inner_hash = digest_bytes(raw)
                        destination = output_root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if destination.exists() and digest_bytes(destination.read_bytes()) != inner_hash:
                            raise ValueError("같은 경로에 내용이 다른 ZIP이 이미 존재함")
                        if not destination.exists():
                            destination.write_bytes(raw)
                        materialized_path = relative.as_posix()
                        manifest.append(
                            {
                                "outer_source_id": outer_source,
                                "outer_relative_path": outer["relative_path"],
                                "outer_sha256": outer["sha256"],
                                "inner_source_id": source_id(
                                    "datalab", materialized_path, inner_hash
                                ),
                                "inner_original_name": repair_member_name(member.filename),
                                "materialized_relative_path": materialized_path,
                                "inner_sha256": inner_hash,
                                "inner_size_bytes": len(raw),
                                "status": "materialized",
                            }
                        )
                    except (OSError, ValueError, zipfile.BadZipFile) as exc:
                        errors.append(
                            {
                                "outer_relative_path": outer["relative_path"],
                                "member_name": repair_member_name(member.filename),
                                "detail": str(exc),
                            }
                        )
        except (OSError, zipfile.BadZipFile) as exc:
            errors.append(
                {
                    "outer_relative_path": outer["relative_path"],
                    "member_name": "",
                    "detail": str(exc),
                }
            )

    write_csv(manifest_dir / "nested_archive_manifest.csv", manifest)
    error_path = manifest_dir / "nested_archive_errors.csv"
    error_path.parent.mkdir(parents=True, exist_ok=True)
    with error_path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=["outer_relative_path", "member_name", "detail"]
        )
        writer.writeheader()
        writer.writerows(errors)

    summary: dict[str, object] = {
        "outer_archive_count": len(candidates),
        "inner_archive_count": len(manifest),
        "materialized_region_count": len(
            {Path(str(row["materialized_relative_path"])).parts[0] for row in manifest}
        ),
        "error_count": len(errors),
        "output_root": str(output_root),
    }
    (manifest_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="중첩 Data Lab ZIP snapshot 생성")
    parser.add_argument("--repository-root", default=os.getenv("TOURISM_REPOSITORY_ROOT", ""))
    parser.add_argument(
        "--inventory-csv", default="data/interim/source_repository_inventory/files.csv"
    )
    parser.add_argument(
        "--output-root", default="data/raw/materialized/region_archives"
    )
    parser.add_argument(
        "--manifest-dir", default="data/interim/nested_archive_materialization"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repository_root = Path(args.repository_root)
    if not args.repository_root or not repository_root.is_dir():
        print("오류: 유효한 팀 공유폴더 root가 필요합니다.", file=sys.stderr)
        return 2
    print(
        json.dumps(
            materialize_nested_archives(
                repository_root,
                Path(args.inventory_csv),
                Path(args.output_root),
                Path(args.manifest_dir),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
