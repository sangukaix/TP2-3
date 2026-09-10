"""Word·PowerPoint가 공유하는 기획 기간/목표 계산입니다. 모델을 학습하거나 호출하지 않습니다.

관측 공백을 메우는 내부 예측 월과 실제 사업 월을 구분합니다. 문서마다 배열 앞부분을
자르거나 서로 다른 목표 산식을 쓰지 않고, 저장된 보고서의 기간과 수치만 사용합니다.
"""

from __future__ import annotations

import math
import re
from typing import Any


def _month(value: Any) -> str:
    """월 키를 검증한 뒤 YYYYMM으로 통일합니다. 잘못된 월을 보정하지 않습니다."""
    text = str(value or '').strip()
    match = re.fullmatch(r'(20\d{2})[-./년]?\s*(\d{1,2})월?', text)
    if not match or not 1 <= int(match[2]) <= 12:
        return ''
    return match[1] + match[2].zfill(2)


def _index(month: str) -> int:
    return int(month[:4]) * 12 + int(month[4:]) - 1


def _add_months(month: str, offset: int) -> str:
    year, zero_month = divmod(_index(month) + offset, 12)
    return f'{year:04d}{zero_month + 1:02d}'


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def execution_target(report: dict[str, Any]) -> tuple[float, float] | None:
    """목표는 두 비율이 명시적으로 입력된 경우만 사용하며 기본 증가율을 만들지 않습니다."""
    scenario = report.get('execution_scenario') or report.get('planning_brief') or {}
    visitors = _number(scenario.get('visitor_target_pct'))
    spending = _number(scenario.get('spending_target_pct'))
    if visitors is None or spending is None or visitors > 20 or spending > 30:
        return None
    return visitors, spending


def target_series(natural: list[float], target_pct: float) -> list[float]:
    """최종 월 목표율까지 월별로 균등하게 접근하는 검토값입니다. 사업효과 예측이 아닙니다."""
    count = len(natural)
    return [value * (1 + target_pct / 100 * (index + 1) / count)
            for index, value in enumerate(natural)]


def visitor_linked_spending(visitors: list[float], spending: list[float],
                            target_visitors: list[float]) -> dict[str, Any]:
    """같은 월 소비/방문 비율을 추가 방문에 적용한 기획 가정. 실제 객단가가 아닙니다.

    방문이 0이면 비율을 추정하지 않고 None을 반환합니다. 입력값은 변경하지 않습니다.
    """
    if len(visitors) != len(spending) or len(visitors) != len(target_visitors):
        raise ValueError('방문·소비·목표의 월 수가 같아야 합니다.')
    if any(_number(v) is None for series in (visitors, spending, target_visitors) for v in series):
        raise ValueError('방문·소비·목표는 유한한 0 이상의 수여야 합니다.')
    ratios = [s / v if v > 0 else None for v, s in zip(visitors, spending)]
    targets = [s + (t - v) * ratio if ratio is not None else None
               for v, s, t, ratio in zip(visitors, spending, target_visitors, ratios)]
    return {'ratios': ratios, 'targets': targets}


