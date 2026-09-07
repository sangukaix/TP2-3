"""공유폴더의 지역별 ZIP을 프로젝트 원본 보관소에 불변 snapshot으로 복제한다.

공유폴더는 팀원 PC·네트워크 상태에 따라 접근 가능 여부가 달라진다. 이 도구는
강원도처럼 ``지역/분류/연도.zip``으로 내려받은 파일과, 서울처럼 바깥 ZIP 안에
지역별 ZIP이 들어 있는 묶음을 같은 ``data/source_snapshots/<시도>/<시군구>/`` 구조로 만든다.
원본 ZIP은 열어 읽기만 하며, 목적지에 이미 같은 이름의 다른 내용이 있으면
덮어쓰지 않고 중단한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

from .materialize_nested_archives import repair_member_name, safe_relative_member


MANIFEST_FIELDS = [
    "source_kind",
    "source_path",
    "source_sha256",
    "outer_source_sha256",
    "materialized_relative_path",
    "materialized_sha256",
    "size_bytes",
    "status",
]


def sha256_file(path: Path) -> str:
    """대용량 ZIP도 일정 크기로 읽어 재현 가능한 hash를 계산한다."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_bytes_once(destination: Path, raw: bytes) -> str:
    """동일 hash만 재사용하고 서로 다른 원본의 조용한 덮어쓰기를 막는다."""

    digest = sha256_bytes(raw)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing_digest = sha256_file(destination)
        if existing_digest != digest:
            raise ValueError(f"RAW_DESTINATION_HASH_CONFLICT: {destination}")
        return "reused"
    temporary = destination.with_suffix(f"{destination.suffix}.partial")
    if temporary.exists():
        temporary.unlink()
    temporary.write_bytes(raw)
    temporary.replace(destination)
    return "materialized"


def _write_file_once(source: Path, destination: Path) -> tuple[str, str]:
    """공유폴더의 직접 ZIP을 읽어 목적지 snapshot으로 한 번만 복제한다."""

    raw = source.read_bytes()
    return _write_bytes_once(destination, raw), sha256_bytes(raw)


def _iter_direct_archives(source_root: Path) -> Iterable[tuple[Path, Path]]:
    """강원처럼 지역 폴더 아래에 있는 공식 category ZIP만 반환한다."""

    for region_directory in sorted((item for item in source_root.iterdir() if item.is_dir()), key=lambda item: item.name):
        for archive in sorted(region_directory.rglob("*.zip"), key=lambda item: str(item).lower()):
            yield region_directory, archive


