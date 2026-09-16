"""User-approved proposal defaults. Forecasts and audit results remain immutable."""
from copy import deepcopy
import re

CASE_URL = 'https://clik.nanet.go.kr/minutes/viewer.do?DOCID=CLIKC3524169218564260&collection=minutes'


def target_basis(report):
    from .operating_target import build_operating_target
    plan = build_operating_target(report)
    central = plan.get('central') or {}
    return {'kind': 'operating_capacity', 'capacity_plan': plan,
            'case_title': '선정 사례의 운영 방식과 지역 운영 규모', 'observed_visitors': None,
            'source_url': '', 'reported_growth_pct': None,
            'visitor_target_pct': central.get('visitor_target_pct'),
            'spending_target_pct': central.get('spending_target_pct'),
            'explanation': plan['explanation']}


def _automatic_target(report):
    """Migrate identifiable old defaults, but preserve explicit/ambiguous edits."""
    from .report_projection import execution_target
    current = execution_target(report)
    brief = report.get('planning_brief') or {}
    if brief.get('visitor_target_pct') is not None or (report.get('execution_scenario') or {}).get('target_origin') == 'user':
        return False
    basis = report.get('target_proposal_basis') or {}
    if current is None: return True
    if basis.get('target_mode') == 'user': return False
    if basis.get('kind') == 'operating_capacity':
        return current == (basis.get('visitor_target_pct'), basis.get('spending_target_pct'))
    explanation = basis.get('explanation', '')
    return (basis.get('kind') == 'planning_assumption' and '현재 조정된 목표' not in explanation
            and current in ((5.0, 5.0), (20.0, 20.0)))


def align_business_period(report):
    brief = report.get('planning_brief') or {}
    if brief.get('input_profile') != 'guided_v2' or not brief.get('start_date') or not brief.get('end_date'):
        return
    start, end = str(brief['start_date'])[:7], str(brief['end_date'])[:7]
    months = (int(end[:4]) - int(start[:4])) * 12 + int(end[5:]) - int(start[5:]) + 1
    audit = report.setdefault('planning_decision', {}).setdefault('period_alignment', [])
    for index, strategy in enumerate(report.get('strategies') or []):
        expected = f'{start} ~ {end}, {months}개월'
        if strategy.get('timeframe') != expected:
            audit.append({'field': f'strategies[{index}].timeframe', 'original': strategy.get('timeframe'), 'updated': expected})
            strategy['timeframe'] = expected
        for step in strategy.get('implementation_steps') or []:
            original = str(step.get('schedule') or '')
            updated = re.sub(r'20\d{2}-(?:0[1-9]|1[0-2])(?!\d)', lambda match: min(end, max(start, match[0])), original)
            updated = re.sub(r'(20\d{2}-\d{2})\s*[~∼]\s*\1', r'\1', updated)
            if updated != original:
                audit.append({'field': f'strategies[{index}].step[{step.get("step")}].schedule', 'original': original, 'updated': updated})
                step['schedule'] = updated


