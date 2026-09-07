"""프로젝트 안의 수동 원본을 hash-검증 불변 snapshot으로 복제한다.

``data/raw``는 기존 수동 원본을 보관하는 읽기 전용 영역이다. 이 도구는 해당
원본을 바꾸거나 이동하지 않고, 명시한 하위 폴더의 파일을
``data/source_snapshots`` 아래에 같은 상대 구조로 한 번만 복제한다. 같은 이름의
서로 다른 파일은 절대 덮어쓰지 않아, 후속 갱신 자료가 과거 원본을 조용히 바꾸는
것을 막는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Sequence


MANIFEST_FIELDS = [
    "source_kind",
    "source_path",
    "source_sha256",
    "materialized_relative_path",
    "materialized_sha256",
    "size_bytes",
    "status",
]


def sha256_file(path: Path) -> str:
    """파일을 바꾸지 않고 SHA-256을 계산한다."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_destination(output_root: Path, destination_relative_path: Path) -> Path:
    """snapshot 보관소 밖으로 나가는 상대경로를 거절한다."""

    if destination_relative_path.is_absolute() or ".." in destination_relative_path.parts:
        raise ValueError(f"SNAPSHOT_DESTINATION_INVALID: {destination_relative_path}")
    resolved_root = output_root.resolve()
    destination = (resolved_root / destination_relative_path).resolve()
    if resolved_root != destination and resolved_root not in destination.parents:
        raise ValueError(f"SNAPSHOT_DESTINATION_OUTSIDE_ROOT: {destination_relative_path}")
    return destination


def _copy_file_once(source: Path, destination: Path) -> tuple[str, str]:
    """동일 hash만 재사용하며 기존 snapshot을 덮어쓰지 않는다."""

    source_hash = sha256_file(source)
    if destination.exists():
        if sha256_file(destination) != source_hash:
            raise ValueError(f"SNAPSHOT_DESTINATION_HASH_CONFLICT: {destination}")
        return "reused", source_hash

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.partial")
    if temporary.exists():
        raise FileExistsError(f"SNAPSHOT_PARTIAL_EXISTS: {temporary}")
    shutil.copyfile(source, temporary)
    copied_hash = sha256_file(temporary)
    if copied_hash != source_hash:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"SNAPSHOT_COPY_HASH_MISMATCH: {source}")
    temporary.replace(destination)
    return "materialized", source_hash


def materialize_local_source_snapshot(
    *,
    source_root: Path,
    output_root: Path,
    destination_relative_path: Path,
    manifest_dir: Path,
    source_kind: str = "local_raw_file",
) -> dict[str, object]:
    """한 원본 폴더를 변경 없이 snapshot으로 복제하고 hash manifest를 남긴다."""

    if not source_root.is_dir():
        raise FileNotFoundError(f"SNAPSHOT_SOURCE_ROOT_MISSING: {source_root}")
    if not source_kind.strip():
        raise ValueError("SNAPSHOT_SOURCE_KIND_MISSING")

    destination_root = _safe_destination(output_root, destination_relative_path)
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for source in sorted((path for path in source_root.rglob("*") if path.is_file()), key=lambda path: path.as_posix().lower()):
        relative = source.relative_to(source_root)
        destination = destination_root / relative
        try:
            status, digest = _copy_file_once(source, destination)
            rows.append(
                {
                    "source_kind": source_kind,
                    "source_path": str(source),
                    "source_sha256": digest,
                    "materialized_relative_path": destination.relative_to(output_root.resolve()).as_posix(),
                    "materialized_sha256": digest,
                    "size_bytes": source.stat().st_size,
                    "status": status,
                }
            )
        except (OSError, ValueError) as exc:
            errors.append({"source_path": str(source), "detail": str(exc)})

    manifest_dir.mkdir(parents=True, exist_ok=True)
    with (manifest_dir / "local_source_snapshot_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with (manifest_dir / "local_source_snapshot_errors.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "detail"])
        writer.writeheader()
        writer.writerows(errors)
    summary = {
        "source_file_count": len(rows) + len(errors),
        "materialized_count": sum(row["status"] == "materialized" for row in rows),
        "reused_count": sum(row["status"] == "reused" for row in rows),
        "error_count": len(errors),
        "output_root": str(output_root),
        "destination_relative_path": destination_relative_path.as_posix(),
    }
    (manifest_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="수동 원본 폴더의 hash-검증 snapshot 생성")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", default="data/source_snapshots")
    parser.add_argument("--destination-relative-path", required=True)
    parser.add_argument("--manifest-dir", required=True)
    parser.add_argument("--source-kind", default="local_raw_file")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = materialize_local_source_snapshot(
            source_root=Path(args.source_root),
            output_root=Path(args.output_root),
            destination_relative_path=Path(args.destination_relative_path),
            manifest_dir=Path(args.manifest_dir),
            source_kind=args.source_kind,
        )
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
