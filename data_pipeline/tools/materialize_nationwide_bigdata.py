"""공유폴더의 전국 빅데이터 ZIP을 불변 snapshot으로 복제한다.

원본은 읽기만 하며 ``data/raw``에는 절대 쓰지 않는다. 같은 이름이더라도 hash가
다르면 덮어쓰지 않아, 팀 공유폴더의 후속 변경과 이미 사용한 분석 입력을 구분한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


MANIFEST_FIELDS = (
    "relative_path", "source_path", "source_sha256", "materialized_relative_path",
    "size_bytes", "status",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_once(source: Path, destination: Path) -> str:
    source_hash = sha256_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(destination) != source_hash:
            raise ValueError(f"SNAPSHOT_HASH_CONFLICT: {destination}")
        return "reused"
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.unlink(missing_ok=True)
    with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
    if sha256_file(temporary) != source_hash:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"SNAPSHOT_COPY_HASH_MISMATCH: {source.name}")
    temporary.replace(destination)
    return "materialized"


def materialize_nationwide_bigdata(*, source_root: Path, output_root: Path, manifest_dir: Path) -> dict[str, object]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"NATIONWIDE_BIGDATA_SOURCE_MISSING: {source_root}")
    archives = sorted((path for path in source_root.rglob("*.zip") if path.is_file()), key=lambda item: item.as_posix())
    if not archives:
        raise ValueError("NATIONWIDE_BIGDATA_ARCHIVES_MISSING")
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for source in archives:
        relative = source.relative_to(source_root)
        destination = output_root / relative
        try:
            rows.append({
                "relative_path": relative.as_posix(), "source_path": str(source),
                "source_sha256": sha256_file(source),
                "materialized_relative_path": destination.relative_to(output_root).as_posix(),
                "size_bytes": source.stat().st_size, "status": _copy_once(source, destination),
            })
        except (OSError, ValueError) as exc:
            errors.append({"source_path": str(source), "detail": str(exc)})
    manifest_dir.mkdir(parents=True, exist_ok=True)
    with (manifest_dir / "nationwide_bigdata_snapshot_manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "source_kind": "team_shared_nationwide_bigdata_datalab_downloads",
        "source_root": str(source_root), "snapshot_root": str(output_root),
        "archive_count": len(rows), "materialized_count": sum(row["status"] == "materialized" for row in rows),
        "reused_count": sum(row["status"] == "reused" for row in rows), "error_count": len(errors),
        "materialized_at": datetime.now(timezone.utc).isoformat(),
        "rule": "공유 원본을 수정하지 않고 data/source_snapshots에 hash 고정 사본으로 보관한다.",
    }
    (manifest_dir / "nationwide_bigdata_snapshot_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (manifest_dir / "nationwide_bigdata_snapshot_errors.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("source_path", "detail"))
        writer.writeheader()
        writer.writerows(errors)
    if errors:
        raise ValueError(f"NATIONWIDE_BIGDATA_SNAPSHOT_ERRORS: {len(errors)}")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전국 빅데이터 ZIP 불변 snapshot 생성")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", default="data/source_snapshots/nationwide_bigdata/20260820")
    parser.add_argument("--manifest-dir", default="data/interim/nationwide_bigdata_snapshot")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = materialize_nationwide_bigdata(source_root=Path(args.source_root), output_root=Path(args.output_root), manifest_dir=Path(args.manifest_dir))
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
