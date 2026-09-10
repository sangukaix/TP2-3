"""User-approved proposal defaults. Forecasts and audit results remain immutable."""
from copy import deepcopy
import re

CASE_URL = 'https://clik.nanet.go.kr/minutes/viewer.do?DOCID=CLIKC3524169218564260&collection=minutes'


def target_basis(report):
    strategy = (report.get('strategies') or [{}])[0]
    decision = report.get('planning_decision') or {}
    ids = list(decision.get('recommended_case_ids') or [])
    for candidate in decision.get('design_candidates') or []:
        if candidate.get('candidate_id') == decision.get('selected_candidate_id'):
            ids.extend(candidate.get('case_source_ids') or [])
    refund = any(word in str(strategy.get('title', '')) + str(strategy.get('solution', '')) for word in ('반값', '환급'))
    gangjin = refund and ('gangjin' in str(ids) or '강진' in str(strategy))
    return {
        'kind': 'planning_assumption', 'visitor_target_pct': 20.0 if gangjin else 5.0, 'spending_target_pct': 20.0 if gangjin else 5.0,
        'case_title': '강진 반값여행과 지역축제 운영 실적' if gangjin else '선정 사례의 운영 방식과 시범 목표',
        'source_url': CASE_URL if gangjin else '',
        'period': '2024년 1~10월 누적 / 전년 비교 발표' if gangjin else '',
        'observed_visitors': 2480000 if gangjin else None,
        'reported_growth_pct': 25.0 if gangjin else None,
        'prior_visitors_backcalculated': 1984000 if gangjin else None,
        'explanation': (
            '강진군의회 2024-11-20 시정연설: 10월 말 관광객 약 248만 명, 전년 대비 25% 증가. '
            '전년 규모 역산: 248만÷1.25≈198.4만 명, 차이≈49.6만 명. 역산값은 별도 관측 원자료가 아니다. '
            '반값여행과 축제의 동시기 실적이며 사업 단독 효과·ML 대비 증가율은 아니다. '
            f"{report.get('region_name') or '선택 지역'}은 최종월 방문 +20%를 도전 목표로 제안한다(25% × 80%). 80%는 전면 적용 대신 단계 운영을 고려한 계획 가정이며 인구 보정·통계 추정 계수가 아니다. "
            '기본 소비 목표는 월별 소비/방문 비율을 추가 방문 수에 적용한 계획 가정이며 강진 소비 실적으로 계산한 값이 아니다.'
            if gangjin else
            '선정 사례의 운영 방식을 참고하여 최종월 방문·소비 +5%를 초기 계획 목표로 제안한다. '
            '이 비율은 사례의 검증된 효과율이나 ML 결과가 아니라 조정 가능한 기획 가정이다.'
        ),
    }


def prepare_idea_report(report):
    """One copy for web and exports; explicit user targets always win."""
    from .report_projection import execution_target
    from .proposal_evidence import build_reference_estimate
    result = deepcopy(report)
    from .case_recommendation import link_decision
    result['planning_decision'] = link_decision(result.get('planning_decision') or {},
        [s for s in result.get('evidence_sources') or [] if s.get('source_type') == 'benchmark_case'])
    result['summary'] = re.sub(r'\s*·?\s*코드 점검에서 실행·근거 보완 항목이 확인되었습니다\.?', '', str(result.get('summary') or ''))
    basis = target_basis(result)
    if execution_target(result) is None:
        result['execution_scenario'] = {key: basis[key] for key in ('visitor_target_pct', 'spending_target_pct')}
    actual = execution_target(result)
    if actual != (basis['visitor_target_pct'], basis['spending_target_pct']):
        basis['explanation'] += f' 현재 조정된 목표는 방문 +{actual[0]:g}%, 소비 +{actual[1]:g}%이다.'
    if actual[0] != actual[1]:
        basis['explanation'] += ' 현재 소비 목표는 방문 연동식 대신 별도로 지정한 소비 목표율을 적용한다.'
    else:
        basis['explanation'] += ' 방문 수가 0보다 큰 월은 ML 소비액÷ML 방문 수를 추가 방문 수에 곱한다. 같은 월의 두 증가율은 같으며, 이 비율은 실제 1인당 소비액이 아니다.'
    basis['visitor_target_pct'], basis['spending_target_pct'] = actual
    result['target_proposal_basis'] = basis
    for strategy in result.get('strategies') or []:
        strategy['expected_effect'] = f'계획 목표: 최종월 ML 기준 전망 대비 방문 +{actual[0]:g}%, 소비 +{actual[1]:g}%. 월별 목표는 단계 적용하며 상품권 재사용률 등 운영 실적은 별도 집계합니다.'
        kpi = str(strategy.get('kpi') or '')
        if '⑥성공/중단 기준:' in kpi:
            strategy['kpi'] = kpi.split('⑥성공/중단 기준:', 1)[0].rstrip() + ' ⑥성과 판단: 위 계획 목표와 실제 집계 결과를 비교합니다.'
    if not result.get('reference_estimate'):
        result['reference_estimate'] = build_reference_estimate(result)
        estimate = result['reference_estimate']
        brief = result.get('planning_brief') or {}
        if brief.get('input_profile') == 'guided_v1' and brief.get('budget_max_krw'):
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
            current = prepare_idea_report(report)['execution_scenario']
            v = float(visitor[1]) if visitor else current['visitor_target_pct']
            s = float(spending[1]) if spending else current['spending_target_pct']
            if not 0 <= v <= 20 or not 0 <= s <= 30:
                return reply('방문 목표는 0~20%, 소비 목표는 0~30%로 조정할 수 있습니다.')
            return reply(f'방문 +{v:g}%, 소비 +{s:g}%로 계획 목표를 조정합니다. ML 예측값은 유지됩니다.',
                         {'execution_scenario': {'visitor_target_pct': v, 'spending_target_pct': s}})
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
    original = estimate['total_krw']
    amounts = [int(row['amount'] * total / original) for row in estimate['items']]
    amounts[-1] += total - sum(amounts)
    for row, amount in zip(estimate['items'], amounts):
        row.update(amount=amount, basis='요청 총액 내 항목별 배분 가정 · 운영량 별도 조정')
    for key in ('quantity', 'unit_krw', 'redemption_count', 'qualifying_spend_krw'):
        estimate.pop(key, None)
    estimate.update(total_krw=total, reserve_krw=amounts[-1], subtotal_krw=sum(amounts[:-1]), within_hard_budget=True)
