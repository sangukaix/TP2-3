"""LLM의 해석 전에 고정하는 비교·전망 사실표입니다. 사업 효과를 새로 추정하지 않습니다."""

from __future__ import annotations

import math
import re
from typing import Any


def build_decision_facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    comparison = snapshot.get('nationwide_comparison') or {}
    comparisons = []
    if comparison.get('available'):
        for peer in comparison.get('peer_regions') or []:
            for key, value in peer.items():
                if '_gap_' not in key or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    continue
                comparisons.append({'peer_region': peer.get('region_name'), 'metric': key, 'gap': value,
                                    'direction': 'higher' if value > 0 else 'lower' if value < 0 else 'equal',
                                    'period': comparison.get('period')})
    ml = snapshot.get('ml_analysis') or {}
    # 기존 ML 집계 결과만 선택합니다. 방문/소비 합계와 숙박/체류 평균의 계산법을 LLM이 바꾸지 않게 합니다.
    forecasts = [{key: signal.get(key) for key in ('metric', 'period', 'aggregation', 'forecast_value',
                 'previous_year_same_months_value', 'change_percent', 'reliability', 'model_reliability', 'source_id')}
                 for signal in ml.get('signals') or [] if signal.get('kind') == 'forecast_signal']
    return {'comparison_convention': '선택 지역 - 비교 지역', 'peer_comparisons': comparisons,
            'comparison_metric_definitions': comparison.get('metric_definitions') or {},
            'comparison_source_ids': [row.get('source_id') for row in comparison.get('source_records', [])],
            'forecast_windows': forecasts, 'intervention_effect': 'not_estimated',
            'causal_limit': 'ML 자연추세·타지역 관측 변화로 사업 시행의 추가 소비/방문 증가를 확정할 수 없습니다.'}


def comparison_direction_issues(snapshot: dict, draft: dict) -> list[dict]:
    """기간 비교에서 실제 확인된 %p 격차를 반대로 서술하는 좁은 오류만 확정적으로 검출합니다."""
    facts = build_decision_facts(snapshot)
    def texts(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from texts(item)
        elif isinstance(value, list):
            for item in value:
                yield from texts(item)
    issues = []
    for fact in facts['peer_comparisons']:
        if fact['metric'] != 'overnight_ratio_gap_pct_point' or not fact['peer_region'] or not fact['gap']:
            continue
        name = str(fact['peer_region']).split()[-1]
        short = name.removesuffix('구') if name.endswith('구') else name
        pattern = re.escape(short) + r'(?:구)?\s*보다\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*p\s*(낮|높)'
        for text in texts(draft):
            if '숙박' not in text or '가정' in text:
                continue
            for match in re.finditer(pattern, text, re.IGNORECASE):
                direction = 'higher' if match[2] == '높' else 'lower'
                if abs(float(match[1]) - abs(fact['gap'])) <= 0.005 and direction != fact['direction']:
                    issues.append({'severity': 'critical', 'field': 'evidence.comparison_direction',
                        'problem': f"{name} 대비 숙박비율 격차의 높음/낮음 방향이 검증된 수치와 반대입니다.",
                        'revision_instruction': f"{fact['period']} 선택 지역-비교 지역={fact['gap']}%p. 양수는 높음, 음수는 낮음으로 고치세요."})
    return issues


def past_execution_month_issues(snapshot: dict, draft: dict) -> list[dict]:
    """관측/성과 비교의 과거 월은 허용하되, 신규 집행 단계가 과거 월에 배치된 경우만 검출합니다."""
    as_of = str(((snapshot.get('ml_analysis') or {}).get('horizon_policy') or {}).get('as_of_date') or '')
    if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', as_of):
        return []
    current_month = as_of[:7].replace('-', '')
    for strategy in draft.get('strategies') or []:
        for step in strategy.get('implementation_steps') or []:
            schedule = str(step.get('schedule') or '')
            for year, month in re.findall(r'(?<!\d)(20\d{2})[-./년]\s*(1[0-2]|0?[1-9])(?:월|\b)', schedule):
                if year + month.zfill(2) < current_month:
                    return [{'severity': 'major', 'field': 'implementation_steps.schedule',
                             'problem': f'신규 집행 단계에 기획 기준일({as_of})보다 과거인 월이 포함됐습니다.',
                             'revision_instruction': '과거 월은 관측/기준선 설명에만 두고 준비부터 최종 평가까지 실제 집행 가능한 미래 일정으로 재배치하세요.'}]
    return []
