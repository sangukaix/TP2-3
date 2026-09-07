"""공유폴더의 지역별 관광 현황 묶음을 불변 snapshot으로 복제한다.

이 도구는 원본과 내부 ZIP을 수정·재압축·추출하지 않는다. 공유폴더가 끊겨도
같은 입력을 재현할 수 있도록 바깥 ZIP 한 개와 SHA-256, 내부 archive 개수만
기록한다. 실제 CSV 해석은 ``build_regional_tourism_status.py``가 담당한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def sha256_file(path: Path) -> str:
    """대용량 ZIP도 일정 단위로 읽어 원본 지문을 계산한다."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_once(source: Path, destination: Path) -> str:
    """동일한 파일만 재사용하고, 다른 hash의 조용한 덮어쓰기는 차단한다."""

    source_hash = sha256_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(destination) != source_hash:
            raise ValueError(f"SNAPSHOT_HASH_CONFLICT: {destination}")
        return "reused"

    temporary = destination.with_suffix(destination.suffix + ".partial")
    if temporary.exists():
        # 직전 중단으로 남은, 정확히 이 목적지의 부분 파일만 다시 만듭니다.
        temporary.unlink()
    with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
    if sha256_file(temporary) != source_hash:
        temporary.unlink(missing_ok=True)
        raise ValueError("SNAPSHOT_COPY_HASH_MISMATCH")
    temporary.replace(destination)
    return "materialized"


def materialize_regional_tourism_status(
    *, source_zip: Path, snapshot_root: Path, manifest_dir: Path
) -> dict[str, object]:
    """바깥 ZIP 자체를 보관하고 안의 제공 범위는 manifest로만 기록한다."""

    if not source_zip.is_file() or not zipfile.is_zipfile(source_zip):
        raise FileNotFoundError(f"REGIONAL_TOURISM_STATUS_ZIP_INVALID: {source_zip}")

    source_hash = sha256_file(source_zip)
    destination = snapshot_root / source_zip.name
    status = copy_once(source_zip, destination)
    with zipfile.ZipFile(source_zip) as archive:
        nested = [member for member in archive.infolist() if not member.is_dir() and member.filename.lower().endswith(".zip")]
        municipality = [member for member in nested if member.filename.split("/", 1)[0] == "시군구"]
        province = [member for member in nested if member.filename.split("/", 1)[0] == "시도"]

    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_kind": "regional_tourism_status_outer_bundle",
        "source_path": str(source_zip),
        "snapshot_relative_path": destination.name,
        "source_sha256": source_hash,
        "size_bytes": source_zip.stat().st_size,
        "status": status,
        "archive_entry_count": len(nested),
        "municipality_archive_count": len(municipality),
        "province_archive_count": len(province),
        "materialized_at": datetime.now(timezone.utc).isoformat(),
        "rule": "원본 ZIP은 data/raw를 바꾸지 않고 data/source_snapshots에 불변 보관한다.",
    }
    (manifest_dir / "regional_tourism_status_snapshot.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지역별 관광 현황 ZIP snapshot 생성")
    parser.add_argument("--source-zip", required=True)
    parser.add_argument("--snapshot-root", default="data/source_snapshots/regional_tourism_status")
    parser.add_argument("--manifest-dir", default="data/interim/regional_tourism_status_snapshot")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = materialize_regional_tourism_status(
            source_zip=Path(args.source_zip),
            snapshot_root=Path(args.snapshot_root),
            manifest_dir=Path(args.manifest_dir),
        )
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