def prepare_idea_report(report):
    """One copy for web and exports; explicit user targets always win."""
    from .report_projection import execution_target
    from .proposal_evidence import build_reference_estimate
    result = deepcopy(report)
    from .case_recommendation import link_decision
    result['planning_decision'] = link_decision(result.get('planning_decision') or {},
        [s for s in result.get('evidence_sources') or [] if s.get('source_type') == 'benchmark_case'])
    result['summary'] = re.sub(r'\s*·?\s*코드 점검에서 실행·근거 보완 항목이 확인되었습니다\.?', '', str(result.get('summary') or ''))
    align_business_period(result)
    automatic = _automatic_target(result)
    basis = target_basis(result)
    plan = basis['capacity_plan']
    if automatic:
        result['execution_scenario'] = ({**{key: basis[key] for key in ('visitor_target_pct', 'spending_target_pct')},
                                        'target_origin': 'operating_capacity'} if plan.get('central') else None)
    actual = execution_target(result)
    basis['target_mode'] = 'automatic' if automatic else 'user'
    if not automatic and actual:
        basis['explanation'] = (f'현재 최종월 목표는 사용자 지정 방문 +{actual[0]:.2f}%, 소비 +{actual[1]:.2f}%입니다. '
                                '운영 규모로 계산한 시나리오는 별도 참고안입니다. ' + plan['explanation'])
    if actual: basis['visitor_target_pct'], basis['spending_target_pct'] = actual
    result['target_proposal_basis'] = basis
    for strategy in result.get('strategies') or []:
        if actual:
            strategy['expected_effect'] = f'계획 목표: 최종월 ML 전망 대비 방문 +{actual[0]:.2f}%, 소비 +{actual[1]:.2f}%. 운영 규모와 참여 가정으로 산정하며 실제 성과는 별도 집계합니다.'
        kpi = str(strategy.get('kpi') or '')
        from .measurement_alignment import align_night_growth
        aligned_kpi = align_night_growth(kpi)
        if aligned_kpi != kpi:
            result.setdefault('planning_decision', {}).setdefault('measurement_alignment', []).append(
                {'original': kpi, 'updated': aligned_kpi, 'reason': '야간 방문 비중과 전년 대비 증가율의 분모 구분'})
            strategy['kpi'] = kpi = aligned_kpi
        if '⑥성공/중단 기준:' in kpi:
            strategy['kpi'] = kpi.split('⑥성공/중단 기준:', 1)[0].rstrip() + ' ⑥성과 판단: 위 계획 목표와 실제 집계 결과를 비교합니다.'
    previous_estimate = result.get('reference_estimate') or {}
    estimate_is_manual = previous_estimate.get('user_adjusted') or '사용자 참고 총액' in previous_estimate.get('scale_basis', '')
    if plan.get('estimate') and not estimate_is_manual:
        result['reference_estimate'] = deepcopy(plan['estimate'])
    elif not result.get('reference_estimate'):
        result['reference_estimate'] = build_reference_estimate(result)
        estimate = result['reference_estimate']
        brief = result.get('planning_brief') or {}
        if brief.get('input_profile') in ('guided_v1', 'guided_v2') and brief.get('budget_max_krw'):
            scale_estimate(estimate, brief['budget_max_krw'])
        if not estimate['within_hard_budget']:
            cap = int((result.get('planning_brief') or {})['budget_max_krw'])
            scale_estimate(estimate, cap)
    return result


def available_candidates(report):
    """Only actual source-linked designs, never a fabricated fixed count."""
    return [row for row in (report.get('planning_decision') or {}).get('design_candidates') or []
            if row.get('candidate_id') and row.get('title') and row.get('case_source_ids')]