def materialize_regional_archives(
    *,
    gangwon_root: Path,
    seoul_outer_zip: Path,
    output_root: Path,
    manifest_dir: Path,
    conflict_snapshot_root: Path | None = None,
) -> dict[str, object]:
    """두 제공 형태를 프로젝트 내 읽기 전용 원본 snapshot으로 통합한다."""

    if not gangwon_root.is_dir():
        raise FileNotFoundError(f"GANGWON_SOURCE_ROOT_MISSING: {gangwon_root}")
    if not seoul_outer_zip.is_file() or not zipfile.is_zipfile(seoul_outer_zip):
        raise FileNotFoundError(f"SEOUL_OUTER_ZIP_INVALID: {seoul_outer_zip}")

    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    # 직접 원본은 category ZIP 자체가 제공기관 원본이므로 파일명·상대경로를 그대로 보존한다.
    for region_directory, archive in _iter_direct_archives(gangwon_root):
        relative = archive.relative_to(region_directory)
        province = region_directory.name.split("_", 1)[0]
        destination = output_root / province / region_directory.name / relative
        try:
            status, digest = _write_file_once(archive, destination)
            rows.append(
                {
                    "source_kind": "direct_region_archive",
                    "source_path": str(archive),
                    "source_sha256": digest,
                    "outer_source_sha256": "",
                    "materialized_relative_path": destination.relative_to(output_root).as_posix(),
                    "materialized_sha256": digest,
                    "size_bytes": archive.stat().st_size,
                    "status": status,
                }
            )
        except (OSError, ValueError) as exc:
            # 30일 집중률처럼 시점에 따라 바뀌는 공식 파일이 기존 snapshot과 같은
            # 경로·다른 hash로 들어올 수 있다. 기존 원본을 덮어쓰지 않고, 호출자가
            # 지정한 날짜별 보관소에만 별도 version snapshot을 만든다.
            if conflict_snapshot_root is not None and str(exc).startswith("RAW_DESTINATION_HASH_CONFLICT:"):
                versioned_destination = conflict_snapshot_root / province / region_directory.name / relative
                try:
                    status, digest = _write_file_once(archive, versioned_destination)
                    rows.append(
                        {
                            "source_kind": "versioned_conflict_archive",
                            "source_path": str(archive),
                            "source_sha256": digest,
                            "outer_source_sha256": "",
                            "materialized_relative_path": versioned_destination.relative_to(output_root).as_posix(),
                            "materialized_sha256": digest,
                            "size_bytes": archive.stat().st_size,
                            "status": "versioned_conflict_snapshot" if status == "materialized" else "versioned_conflict_reused",
                        }
                    )
                    continue
                except (OSError, ValueError) as versioned_exc:
                    errors.append({"source_path": str(archive), "detail": str(versioned_exc)})
                    continue
            errors.append({"source_path": str(archive), "detail": str(exc)})

    # 서울 바깥 ZIP도 보관해 inner ZIP과 부모 원본의 lineage를 모두 확인할 수 있게 한다.
    outer_digest = sha256_file(seoul_outer_zip)
    try:
        outer_destination = output_root / "downloads" / seoul_outer_zip.name
        outer_status, _ = _write_file_once(seoul_outer_zip, outer_destination)
        rows.append(
            {
                "source_kind": "outer_bundle",
                "source_path": str(seoul_outer_zip),
                "source_sha256": outer_digest,
                "outer_source_sha256": "",
                "materialized_relative_path": outer_destination.relative_to(output_root).as_posix(),
                "materialized_sha256": outer_digest,
                "size_bytes": seoul_outer_zip.stat().st_size,
                "status": outer_status,
            }
        )
    except (OSError, ValueError) as exc:
        errors.append({"source_path": str(seoul_outer_zip), "detail": str(exc)})

    # ZIP-slip을 막는 기존 safe_relative_member를 사용한다. 첫 서울 wrapper만 제거한 경로는
    # ``서울특별시_강남구/관광소비/2024_01_12.zip`` 형태가 된다.
    try:
        with zipfile.ZipFile(seoul_outer_zip) as outer:
            for member in outer.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".zip"):
                    continue
                source_name = repair_member_name(member.filename)
                try:
                    relative = safe_relative_member(member.filename)
                    if len(relative.parts) < 3:
                        raise ValueError("SEOUL_INNER_PATH_INVALID")
                    raw = outer.read(member)
                    if not zipfile.is_zipfile(io.BytesIO(raw)):
                        raise ValueError("SEOUL_INNER_ARCHIVE_INVALID")
                    destination = output_root / "서울특별시" / relative
                    status = _write_bytes_once(destination, raw)
                    inner_digest = sha256_bytes(raw)
                    rows.append(
                        {
                            "source_kind": "nested_region_archive",
                            "source_path": source_name,
                            "source_sha256": inner_digest,
                            "outer_source_sha256": outer_digest,
                            "materialized_relative_path": destination.relative_to(output_root).as_posix(),
                            "materialized_sha256": inner_digest,
                            "size_bytes": len(raw),
                            "status": status,
                        }
                    )
                except (OSError, ValueError, zipfile.BadZipFile) as exc:
                    errors.append({"source_path": source_name, "detail": str(exc)})
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append({"source_path": str(seoul_outer_zip), "detail": str(exc)})

    manifest_dir.mkdir(parents=True, exist_ok=True)
    with (manifest_dir / "regional_archive_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with (manifest_dir / "regional_archive_errors.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "detail"])
        writer.writeheader()
        writer.writerows(errors)
    summary = {
        "direct_archive_count": sum(row["source_kind"] == "direct_region_archive" for row in rows),
        "nested_archive_count": sum(row["source_kind"] == "nested_region_archive" for row in rows),
        "outer_bundle_count": sum(row["source_kind"] == "outer_bundle" for row in rows),
        "materialized_count": sum(row["status"] == "materialized" for row in rows),
        "reused_count": sum(row["status"] == "reused" for row in rows),
        "versioned_conflict_count": sum(str(row["status"]).startswith("versioned_conflict_") for row in rows),
        "error_count": len(errors),
        "output_root": str(output_root),
    }
    (manifest_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공유폴더 지역별 관광데이터 ZIP snapshot 생성")
    parser.add_argument("--gangwon-root", required=True)
    parser.add_argument("--seoul-outer-zip", required=True)
    parser.add_argument("--output-root", default="data/source_snapshots")
    parser.add_argument("--manifest-dir", default="data/interim/regional_archive_materialization")
    parser.add_argument(
        "--conflict-snapshot-root",
        default="",
        help="같은 경로·다른 hash 원본을 별도 보관할 output-root 하위 날짜 폴더",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = materialize_regional_archives(
            gangwon_root=Path(args.gangwon_root),
            seoul_outer_zip=Path(args.seoul_outer_zip),
            output_root=Path(args.output_root),
            manifest_dir=Path(args.manifest_dir),
            conflict_snapshot_root=Path(args.conflict_snapshot_root) if args.conflict_snapshot_root else None,
        )
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
