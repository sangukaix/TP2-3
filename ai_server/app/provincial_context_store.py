"""Read-only parent-province observations; never province planning/ML input."""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

from .nationwide_context_store import _connect

LOGGER = logging.getLogger(__name__)
RULE = ('소속 시도 전체의 관측 배경이다. 외지인 집계 경계가 시군구와 다르므로 '
        '총량·점유율·순위·인과효과·유사 지역 선정 점수로 쓰지 않는다. '
        '같은 월 전년 대비 증감률과 숙박 특성의 방향만 참고하며, ML 전망·목표율을 변경하지 않는다.')


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def _yoy(now: Any, before: Any) -> float | None:
    now, before = _number(now), _number(before)
    return round((now / before - 1) * 100, 2) if now is not None and before and before > 0 else None


def compare_observations(region_code: str, province_name: str, history: list[dict], rows: list[dict]) -> dict:
    """Same end-month only; missing/zero previous-year data never becomes a zero growth rate."""
    if len(region_code) != 5 or not history:
        return {'available': False, 'reason': '시군구 관측 이력이 없음'}
    selected = {str(r['year_month']).replace('-', '').replace('.', ''): r for r in history}
    month = max(selected)
    previous = str(int(month[:4]) - 1) + month[4:]
    province = {(str(r['year_month']), r['metric_name']): r for r in rows
                if str(r['province_code']) == region_code[:2] and r['province_name'] == province_name}
    comparisons = []
    used = []
    for metric, label, unit in [('visitors', '순 방문자 수 전년 동월 대비', '%'),
                                ('spending_krw', '외지인 관광소비 전년 동월 대비', '%'),
                                ('lodging_rate_pct', '숙박 방문 비율', '%'),
                                ('lodging_nights', '평균 숙박일수', '일')]:
        current = province.get((month, metric))
        if not current:
            continue
        if metric in {'visitors', 'spending_krw'}:
            old = province.get((previous, metric))
            if not old:
                continue
            local_value = _yoy(selected[month].get(metric), selected.get(previous, {}).get(metric))
            province_value = _yoy(current['metric_value'], old['metric_value'])
            provenance = [current, old]
        else:
            local_value = _number(selected[month].get(metric))
            province_value = _number(current['metric_value'])
            provenance = [current]
        if local_value is None or province_value is None:
            continue
        comparisons.append({'metric': metric, 'label': label, 'unit': unit,
            'district_value': round(local_value, 2), 'province_value': round(province_value, 2),
            'gap': round(local_value - province_value, 2), 'gap_unit': '%p' if unit == '%' else '일'})
        used.extend(provenance)
    if not comparisons:
        return {'available': False, 'reason': '동일 관측월의 소속 시도 자료가 없음'}
    digest = hashlib.sha256('|'.join(sorted({r['source_sha256'] for r in used})).encode()).hexdigest()[:12]
    source_id = f'province-context:{region_code}:{month}:{digest}'
    summary = f'{month[:4]}년 {month[4:]}월 관측 · {province_name} 전체와 비교. ' + ' / '.join(
        f"{r['label']}: 선택 시군구 {r['district_value']:g}{r['unit']}, 시도 {r['province_value']:g}{r['unit']}"
        for r in comparisons)
    return {'available': True, 'region_code': region_code, 'province_code': region_code[:2],
        'province_name': province_name, 'observation_month': month, 'previous_year_month': previous,
        'comparison_type': 'observed_parent_context', 'comparisons': comparisons, 'summary': summary,
        'read_rule': RULE, 'source_id': source_id,
        'source_records': [{'source_id': source_id, 'source_type': 'provincial_tourism_context',
            'title': f'한국관광 데이터랩 · {province_name} 상위 지역 관측 비교',
            'source_url': 'https://datalab.visitkorea.or.kr/', 'summary': summary + ' ' + RULE,
            'observation_period': month, 'published_or_updated_at': '',
            'source_files': sorted({r['source_file'] + ' :: ' + r['source_member'] for r in used}),
            'original_source_ids': sorted({r['source_id'] for r in used}),
            'source_review_status': 'official_download_local_snapshot'}]}


def load_provincial_context(region_code: str, history: list[dict], env_values: dict[str, Any]) -> dict:
    """Resolve district membership from MySQL; absent optional context cannot stop generation."""
    if len(region_code) != 5 or not history:
        return {'available': False}
    try:
        with _connect(env_values) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT province_name FROM dim_region WHERE region_code=%s', (region_code,))
                region = cursor.fetchone()
                if not region:
                    return {'available': False, 'reason': '등록된 시군구 소속 정보가 없음'}
                cursor.execute('SELECT * FROM provincial_tourism_monthly_context WHERE province_code=%s AND province_name=%s',
                               (region_code[:2], region['province_name']))
                rows = cursor.fetchall()
        return compare_observations(region_code, region['province_name'], history, rows)
    except Exception as exc:
        # Optional new table may not yet be installed on another team member's host.
        LOGGER.info('Province context unavailable for %s (%s)', region_code, type(exc).__name__)
        return {'available': False, 'reason': '상위 시도 보조 자료 연결 대기'}
