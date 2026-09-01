"""원본과 분리한 지역 데이터 카탈로그를 읽어 ML 등록 정보를 제공합니다."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / 'data' / 'catalog' / 'region_data_registry.csv'


@dataclass(frozen=True)
class RegionDataCatalogEntry:
    """한 지역의 코드·원본 위치·어댑터·출처 상태를 담는 읽기 전용 설정입니다."""

    region_code: str
    region_name: str
    short_name: str
    raw_relative_path: str
    adapter_type: str
    source_name: str
    source_url: str
    downloaded_at: str
    provenance_status: str
    enabled: bool

    @property
    def raw_path(self) -> Path:
        """카탈로그의 상대 경로를 현재 프로젝트의 안전한 원본 경로로 바꿉니다."""
        path = (PROJECT_ROOT / self.raw_relative_path).resolve()
        raw_root = (PROJECT_ROOT / 'data' / 'raw').resolve()
        if raw_root not in path.parents and path != raw_root:
            raise ValueError(f'ML_RAW_PATH_OUTSIDE_ROOT: {self.raw_relative_path}')
        return path


def list_region_data_catalog(*, enabled_only: bool = True) -> tuple[RegionDataCatalogEntry, ...]:
    """CSV 카탈로그를 읽고 중복 코드·누락 필드를 초기에 명확하게 거절합니다."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f'ML_REGION_CATALOG_MISSING: {CATALOG_PATH}')
    entries: list[RegionDataCatalogEntry] = []
    seen_codes: set[str] = set()
    with CATALOG_PATH.open(encoding='utf-8-sig', newline='') as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            required = ('region_code', 'region_name', 'short_name', 'raw_relative_path', 'adapter_type', 'source_name')
            if any(not str(row.get(key) or '').strip() for key in required):
                raise ValueError(f'ML_REGION_CATALOG_INVALID: {row_number}행 필수 값이 비어 있습니다.')
            region_code = str(row['region_code']).strip()
            if region_code in seen_codes:
                raise ValueError(f'ML_REGION_CATALOG_DUPLICATE: {region_code}')
            seen_codes.add(region_code)
            entry = RegionDataCatalogEntry(
                region_code=region_code,
                region_name=str(row['region_name']).strip(),
                short_name=str(row['short_name']).strip(),
                raw_relative_path=str(row['raw_relative_path']).strip(),
                adapter_type=str(row['adapter_type']).strip(),
                source_name=str(row['source_name']).strip(),
                source_url=str(row.get('source_url') or '').strip(),
                downloaded_at=str(row.get('downloaded_at') or '').strip(),
                provenance_status=str(row.get('provenance_status') or 'needs_provenance').strip(),
                enabled=str(row.get('enabled') or '').strip().lower() == 'true',
            )
            if not enabled_only or entry.enabled:
                entries.append(entry)
    return tuple(entries)


def get_region_data_catalog_entry(region_code: str) -> RegionDataCatalogEntry:
    """지역 코드로 카탈로그 한 줄을 찾아 모델·점검기가 같은 설정을 쓰게 합니다."""
    for entry in list_region_data_catalog(enabled_only=False):
        if entry.region_code == str(region_code):
            return entry
    raise ValueError(f'ML_REGION_CATALOG_NOT_FOUND: {region_code}')