def bounded_chat_reply(report, question):
    """Handle explicit numeric edits and out-of-scope construction without an LLM."""
    candidates = available_candidates(report)
    titles = [row['title'] for row in candidates]
    def reply(answer, patch=None):
        return {'answer': answer, 'mode': 'revise' if patch else 'explain',
                'key_points': titles if not patch else ['미리보기에 반영한 뒤 저장하세요.'],
                'sources': [], 'report_patch': patch, 'generation_mode': 'local',
                'execution': {'model': '입력 조건 처리', 'web_search_used': False}}
    if re.search(r'63\s*빌딩|고층|초고층|공원.{0,12}(짓|건설|조성)|빌딩.{0,12}(짓|건설)|아파트', question):
        return reply(f'현재 기획안에서는 근거가 연결된 관광사업 아이디어 {len(titles)}개만 비교할 수 있습니다. 건물·공원 신축은 제공 범위에 포함되지 않습니다. 아래 후보와 현재 사업의 목표·견적·운영 내용을 조정할 수 있습니다.')
    if re.search(r'수정.{0,8}(가능|항목)|변경.{0,8}(가능|항목)|어떤.{0,8}(바꿀|수정)', question):
        return reply('목표 KPI 증가율, 예상 견적, 소개·홍보 문구, 참여 범위와 실행 단계를 조정할 수 있습니다. 관측값·ML 전망·공식 사례 실적은 변경하지 않습니다.')
    if re.search(r'바꿔|변경|수정|설정', question):
        visitor = re.search(r'방문(?:자)?(?:\s*목표(?:율)?)?\s*([0-9]+(?:\.[0-9]+)?)\s*%', question)
        spending = re.search(r'(?:관광)?소비(?:\s*목표(?:율)?)?\s*([0-9]+(?:\.[0-9]+)?)\s*%', question)
        if visitor or spending:
            current = prepare_idea_report(report)['execution_scenario'] or {}
            if (not visitor and 'visitor_target_pct' not in current) or (not spending and 'spending_target_pct' not in current):
                return reply('현재 자동 목표가 없어 한 지표만 바꾸면 다른 목표를 임의로 정하게 됩니다. 방문·소비 목표를 함께 알려주시면 반영합니다.')
            v = float(visitor[1]) if visitor else current['visitor_target_pct']
            s = float(spending[1]) if spending else current['spending_target_pct']
            if not 0 <= v <= 20 or not 0 <= s <= 30:
                return reply('방문 목표는 0~20%, 소비 목표는 0~30%로 조정할 수 있습니다.')
            return reply(f'방문 +{v:g}%, 소비 +{s:g}%로 계획 목표를 조정합니다. ML 예측값은 유지됩니다.',
                         {'execution_scenario': {'visitor_target_pct': v, 'spending_target_pct': s, 'target_origin': 'user'}})
        budget = re.search(r'(?:견적|예산)(?:\s*총액)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(억|만)?\s*원', question)
        if budget:
            total = round(float(budget[1].replace(',', '')) * {'억': 100000000, '만': 10000, None: 1}[budget[2]])
            if not 1 <= total <= 10**12:
                return reply('예상 견적은 1원 이상 1조 원 이하로 입력해 주세요.')
            hard = report.get('planning_brief') or {}
            if hard.get('budget_hard_limit') and total > (hard.get('budget_max_krw') or 0):
                return reply('설정한 예산 상한을 넘습니다. 상한 안의 예상 견적으로 조정해 주세요.')
            estimate = prepare_idea_report(report)['reference_estimate']
            scale_estimate(estimate, total)
            return reply(f'예상 견적을 총 {total:,}원으로 배분했습니다. 실제 계약 금액과 다를 수 있습니다.', {'reference_estimate': estimate})
    return None


def scale_estimate(estimate, total):
    estimate['user_adjusted'] = True
    original = estimate['total_krw']
    amounts = [int(row['amount'] * total / original) if original else int(total / len(estimate['items'])) for row in estimate['items']]
    amounts[-1] += total - sum(amounts)
    for row, amount in zip(estimate['items'], amounts):
        row.update(amount=amount, basis='요청 총액 내 항목별 배분 가정 · 운영량 별도 조정')
    for key in ('quantity', 'unit_krw', 'redemption_count', 'qualifying_spend_krw',
                'full_participation_budget_krw', 'participant_purchases_krw',
                'additional_spending_krw', 'scenario_note', 'capacity_quantity',
                'per_claim_cap_krw', 'refund_rate_pct', 'purchase_per_participant_krw'):
        estimate.pop(key, None)
    estimate['assumptions'] = ['사용자가 지정한 총액의 항목별 배분 예시이며 운영 시나리오와 별도로 조정한 금액입니다.']
    estimate['scale_basis'] = f'사용자 참고 총액 {total:,}원을 기존 항목 비중으로 재배분. 수량·단가는 별도 조정하는 배분 예시입니다.'
    estimate.update(total_krw=total, reserve_krw=amounts[-1], subtotal_krw=sum(amounts[:-1]), within_hard_budget=True)
