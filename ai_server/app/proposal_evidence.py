"""Document-only, auditable planning estimates and complete provenance.

Never modifies a saved report, its forecasts, or its quality verdict. Unit prices
are planning allowances, not supplier quotes; operational volume is not causal uplift.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
import math
import re
from typing import Any

from .report_projection import select_report_forecast

REFUND_SOURCE = {
    'source_id': 'estimate:gangjin-refund-rules:20260905',
    'source_type': 'budget_reference',
    'title': '강진군 반값여행 공식 신청·정산 조건',
    'source_url': 'https://www.gangjintour.com/advance/advance_req.html',
    'summary': '일반 관광객 여행비 50% 상품권 환급. 개인 최대 10만원·팀 최대 20만원. 원주 효과나 공급업체 단가의 근거는 아님.',
    'accessed_at': '2026-09-05',
}

METRIC_LABELS = {
    'visitors': '방문자 수', 'spending_krw': '관광소비액',
    'stay_minutes': '평균 체류시간', 'lodging_nights': '평균 숙박일수',
    'lodging_rate_pct': '숙박방문자 비율', 'lodging_searches': '숙박 목적지 검색량',
    'navigation_searches': '내비게이션 검색량',
}


def saved_budget_view(report: dict[str, Any]) -> dict[str, Any]:
    """Render the saved narrative, never substitute a document-only pilot budget.

    A declared total is a transcription, not verification of its arithmetic.
    Operators and amounts in the original formula remain unchanged.
    """
    strategy = (report.get('strategies') or [{}])[0]
    raw = str(strategy.get('budget') or '').strip()
    matches = re.findall(r'총\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:억\s*원|만\s*원|원))', raw)
    totals = list(dict.fromkeys(matches))
    total_label = '총 ' + totals[0] if len(totals) == 1 else '총액 미확정'
    parts = [part.strip() for part in re.split(r'[\n;；]+', raw) if part.strip()]
    # Bounded row count without throwing away text or interpreting '+' as a separator.
    if len(parts) > 6:
        parts = parts[:5] + ['; '.join(parts[5:])]
    return {
        'status': 'saved_report_budget', 'total_label': total_label,
        'rows': [[f'산정 내역 {index}', part, '본문 기준'] for index, part in enumerate(parts, 1)]
                or [['예산 산정', '저장 기획안에 예산 산식이 없습니다.', '미정']],
        'original_text': raw, 'sources': [],
        'note': '저장 기획안의 예산 산정 내용을 그대로 표시합니다. 확정 견적이 아니며 계약 전 수량·단가·세금과 합계를 확인합니다.',
    }


def build_reference_estimate(report: dict[str, Any]) -> dict[str, Any]:
    """Explicit quantity×allowance pilot estimate, scaled to the selected period.

    This is an editable proposal, not a recommendation backed by measured uplift.
    A hard budget is respected by reducing funded volume; an infeasible fixed-cost
    floor is reported, never hidden. No LLM or network request is needed.
    """
    strategy = (report.get('strategies') or [{}])[0]
    text = ' '.join(str(strategy.get(k) or '') for k in ('title', 'solution'))
    refund = '환급' in text or '반값' in text
    rows = select_report_forecast(report).get('rows') or []
    duration_match = re.search(r'(\d+)\s*개월', str(strategy.get('timeframe') or ''))
    months = len(rows) or (int(duration_match[1]) if duration_match else 3)
    months = max(1, min(6, months))
    from .proposal_presentation_v4 import _scenario_for_display
    scenario, _ = _scenario_for_display(report)
    additional = (sum(scenario['target_visitors']) - sum(scenario['baseline_visitors'])
                  if scenario and scenario.get('has_target') else 0)
    # Participation is a disclosed planning allocation, not estimated causal conversion.
    quantity = math.ceil(max(0, additional) * .01) if additional > 0 else round(1000 * months / 3)
    scale_basis = (f'사업기간 추가 방문 목표 {additional:,.0f}명 × 시범 담당 비중 1% → {quantity:,}건(올림). '
                   '1%는 직접 운영할 참여량 배분 가정이며 전환율 예측이 아닙니다.' if additional > 0 else
                   '기준 참여량 1,000건 × 운영 개월/3의 초기 운영 가정.')
    unit = 50_000 if refund else 10_000
    staff_days = max(20 * months, math.ceil(quantity / 25))  # 25 cases per staff day: planning assumption
    fixed = staff_days * 150_000 + 8_000_000 + 5_000_000 + 3_000_000
    brief = report.get('planning_brief') or {}
    hard_limit = brief.get('budget_max_krw') if brief.get('budget_hard_limit') else None
    if hard_limit is not None:
        quantity = min(quantity, max(0, math.floor((float(hard_limit) / 1.1 - fixed) / unit)))
    benefits = quantity * unit
    subtotal = benefits + fixed
    reserve = math.ceil(subtotal * .10)
    total = subtotal + reserve
    return {
        'version': 'reference-estimate-v2', 'scale_basis': scale_basis, 'additional_visitors_target': additional, 'pilot_share_pct': 1, 'status': 'planning_assumption_not_quote',
        'months': months, 'refund': refund, 'quantity': quantity, 'unit_krw': unit,
        'redemption_target_pct': 80, 'redemption_count': math.floor(quantity * .8),
        'qualifying_spend_krw': quantity * 100_000 if refund else None,
        'subtotal_krw': subtotal, 'reserve_krw': reserve, 'total_krw': total,
        'within_hard_budget': hard_limit is None or total <= float(hard_limit),
        'items': [
            {'name': '여행비 환급 지원' if refund else '참여 혜택', 'basis': f'{quantity:,}건 × {unit:,}원', 'amount': benefits},
            {'name': '현장 운영·정산', 'basis': f'max(월 20인일 × {months}, {quantity:,}건 ÷ 25건/인일 올림) = {staff_days}인일 × 150,000원', 'amount': staff_days * 150_000},
            {'name': '신청·증빙 시스템', 'basis': '기존 시스템 설정 1식 × 800만원', 'amount': 8_000_000},
            {'name': '홍보·참여처 안내', 'basis': '콘텐츠·안내물 1식 × 500만원', 'amount': 5_000_000},
            {'name': '성과 집계·검토', 'basis': '자료 정리·평가 1식 × 300만원', 'amount': 3_000_000},
            {'name': '예비비', 'basis': f'직접비 {subtotal / 10000:,.0f}만원 × 10%', 'amount': reserve},
        ],
        'sources': [deepcopy(REFUND_SOURCE)] if refund else [],
        'assumptions': [
            '전 항목은 기획용 가정 단가이며 확정 견적·공식 표준단가가 아닙니다.',
            '인력 15만원/인일은 현장 용역 예산 가정입니다. 근로계약 임금 산정값이 아닙니다.',
            '시스템은 기존 신청·정산 수단의 설정·운영 범위입니다. 신규 앱·키오스크 구축비는 제외합니다.',
            '용역비는 세금 포함 예산 한도로 가정합니다. 환급금 과세·수수료·계약조건은 착수 전 확인합니다.',
            '지원 건수·평균 지원액·80% 후속 사용 목표는 운영 제안이며 관측값 또는 ML 산출값이 아닙니다.',
        ],
    }


def enrich_source_names(report: dict[str, Any], env_values: dict[str, Any]) -> dict[str, Any]:
    """Resolve existing source IDs in MySQL, read-only; never drop an unresolved ID."""
    result = deepcopy(report)
    ids = list(dict.fromkeys(str(s.get('source_id')) for s in result.get('evidence_sources', [])
                            if str(s.get('source_id') or '').startswith(('datalab:', 'bigdata:', 'team-bigdata:'))))
    if not ids:
        return result
    from .nationwide_context_store import _connect
    try:
        with _connect(env_values) as connection, connection.cursor() as cursor:
            cursor.execute('SELECT source_id, file_name, source_name FROM data_source WHERE source_id IN (' + ','.join(['%s'] * len(ids)) + ')', ids)
            resolved = {row['source_id']: row for row in cursor.fetchall()}
        for source in result.get('evidence_sources', []):
            row = resolved.get(source.get('source_id'))
            if row:
                source['source_file_name'] = row['file_name']
        result['document_source_resolution'] = 'mysql_source_id_lookup'
    except Exception as exc:
        result['document_source_resolution'] = f'unavailable:{type(exc).__name__}'
    return result


def source_display_name(source: dict[str, Any]) -> str:
    filename = str(source.get('source_file_name') or '').replace('\\', '/')
    # Keep the real file name; stripping only filesystem directories is not truncation.
    if filename:
        parts = PurePosixPath(filename).parts
        # Foreign-visitor/card archives need the measurement family as well.
        if any(part in ('이동통신', '신용카드', '내비게이션') for part in parts):
            return '/'.join(parts)
        return '/'.join(parts[-2:]) if len(parts) > 1 else parts[0]
    title = str(source.get('title') or source.get('source_id') or '출처명 미기록')
    if title in {'한국관광 데이터랩 공식 다운로드', '한국관광 데이터랩 전국 빅데이터 다운로드'}:
        return f"{title} [원파일명 미기록; {source.get('source_id')}]"
    return title


def complete_source_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep one readable bibliography row per parent source without hiding PDF pages."""
    grouped: dict[str, dict[str, Any]] = {}
    for source in report.get('evidence_sources') or []:
        if not isinstance(source, dict):
            continue
        key = str(source.get('source_id') or (str(source.get('title')) + str(source.get('source_url'))))
        if key not in grouped:
            grouped[key] = deepcopy(source)
            continue
        target = grouped[key]
        # The same parent PDF can have several selected pages. A bibliography is not
        # the evidence store, but must tell reviewers that it has multiple passages.
        pages = [value for value in (target.get('page_references'), source.get('page_references')) if value]
        if pages:
            target['page_references'] = ', '.join(dict.fromkeys(map(str, pages)))
        chunks = set(target.get('chunk_ids') or [])
        if target.get('chunk_id'):
            chunks.add(str(target['chunk_id']))
        if source.get('chunk_id'):
            chunks.add(str(source['chunk_id']))
        if chunks:
            target['chunk_ids'] = sorted(chunks)
            target['source_chunk_count'] = len(chunks)
    return list(grouped.values())
