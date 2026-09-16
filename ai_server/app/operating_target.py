"""Reproducible operating scenarios, not a fitted treatment-effect model.

Capacity is a proposal. Local demand sets a bounded operating scale, never a
claim about the number of contracted facilities. Reviewed case rates can replace
explicit assumptions. Forecasts, source facts and the caller's report are immutable.
"""
from __future__ import annotations

import math
import re
from copy import deepcopy

from .case_recommendation import operation_family
from .report_projection import select_report_forecast
from .operating_schedule import operating_schedule

VERSION = 'operating-capacity-v4-linked-cost'
MIN_PARTICIPATION_RATE = .75
# days/month, sessions/day, people/session, allowance/slot, existing-visitor extra spend
# These are disclosed planning settings, not official standards or trained parameters.
PROFILES = {
    'night_time_experience': ('야간 문화·체험', '운영 거점', 8, 2, 40, 10000, 12000),
    'spend_conversion': ('지역 소비·환급', '참여 점포 묶음', 20, 1, 20, 50000, 20000),
    'stay_conversion': ('체류 상품', '숙박·체험 묶음', 8, 1, 20, 30000, 30000),
    'return_visit': ('재방문 프로그램', '참여 거점', 12, 1, 25, 10000, 15000),
    'reservation_conversion': ('예약 연계 프로그램', '예약 거점', 12, 2, 20, 10000, 15000),
    'access_and_mobility': ('관광 이동 연계', '운행 노선', 8, 2, 30, 20000, 10000),
    'experience_product': ('지역 체험 상품', '체험 거점', 8, 2, 25, 15000, 20000),
    'other_operation': ('지역 관광 프로그램', '운영 거점', 8, 1, 25, 15000, 10000),
}


def selected_sources(report):
    decision = report.get('planning_decision') or {}
    selected = next((c for c in decision.get('design_candidates') or []
                     if c.get('candidate_id') == decision.get('selected_candidate_id')), {})
    ids = selected.get('case_source_ids') or decision.get('recommended_case_ids') or []
    return [s for s in report.get('evidence_sources') or []
            if s.get('source_id') in ids and s.get('source_url')]


def finite(value, default=None):
    if isinstance(value, bool): return default
    try: number = float(value)
    except (TypeError, ValueError): return default
    return number if math.isfinite(number) and number >= 0 else default


def reviewed_rate(sources, metric, fallback):
    """Only human-reviewed, scoped program rates enter arithmetic automatically.

    A citywide YoY rate, a press-search summary, or an LLM-produced field alone
    cannot certify a conversion or an additional-visitor fraction.
    """
    for source in sources:
        for item in source.get('operating_statistics') or []:
            value = finite(item.get('value'))
            if (item.get('review_status') == 'reviewed' and item.get('metric') == metric
                    and item.get('unit') == 'percent' and item.get('scope') == 'program_participants'
                    and value is not None and value <= 100 and item.get('period') and item.get('quote')):
                return value / 100, {'kind': 'reviewed_case', 'source_id': source['source_id'],
                                    'source_url': source['source_url'], **deepcopy(item)}
    return fallback, {'kind': 'planning_assumption', 'metric': metric, 'value': fallback * 100,
                      'unit': 'percent', 'reason': '사업 규모를 검토하기 위한 공통 계획 가정'}


