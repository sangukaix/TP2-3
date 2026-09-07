"""관광데이터랩 원본 ZIP·CSV를 읽기 전용으로 파싱하고 재사용합니다.

원본 파일은 절대 수정하지 않습니다. 파일 경로·크기·수정시각으로 만든 지문이
달라질 때만 다시 읽으므로, 팀원이 새 원본을 추가하면 서버 재시작 없이도 갱신됩니다.
"""

from __future__ import annotations

import csv
from functools import lru_cache
import io
from pathlib import Path
from typing import TypeAlias
import zipfile


TableRows: TypeAlias = dict[str, list[dict[str, str]]]
SourceFingerprint: TypeAlias = tuple[tuple[str, int, int], ...]
MAX_ARCHIVE_DEPTH = 3
MAX_ARCHIVE_ENTRIES = 1_500
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 500_000_000


def _decode_csv(raw: bytes) -> str:
    """데이터랩에서 주로 사용하는 한국어 CSV 인코딩을 안전하게 판별합니다."""
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('지역 원본 CSV 인코딩을 읽지 못했습니다.')


def _read_zip_tables(raw: bytes, *, label: str, tables: TableRows, depth: int = 0) -> None:
    """바깥 ZIP 안의 연도·지표별 ZIP까지 원본을 풀지 않고 메모리에서 읽습니다."""
    if depth > MAX_ARCHIVE_DEPTH:
        raise ValueError('지역 원본 ZIP의 중첩 깊이가 허용 범위를 넘었습니다.')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES or sum(entry.file_size for entry in entries) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError('지역 원본 ZIP의 파일 수 또는 압축 해제 크기가 허용 범위를 넘었습니다.')
        for entry in entries:
            lower_name = entry.filename.lower()
            if lower_name.endswith('.csv'):
                reader = csv.DictReader(io.StringIO(_decode_csv(archive.read(entry))))
                tables[f'{label}::{entry.filename}'] = [
                    {(key or '').strip(): (value or '').strip() for key, value in row.items()}
                    for row in reader
                ]
            elif lower_name.endswith('.zip'):
                _read_zip_tables(
                    archive.read(entry), label=f'{label}::{entry.filename}', tables=tables, depth=depth + 1,
                )


def _source_fingerprint(region_source: Path) -> SourceFingerprint:
    """원본 내용 변경을 감지하되, 매 요청마다 파일 본문을 다시 읽지는 않습니다."""
    if region_source.is_file() and region_source.suffix.lower() in {'.zip', '.csv'}:
        source_files = [region_source]
        base_directory = region_source.parent
    else:
        source_files = sorted(
            (
                path for path in region_source.rglob('*')
                if path.is_file() and path.suffix.lower() in {'.zip', '.csv'}
            ),
            key=lambda path: str(path.relative_to(region_source)).lower(),
        )
        base_directory = region_source
    return tuple(
        (
            str(path.relative_to(base_directory)),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in source_files
    )


@lru_cache(maxsize=32)
def _read_tables_cached(region_path: str, fingerprint: SourceFingerprint) -> TableRows:
    """검증된 지역 경로와 파일 지문 단위로 파싱 결과를 메모리에 보관합니다."""
    del fingerprint  # 캐시 키로만 사용하며 파일 내용 계산에는 필요하지 않습니다.
    region_source = Path(region_path)
    tables: TableRows = {}

    zip_paths = [region_source] if region_source.is_file() and region_source.suffix.lower() == '.zip' else region_source.rglob('*.zip')
    for zip_path in zip_paths:
        zip_label = zip_path.name if region_source.is_file() else str(zip_path.relative_to(region_source))
        _read_zip_tables(zip_path.read_bytes(), label=zip_label, tables=tables)

    csv_paths = [region_source] if region_source.is_file() and region_source.suffix.lower() == '.csv' else region_source.rglob('*.csv')
    for csv_path in csv_paths:
        reader = csv.DictReader(io.StringIO(_decode_csv(csv_path.read_bytes())))
        csv_label = csv_path.name if region_source.is_file() else str(csv_path.relative_to(region_source))
        tables[csv_label] = [
            {(key or '').strip(): (value or '').strip() for key, value in row.items()}
            for row in reader
        ]

    if not tables:
        raise FileNotFoundError('지역 원본 CSV 또는 ZIP 파일을 찾지 못했습니다.')
    return tables


def read_region_tables(region_source: Path) -> TableRows:
    """지역 원본 폴더 또는 카탈로그의 단일 ZIP/CSV를 읽고 같은 원본은 재사용합니다."""
    resolved = region_source.resolve()
    fingerprint = _source_fingerprint(resolved)
    if not fingerprint:
        raise FileNotFoundError('지역 원본 CSV 또는 ZIP 파일을 찾지 못했습니다.')
    return _read_tables_cached(str(resolved), fingerprint)


def raw_table_cache_info():
    """성능 테스트와 운영 점검에서 사용할 표준 캐시 통계입니다."""
    return _read_tables_cached.cache_info()
