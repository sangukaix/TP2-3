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


def _decode_csv(raw: bytes) -> str:
    """데이터랩에서 주로 사용하는 한국어 CSV 인코딩을 안전하게 판별합니다."""
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('지역 원본 CSV 인코딩을 읽지 못했습니다.')


def _source_fingerprint(region_directory: Path) -> SourceFingerprint:
    """원본 내용 변경을 감지하되, 매 요청마다 파일 본문을 다시 읽지는 않습니다."""
    source_files = sorted(
        (
            path for path in region_directory.rglob('*')
            if path.is_file() and path.suffix.lower() in {'.zip', '.csv'}
        ),
        key=lambda path: str(path.relative_to(region_directory)).lower(),
    )
    return tuple(
        (
            str(path.relative_to(region_directory)),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in source_files
    )


@lru_cache(maxsize=32)
def _read_tables_cached(region_path: str, fingerprint: SourceFingerprint) -> TableRows:
    """검증된 지역 경로와 파일 지문 단위로 파싱 결과를 메모리에 보관합니다."""
    del fingerprint  # 캐시 키로만 사용하며 파일 내용 계산에는 필요하지 않습니다.
    region_directory = Path(region_path)
    tables: TableRows = {}

    for zip_path in region_directory.rglob('*.zip'):
        with zipfile.ZipFile(zip_path) as archive:
            for file_name in archive.namelist():
                if not file_name.lower().endswith('.csv'):
                    continue
                reader = csv.DictReader(io.StringIO(_decode_csv(archive.read(file_name))))
                table_name = f'{zip_path.relative_to(region_directory)}::{file_name}'
                tables[table_name] = [
                    {(key or '').strip(): (value or '').strip() for key, value in row.items()}
                    for row in reader
                ]

    for csv_path in region_directory.rglob('*.csv'):
        reader = csv.DictReader(io.StringIO(_decode_csv(csv_path.read_bytes())))
        tables[str(csv_path.relative_to(region_directory))] = [
            {(key or '').strip(): (value or '').strip() for key, value in row.items()}
            for row in reader
        ]

    if not tables:
        raise FileNotFoundError('지역 원본 CSV 또는 ZIP 파일을 찾지 못했습니다.')
    return tables


def read_region_tables(region_directory: Path) -> TableRows:
    """지역 원본 표를 읽고, 동일한 원본이면 이전 파싱 결과를 반환합니다."""
    resolved = region_directory.resolve()
    fingerprint = _source_fingerprint(resolved)
    if not fingerprint:
        raise FileNotFoundError('지역 원본 CSV 또는 ZIP 파일을 찾지 못했습니다.')
    return _read_tables_cached(str(resolved), fingerprint)


def raw_table_cache_info():
    """성능 테스트와 운영 점검에서 사용할 표준 캐시 통계입니다."""
    return _read_tables_cached.cache_info()
