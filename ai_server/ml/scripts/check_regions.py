"""새 지역 원자료의 ML 등록 가능 여부를 OpenAI 없이 점검하는 관리 CLI입니다."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..gangnam_data import load_gangnam_monthly_demand
from ..region_catalog import RegionDataCatalogEntry, list_region_data_catalog
from ..regional_datalab_data import StandardDatalabRegion, load_standard_datalab_monthly_demand


def _source_warnings(entry: RegionDataCatalogEntry) -> list[str]:
    """출처 URL·다운로드 일시가 빠져도 원본을 만들지 않고 사람이 보완할 항목만 알려 줍니다."""
    warnings = []
    if not entry.source_url.startswith('https://'):
        warnings.append('SOURCE_URL_MISSING')
    if not entry.downloaded_at:
        warnings.append('DOWNLOAD_DATE_MISSING')
    if entry.provenance_status != 'verified':
        warnings.append(f'PROVENANCE_{entry.provenance_status.upper()}')
    return warnings


def check_region(entry: RegionDataCatalogEntry) -> dict[str, Any]:
    """한 지역의 원본 위치·표 구조·공통 월·출처 상태를 JSON 한 줄로 정리합니다."""
    result: dict[str, Any] = {
        'region_code': entry.region_code,
        'region_name': entry.region_name,
        'adapter_type': entry.adapter_type,
        'status': 'failed',
        'source_warnings': _source_warnings(entry),
    }
    try:
        if entry.adapter_type == 'snapshot_gangnam_overlay':
            frame = load_gangnam_monthly_demand()
        elif entry.adapter_type in {'standard_datalab_csv', 'standard_datalab_archive'}:
            spec = StandardDatalabRegion(
                region_code=entry.region_code,
                region_name=entry.region_name,
                short_name=entry.short_name,
                raw_directory=entry.raw_path,
            )
            frame = load_standard_datalab_monthly_demand(spec)
        else:
            raise ValueError(f'ML_ADAPTER_TYPE_UNKNOWN: {entry.adapter_type}')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['error_code'] = str(exc).split(':', 1)[0]
        result['message'] = str(exc)
        return result
    result.update({
        'status': 'ready' if not result['source_warnings'] else 'ready_with_provenance_warnings',
        'source_period': f"{frame['year_month'].iloc[0]}~{frame['year_month'].iloc[-1]}",
        'observation_count': len(frame),
        'targets': [column for column in frame.columns if column not in {'region_code', 'region_name', 'year_month'}],
    })
    return result


def main() -> None:
    """선택한 카탈로그 지역 또는 전체 활성 지역의 준비 상태를 반환합니다."""
    # Windows PowerShell 기본 CP949에서도 지역명과 검증 메시지가 깨지지 않게 한다.
    # 원자료·모델·카탈로그의 인코딩이나 내용은 변경하지 않는다.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description='관광 원자료의 지역별 ML 등록 가능 여부를 점검합니다.')
    parser.add_argument('--region-code', action='append', default=[], help='점검할 시군구 코드. 여러 번 입력 가능')
    parser.add_argument('--all', action='store_true', help='카탈로그에서 enabled=true인 모든 지역 점검')
    args = parser.parse_args()
    # 특정 코드 점검은 아직 화면에 공개하지 않은 enabled=false 후보도 검사할 수 있어야 합니다.
    # --all만 현재 공개 대상으로 제한해 미검증 후보가 학습·대시보드에 섞이지 않게 합니다.
    entries = list_region_data_catalog(enabled_only=not bool(args.region_code))
    codes = set(args.region_code)
    if not args.all and not codes:
        parser.error('--region-code 또는 --all 중 하나가 필요합니다.')
    selected = [entry for entry in entries if args.all or entry.region_code in codes]
    unknown = codes - {entry.region_code for entry in entries}
    results = [check_region(entry) for entry in selected]
    results.extend({'region_code': code, 'status': 'failed', 'error_code': 'ML_REGION_CATALOG_NOT_FOUND'} for code in sorted(unknown))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