def participation_target(sources):
    """Use comparable reviewed attendance counts; preserve observed rates below the goal floor."""
    for source in sources:
        for item in source.get('operating_statistics') or []:
            capacity=finite(item.get('capacity_count'))
            participants=finite(item.get('participant_count'))
            if not (item.get('metric')=='utilization_rate' and item.get('review_status')=='reviewed'
                    and item.get('scope')=='program_participants' and item.get('unit')=='percent'
                    and item.get('period') and item.get('quote') and source.get('source_url')
                    and capacity and participants is not None and participants<=capacity
                    and (item.get('case_region') or source.get('case_region'))
                    and (item.get('program_name') or source.get('intervention'))):
                continue
            observed=participants/capacity
            stated=finite(item.get('value'))
            if stated is None or abs(stated-observed*100)>.51:continue
            target=max(MIN_PARTICIPATION_RATE,observed)
            region=item.get('case_region') or source['case_region']
            program=item.get('program_name') or source['intervention']
            citation=(f"{region} {program} ({item['period']}): "
                      f"정원 {capacity:,.0f}명 중 {participants:,.0f}명 참여, "
                      f"{participants:,.0f} ÷ {capacity:,.0f} × 100 = {observed*100:.2f}%.")
            decision=(f' 이 비율을 참고해 참여 목표 {target*100:.2f}%를 적용합니다.' if observed>=MIN_PARTICIPATION_RATE
                      else ' 사례 실적은 그대로 두고, 우리 참여 목표는 최소 기준 75%로 설정합니다.')
            return target, {**deepcopy(item), 'kind':'reviewed_case', 'source_id':source.get('source_id',''),
                            'source_url':source['source_url'], 'case_region':region, 'program_name':program,
                            'capacity_count':capacity, 'participant_count':participants,
                            'observed_value':observed*100, 'target_value':target*100,
                            'floor_applied':observed<MIN_PARTICIPATION_RATE,
                            'reason':citation+decision}
    return MIN_PARTICIPATION_RATE, {'kind':'planning_policy','metric':'utilization_rate',
            'value':75.0,'target_value':75.0,'unit':'percent','floor_applied':True,
            'reason':'참여 목표 75%는 공통 최소 운영 목표입니다. 사례 참여율을 인용한 값이 아닙니다.'}


def refund_settings(report):
    """Read explicitly labelled *proposal* terms, never benchmark case rates."""
    decision = report.get('planning_decision') or {}
    selected = next((c for c in decision.get('design_candidates') or []
                     if c.get('candidate_id') == decision.get('selected_candidate_id')), {})
    formula = str(selected.get('budget_formula') or (decision.get('strategy_brief') or {}).get('budget_formula') or '')
    rates = re.findall(r'(?:환급률\s*[:：]?\s*|(?:인정\s*)?지출액\s*[×*]\s*)(\d+(?:\.\d+)?)\s*%', formula)
    caps = re.findall(r'건별\s*(?:환급\s*)?상한\s*[:：]?\s*(\d[\d,]*(?:\.\d+)?)\s*(만)?\s*원', formula)
    rate = float(rates[0]) / 100 if len(set(rates)) == 1 and 0 < float(rates[0]) <= 100 else .10
    cap = round(float(caps[0][0].replace(',', '')) * (10000 if caps[0][1] else 1)) if len(set(caps)) == 1 else 50000
    if not 0 < cap <= 1000000: cap = 50000
    return rate, cap