def select_report_forecast(report: dict[str, Any]) -> dict[str, Any]:
    """최종 기획 기간에 해당하는 월만 선택하고 누락·범위 밖·모호한 기간은 명시합니다.

    우선순위: 최종안 명시 연월 → 최종안 개월 수와 일치하는 후보 → 확정 희망 일정.
    기간을 식별할 수 없는 신규 보고서는 첫 후보를 임의로 선택하지 않습니다.
    기간 정책이 없던 구형 저장 보고서만 제한된 호환 경로를 사용합니다.
    """
    ml = report.get('ml_analysis') or {}
    empty = {'rows': [], 'period': '', 'complete': False, 'notes': [], 'selection_basis': 'unavailable'}
    if ml.get('status') != 'available' or not ml.get('forecasts'):
        return {**empty, 'notes': ['사용 가능한 저장 ML 전망이 없습니다.']}

    # 중복 월·NaN·누락값을 0으로 바꾸면 합계와 차트가 왜곡되므로 해당 결과를 거절합니다.
    rows: dict[str, dict[str, Any]] = {}
    for item in ml['forecasts']:
        month = _month(item.get('month'))
        visitors, spending = _number(item.get('visitors')), _number(item.get('spending_krw'))
        if not month or month in rows or visitors is None or spending is None:
            return {**empty, 'notes': ['ML 월별 값의 누락·중복·유효하지 않은 수치를 확인해야 합니다.']}
        rows[month] = {**item, 'month': month, 'visitors': visitors, 'spending_krw': spending}

    policy = ml.get('horizon_policy') or {}
    windows = policy.get('decision_windows') or []
    strategy = next(iter(report.get('strategies') or []), {})
    timeframe = str(strategy.get('timeframe') or '')
    months = [_month(match[0]) for match in re.finditer(
        r'(?<!\d)20\d{2}[-./년]?\s*(?:1[0-2]|0?[1-9])(?:월|\b)', timeframe)]
    months = list(dict.fromkeys(month for month in months if month))
    duration_match = re.search(r'(?<![\d~∼–-])(\d{1,2})\s*개월', timeframe)
    duration = int(duration_match[1]) if duration_match else None
    # "3~6개월"처럼 미선택 범위는 6개월 선택으로 오인하지 않습니다.
    if re.search(r'\d\s*[~∼–-]\s*\d+\s*개월', timeframe):
        duration = None
    start = end = ''
    basis = 'strategy_timeframe'
    if len(months) >= 2:
        start, end = months[0], months[-1]
    elif len(months) == 1 and duration:
        start, end = months[0], _add_months(months[0], duration - 1)
    else:
        matching = [window for window in windows if window.get('months') == duration] if duration else []
        if len(matching) == 1:
            start, end = _month(matching[0].get('start_month')), _month(matching[0].get('end_month'))
            basis = 'selected_duration_window'
        elif policy.get('selection_basis') == 'user_schedule_dates':
            start, end = _month(policy.get('requested_start_month')), _month(policy.get('requested_end_month'))
            basis = 'requested_schedule'
        elif not policy.get('as_of_date') and not policy.get('selection_basis'):
            start = min(rows)
            end = _add_months(start, (duration or min(3, len(rows))) - 1)
            basis = 'legacy_saved_forecast'

    if not start or not end or start > end:
        return {**empty, 'notes': ['기획 시작·종료월을 확정해야 해당 기간의 ML 전망을 표시할 수 있습니다.']}
    requested_count = _index(end) - _index(start) + 1
    selected = [rows[month] for month in sorted(rows) if start <= month <= end]
    if not selected:
        return {**empty, 'notes': ['기획 기간이 저장 ML 전망 범위와 겹치지 않습니다.']}
    if any(_index(right['month']) - _index(left['month']) != 1 for left, right in zip(selected, selected[1:])):
        return {**empty, 'notes': ['기획 기간 중 누락된 예측 월이 있어 합계·목표를 계산하지 않습니다.']}
    complete = len(selected) == requested_count
    notes = []
    if not complete:
        notes.append(f'기획 {start}~{end} 중 저장 전망이 있는 {len(selected)}개월만 표시합니다.')
    if basis == 'legacy_saved_forecast':
        notes.append('구형 보고서의 저장 전망 구간입니다. 실제 사업 일정과 일치하는지 확인하세요.')
    validated = policy.get('validated_recursive_horizon_months', 3)
    latest = _month(ml.get('latest_observed_month'))
    if latest and _index(selected[-1]['month']) - _index(latest) > validated:
        notes.append('3개월 초과 예측 거리는 재귀 검증 범위 밖의 탐색 전망입니다.')
    return {'rows': selected, 'period': f"{selected[0]['month']}~{selected[-1]['month']}",
            'complete': complete, 'notes': notes, 'selection_basis': basis,
            'requested_period': f'{start}~{end}'}