def build_operating_target(report):
    selection = select_report_forecast(report)
    rows = selection['rows']
    if not rows or not selection['complete'] or any(r['visitors'] <= 0 or r['spending_krw'] <= 0 for r in rows):
        return {'version': VERSION, 'status': 'no_comparable_forecast', 'scenarios': [],
                'explanation': '지역 전망과 운영 조건을 연결해 참여 규모를 제안합니다.'}
    strategy = (report.get('strategies') or [{}])[0]
    family = operation_family(strategy)
    label, site_label, days, sessions, seats, allowance, extra_spend = PROFILES.get(family, PROFILES['other_operation'])
    schedule = operating_schedule(rows, strategy)
    months = len(schedule['active_months'])
    visitors = sum(r['visitors'] for r in rows)
    spending = sum(r['spending_krw'] for r in rows)
    mean_visitors = visitors / len(rows)
    # Smooth sublinear scaling prevents metropolitan visitor totals from implying
    # hundreds of contracted venues. This is a planning rule, not carrying capacity.
    sites = min(12, max(1, math.ceil(math.sqrt(mean_visitors / 100000))))
    capacity = sites * days * months * sessions * seats
    sources = selected_sources(report)
    uptake, uptake_basis = participation_target(sources)
    new_share, new_basis = reviewed_rate(sources, 'additional_visitor_share', .30)
    weighted_v = sum(r['visitors'] * w for r, w in zip(rows, schedule['monthly_weights']))
    weighted_s = sum(r['spending_krw'] * w for r, w in zip(rows, schedule['monthly_weights']))
    proxy = spending / visitors
    # Existing participants' additional purchases are separate from new visitors'
    # destination-wide spending proxy, so the two groups are not counted twice.
    unit_extra = min(extra_spend, proxy * .5)
    # One purchase scenario supplies both the expected payout and the spending
    # calculation. The per-claim ceiling is not an expected payment to everyone.
    refund = family == 'spend_conversion'
    refund_rate, refund_cap = refund_settings(report)
    if refund: allowance = refund_cap
    purchase = round(proxy)
    payout = min(allowance, round(purchase * refund_rate)) if refund else allowance
    if refund:
        proxy_for_program = purchase
    else:
        proxy_for_program = proxy
    brief = report.get('planning_brief') or {}
    budget = finite(brief.get('budget_max_krw'))
    # Refund processing is a shared desk, not one full-time crew per shop.
    # This is an explicit proposed staffing arrangement, not observed capacity.
    def teams(count): return math.ceil(count / 4) if refund else count
    staff_teams = teams(sites)
    staff_days = staff_teams * days * months
    fixed = staff_days * 150000 + 16000000
    if budget is not None:
        while sites > 1 and (fixed + days * months * sessions * seats * payout) * 1.1 > budget:
            sites -= 1
            staff_teams = teams(sites)
            staff_days = staff_teams * days * months
            fixed = staff_days * 150000 + 16000000
        capacity = sites * days * months * sessions * seats
    def cost(participants):
        direct = fixed + participants * payout
        return direct + math.ceil(direct / 10)
    funded = capacity
    if budget is not None:
        funded = min(funded, max(0, math.floor((budget / 1.1 - fixed) / max(1, payout))))
        while funded and cost(funded) > budget: funded -= 1
    # Keep all output scenarios inside the existing API target bounds. The
    # proposal discloses this cap rather than silently clipping its percentages.
    high_u, high_n = min(1, uptake + .15), min(1, new_share + .15)
    per_v = high_u * high_n
    per_s = high_u * (high_n * proxy_for_program + (1 - high_n) * unit_extra)
    limit = min(weighted_v * .20 / per_v if per_v else funded,
                weighted_s * .30 / per_s if per_s else funded)
    funded = min(funded, max(0, math.floor(limit)))
    scenarios = []
    for name, u, n in [('보수', max(MIN_PARTICIPATION_RATE, uptake - .15), max(0, new_share - .15)),
                       ('기준', uptake, new_share), ('확대', high_u, high_n)]:
        participants = math.floor(funded * u)
        additional = math.floor(participants * n)
        additional_spend = round(additional * proxy_for_program + (participants - additional) * unit_extra)
        # A planning purchase total is not all incremental to the destination.
        gross_purchases = round(participants * proxy_for_program)
        scenarios.append({'label': name, 'utilization_pct': u * 100, 'additional_visitor_share_pct': n * 100,
                          'participants': participants, 'additional_visitors': additional,
                          'additional_spending_krw': additional_spend,
                          'participant_purchases_krw': gross_purchases,
                          'expected_support_krw': participants * payout,
                          'expected_budget_krw': cost(participants),
                          'visitor_growth_pct': additional / visitors * 100,
                          'spending_growth_pct': additional_spend / spending * 100,
                          # Equivalent final-month rates preserve the shared monthly ramp.
                          'visitor_target_pct': additional / weighted_v * 100,
                          'spending_target_pct': additional_spend / weighted_s * 100})
    central = scenarios[1]
    items = [
        {'name': '여행비 환급 지원' if refund else '프로그램 운영·참여 지원',
         'basis': (f"참여 목표 {central['participants']:,}건 × min(계획 결제 {purchase:,}원 × {refund_rate*100:g}%, 건별 상한 {allowance:,}원) = 건당 {payout:,}원" if refund
                   else f"참여 목표 {central['participants']:,}명 × 계획 지원단가 {payout:,}원"),
         'amount': central['expected_support_krw']},
        {'name': '현장 운영·정산', 'basis': f'{staff_teams}개 운영팀 × 월 {days}일 × {months}개월 × 150,000원'
         + (f' (점포 묶음 {sites}개, 최대 4개당 공동 정산팀 1개)' if refund else ''), 'amount': staff_days * 150000},
        {'name': '신청·운영 시스템', 'basis': '기존 수단 설정 1식 × 가정 단가 8,000,000원', 'amount': 8000000},
        {'name': '홍보·참여처 안내', 'basis': '안내 콘텐츠 1식 × 가정 단가 5,000,000원', 'amount': 5000000},
        {'name': '성과 집계·검토', 'basis': '실적 정리 1식 × 가정 단가 3,000,000원', 'amount': 3000000},
    ]
    subtotal = sum(i['amount'] for i in items)
    reserve = math.ceil(subtotal / 10)
    items.append({'name': '예비비', 'basis': f'직접비 {subtotal:,}원 × 10%', 'amount': reserve})
    minimum_budget = cost(0)
    below_floor = budget is not None and budget < minimum_budget
    if below_floor:
        for item in items:
            item.update(amount=0, basis='운영안 미편성 · 기본 운영비보다 입력 예산이 작음')
        subtotal = reserve = 0
        for scenario in scenarios:
            scenario['expected_budget_krw'] = 0
    formula = f'{sites}개 × 월 {days}일 × {months}개월 × 하루 {sessions}회 × 회당 {seats}명 = {capacity:,}명분'
    explanation = (f'{label}: {formula}. 편성 한도 {funded:,}명분에 이용률 {uptake*100:g}%를 적용해 '
                   f'{central["participants"]:,}명 참여, 추가 방문 비중 {new_share*100:g}%로 '
                   f'{central["additional_visitors"]:,}명 유치를 제안합니다. '
                   f'기간 합계 ML 전망 대비 방문 +{central["visitor_growth_pct"]:.2f}%, '
                   f'소비 +{central["spending_growth_pct"]:.2f}%의 계획 시나리오입니다. '
                   + uptake_basis['reason'])
    plan = {'version': VERSION, 'status': 'budget_below_operating_floor' if below_floor else 'proposed',
            'minimum_operating_budget_krw': minimum_budget,
            'family': family, 'program_label': label, 'site_label': site_label, 'months': months,
            **schedule,
            'forecast_period': selection['period'], 'baseline_visitors': visitors, 'baseline_spending_krw': spending,
            'mean_monthly_visitors': mean_visitors, 'sites': sites, 'days_per_month': days,
            'sessions_per_day': sessions, 'capacity_per_session': seats, 'capacity': capacity, 'funded_capacity': funded,
            'scale_rule': '운영 거점 = ceil(√(월평균 ML 방문 전망 ÷ 100,000)), 최소 1·최대 12개',
            'capacity_formula': formula, 'scale_kind': 'planning_rule_not_population_model',
            'spending_per_visit_proxy_krw': proxy, 'program_purchase_krw': proxy_for_program,
            'existing_participant_extra_spend_krw': unit_extra,
            'spending_formula': f'추가 방문 × 계획 결제 {proxy_for_program:,.0f}원 + 기존 방문 참여 × 추가 구매 {unit_extra:,.0f}원',
            'purchase_basis': '계획 결제액은 3개월 ML 소비 합계 ÷ ML 방문 합계를 참고한 기획값입니다. 실제 객단가가 아닙니다.',
            'rate_basis': [uptake_basis, new_basis], 'scenarios': scenarios, 'central': central,
            'participation_basis': uptake_basis['reason'], 'minimum_participation_pct':75.0,
            'case_sources': [{'source_id': s['source_id'], 'title': s.get('title') or s.get('source_title'),
                              'source_url': s['source_url'], 'operating_model': s.get('operating_model', ''),
                              'observed_result': s.get('observed_result', '')} for s in sources],
            'explanation': explanation,
            'disclosure': '보수·기준·확대는 이용률과 추가 방문 비중을 ±15%p 바꾼 계획 범위이며 통계적 오차범위가 아닙니다. 참여 목표는 75~100% 안에서 적용합니다. 거점 수는 운영 제안이며 소비/방문 비율은 실측 객단가가 아닙니다.',
            'budget_cap_krw': budget, 'capacity_reduced': funded < capacity}
    if below_floor:
        plan['explanation'] = (f'입력 예산 {budget:,.0f}원으로는 기본 운영비 가정 {minimum_budget:,}원을 충족하지 못해 '
                               '현재 운영량·목표·견적을 편성하지 않았습니다. 운영 범위를 조정하는 참고안입니다.')
    active = schedule['active_months']
    plan['operating_period'] = f'{active[0][:4]}-{active[0][4:]}~{active[-1][:4]}-{active[-1][4:]}'
    plan['schedule_note'] = f"실제 운영 산정: {plan['operating_period']}, {months}개월. 준비 기간에는 추가 방문·소비 목표를 배분하지 않습니다."
    plan['explanation'] += ' ' + plan['schedule_note']
    plan['estimate'] = {'version': VERSION, 'status': 'planning_assumption_not_quote',
                        'scale_basis': formula + f" → 참여 목표 {central['participants']:,}건의 예상 집행액. 모든 단가는 기획 가정.",
                        'months': months, 'refund': refund, 'quantity': central['participants'], 'unit_krw': payout,
                        'capacity_quantity': funded, 'per_claim_cap_krw': allowance if refund else None,
                        'refund_rate_pct': refund_rate * 100 if refund else None,
                        'redemption_target_pct': uptake * 100, 'redemption_count': central['participants'],
                        'purchase_per_participant_krw': proxy_for_program,
                        'qualifying_spend_krw': central['participant_purchases_krw'] if refund else None,
                        'subtotal_krw': subtotal, 'reserve_krw': reserve,
                        'total_krw': subtotal + reserve, 'within_hard_budget': budget is None or subtotal + reserve <= budget,
                        'full_participation_budget_krw': cost(funded) if not below_floor else 0,
                        'participant_purchases_krw': central['participant_purchases_krw'],
                        'additional_spending_krw': central['additional_spending_krw'],
                        'scenario_note': (f"참여자 결제 {central['participant_purchases_krw']:,}원 중 추가 소비 목표 {central['additional_spending_krw']:,}원. "
                                          '견적은 같은 참여 목표의 사업비이며, 결제액 전체를 신규 소비나 사업 수익으로 계산하지 않습니다.'),
                        'items': items, 'sources': [], 'assumptions': [
                            '기획용 예상 견적이며 실제 액수와 다를 수 있습니다.',
                            '100% 참여 참고예산도 같은 계획 결제액을 사용한 참고값이며 최대 지급 책임액이 아닙니다.',
                            plan['purchase_basis'],
                            f'기존 방문 참여자의 추가 구매액은 유형별 기준 {extra_spend:,}원과 ML 소비/방문 비율의 50% 중 작은 값입니다.',
                        ] + ([f'환급률 {refund_rate*100:g}%, 건별 상한 {allowance:,}원 및 점포 묶음 최대 4개당 정산팀 1개는 계획 설정입니다. 지급 총액은 편성 예산 내에서 운영합니다.'] if refund else [])}
    return plan
