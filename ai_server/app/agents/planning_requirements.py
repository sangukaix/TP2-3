"""실행 기획의 작성 계약과 자료 보완 목록. 사실·금액·승인 점수는 생성하지 않는다."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

QUALITY_CONTRACT_VERSION = 'execution-evidence-v1'
CANDIDATE_TYPES = ('spend_conversion', 'stay_conversion', 'reservation_conversion',
                   'return_visit', 'access_and_mobility', 'experience_product')


# 기획안 본문의 "2026-09"과 "2026년 9월"을 동일한 월로 다룹니다. 날짜가
# 없는 "1주차"는 최종 기간과 비교할 수 없으므로 여기서는 그대로 허용합니다.
_YEAR_MONTH_PATTERN = re.compile(r'(?<!\d)(20\d{2})[-./년]\s*(1[0-2]|0?[1-9])(?:월|\b)')
_BUDGET_ONLY_TITLE_PATTERN = re.compile(r'예산\s*(?:편성|구조|확보|계획|편성안|체계)(?:\s*(?:구축|마련|수립))?(?:\s*모델\s*도입)?\s*$', re.I)
_FIXED_TOTAL_BUDGET_PATTERN = re.compile(
    r'총\s*(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:억원|억\s*원|원)', re.I,
)
_PROVISIONAL_BUDGET_LABEL_PATTERN = re.compile(
    r'기획\s*가정|미확정|잠정|참고\s*견적|비교\s*견적|예산\s*상한|추정\s*견적', re.I,
)
_REGION_WIDE_REFUND_BUDGET_PATTERN = re.compile(
    r'(?:외지인\s*)?방문객\s*수.{0,80}(?:×|\*|곱하기).{0,80}평균\s*지출(?:액)?.{0,80}(?:×|\*|곱하기).{0,80}환급률',
    re.I | re.S,
)
_OBSERVATION_CAUSAL_FIT_PATTERN = re.compile(
    r'(?=.*(?:방문자\s*수|관광소비\s*총액|검색량|언급량|숙박\s*비율|평균\s*숙박일수))'
    r'(?=.*(?:바탕으로|근거로).*(?:적합|효과적|높일\s*수|증가시킬\s*수))',
    re.I | re.S,
)

# OpenAI 장문 지시와 Qwen/Gemma 전용 지시가 서로 다른 품질 기준을 갖지 않게 공유한다.
EXECUTION_EVIDENCE_RULES = """
실행·근거 계약:
관측(기준월/단위/source_id) → 문제의 원인 가설 → 서로 다른 후보 → 선택 이유 → 실행/비용/검증을 연결한다.
검색량은 관심 지표이지 잠재 방문객 수·실제 수요·결제 전환 증명이 아니다. 높다는 판단에도 비교 기준이 필요하다.
타지역의 전년 대비 증가율은 그 사업의 인과효과가 아니다. 사업 참여 실적과 지역 전체 상품권 결제를 구분한다.
사례의 quantitative_result_approved=false이면 운영 방식만 참고한다. 과거 생성안의 수치를 복사하지 말고 성과 수치 인용을 보류한다.
각 design_candidate.evidence_source_ids에는 선택 지역 지표 또는 검증된 전국 비교 출처를 포함한다.
case_source_ids는 운영 방식을 뒷받침한다. 사례 ID만으로 선택 지역의 적합성을 입증하지 않는다.
local_fit에는 실제 지역 지표/기간과 해결할 행동을, selection_reason에는 다른 후보보다 나은 점/불리한 점을 쓴다.
공식 사업 자격·지역상품권 환급 허용·교통 할인 협약·지급 시점은 별도 확인 대상이다. 미확인 '즉시 환급'을 확정하지 않는다.
사업 제목은 선택 지역에서 실행할 내용으로 쓴다. 다른 지자체 사업명을 제목째 복사하지 않는다.
`예산 편성`, `예산 구조`, `예산 확보`만으로 사업 제목이나 후보를 만들지 않는다. 이는 실행 사업이 아니라 비용 준비 방식이다.
선택 지역에서 실제로 누가 어떤 참여 조건으로 무엇을 이용·예약·결제·인증하는지 제목과 mechanism에 나타나야 한다.
특정 명소·상권·시설 이름은 입력 근거 source_id에 실제로 확인된 경우에만 쓴다. 확인되지 않으면 `예: 특정 명소 연계`처럼 만들지 말고 권역·콘텐츠 유형으로 표현한다.
budget/budget_formula는 항목별 수량×단가와 합산 방식이다. 항목 이름+공식 단가 확인 필요만 나열하지 않는다.
단가 미확인은 오류를 숨길 이유가 아니다. 누구에게 어떤 견적을 언제 받을지와 검증 가능한 변수식을 쓴다.
참고 견적을 제시하면 모든 미확정 수량·단가를 '기획 가정/미확정 견적'으로 표시하고 근거 있는 금액과 구분한다.
확정 사용자 예산 상한을 넘거나 가정을 공식 단가라고 쓰면 안 된다. 예산의 합계·부가세·예비비·중복 지급도 점검한다.
환급 지원액=각 적격 신청의 min(증빙 인정 지출액×가정 환급률, 건별 상한)을 합산한 값이다.
지역 전체 방문객 수×평균 지출액×환급률은 시범 예산이 아니다. 시범 승인 신청 건수와 건별 상한으로 공공비용의 최대 범위를 계산한다.
정액 지급일 때만 적격 신청 건수×건별 지급 단가로 단순화한다. 신청 단위는 개인/팀 중 하나로 고정한다.
이것은 공공비용이며 지역 순증 소비액이 아니다. 신청 건수·환급 인원·재사용 건수·고유 방문자를 섞지 않는다.
expected_effect는 ML 자연추세, 운영 목표 가정, 사후 평가할 추가 효과를 구분한다.
참여자×참여율×소비 같은 식은 단위와 중복 범위를 설명한다. 이미 참여한 사람 수에 참여율을 다시 곱하지 않는다.
사업 전에는 순증 효과를 확정할 수 없다. 비교집단 자료가 없으면 측정 설계/필요 자료를 제시하며 증가율을 꾸미지 않는다.
발전 가능성의 크기는 타지역 성과율을 복사하지 않고, `시범 대상 수×완료율×건별 측정값` 같은 가정 시나리오와 미운영 비교집단 차이로 제시한다.
KPI/measurement_plan은 ①지표·분자/분모(금액이면 합계 정의) ②기준기간 ③측정 주기 ④원자료/수집 담당
⑤동일 범위의 비교집단 ⑥성공·중단 기준의 근거 또는 착수 전 확정 절차를 포함한다.
전년 대비 증가율=(이번 기간 값-전년 같은 기간 값)/전년 같은 기간 값×100이다. 전년 값이 0이면 산정 불가다.
전년 대비 변화는 인과효과가 아니다. 순차 도입 등 비교 설계는 계절·선택 편향·동일 분모 조건을 검토한다.
20% 증가·5% 재방문 같은 숫자를 근거 없이 성공/중단 기준으로 정하지 않는다. 가정 목표이면 명시하고 예산/기준선으로 검증한다.
각 실행 단계는 담당 역할+실제 작업+입력 또는 확인 조건+완료 산출물을 담는다. 시스템 '구축'만으로 끝내지 않는다.
timeframe이 `YYYY-MM ~ YYYY-MM, N개월`이면 모든 implementation_steps 일정은 그 시작·종료 월 안에 있어야 한다.
자료/협약 미확보 시 지급 보류·규모 축소 등 대안을 넣고, 새 앱·키오스크 없이 가능한 운영 방식도 비교한다.
검수자는 효과가 확정되지 않았다는 이유만으로 확정 증가율을 요구하지 않는다. 산식·측정 설계 부실을 구체적으로 지적한다.
검수자는 공식 단가 미확인과 산식 누락을 구분한다. 명시된 임시 견적/변수식과 확보 절차는 허용하되 확정 견적으로 승인하지 않는다.
selection_status=needs_evidence이면 무엇을 확인해야 하는지 prerequisites/selection_reason에 쓴다. ready로 강제 변경하지 않는다.
이 계약의 비용·측정 필드는 180자 제한보다 완전성이 우선한다. 반복은 줄이고 항목별 짧은 문장으로 쓴다.
"""


def issue(field: str, problem: str, instruction: str, severity: str = 'major') -> dict[str, str]:
    return {'severity': severity, 'field': field, 'problem': problem, 'revision_instruction': instruction}


def has_cost_formula(text: str) -> bool:
    # '공식 단가에 따라 확정' 한 문구로 검사 통과하던 구멍을 막는다.
    # 실제 응답이 '수량×단가 산식: 항목 1억, 항목 2억'으로 검사를 우회했다.
    # 형식 이름은 식 자체가 아니므로 표제만 제외한 본문에서 확인한다.
    text = re.sub(r'수량\s*(?:×|\*|곱하기)\s*단가\s*(?:산식|계산식)?\s*[:：]', '', text)
    return bool(re.search(r'\S\s*(?:×|\*|곱하기)\s*\S', text) or re.search(r'수량.+단가.+곱', text))


def uses_region_wide_refund_budget(text: str) -> bool:
    """지역 전체 관측 규모를 시범 지원 예산으로 곱한 산식을 찾습니다."""
    return bool(_REGION_WIDE_REFUND_BUDGET_PATTERN.search(str(text or '')))


def overclaims_local_fit(text: str) -> bool:
    """관측 규모만으로 특정 사업의 적합성·효과를 결론 낸 문장을 찾습니다."""
    return bool(_OBSERVATION_CAUSAL_FIT_PATTERN.search(str(text or '')))


def is_budget_only_title(text: str) -> bool:
    """예산 준비를 실제 관광사업처럼 제안하는 제목을 구분합니다."""
    return bool(_BUDGET_ONLY_TITLE_PATTERN.search(str(text or '').strip()))


def is_budget_only_mechanism(text: str) -> bool:
    """방문객 행동 없이 재원·편성만 설명하는 후보를 구분합니다."""
    value = str(text or '')
    return bool(
        re.search(r'예산|편성|재원|사업비', value)
        and not re.search(r'이용|예약|결제|구매|체험|환급|혜택|숙박|재방문|이동|관람|신청|참여', value)
    )


def _region_aliases(region_name: str) -> set[str]:
    """전체 행정명과 마지막 시·군·구 이름을 복사 검사에만 사용합니다."""
    value = str(region_name or '').strip()
    if not value:
        return set()
    aliases = {value}
    tail = re.split(r'\s+', value)[-1]
    if re.search(r'(?:시|군|구)$', tail) and len(tail) >= 3:
        aliases.update({tail, tail[:-1]})
    return {alias for alias in aliases if len(alias) >= 2}


def _copied_case_region_aliases(pack: dict[str, Any], text: str) -> set[str]:
    value = str(text or '')
    selected = _region_aliases(str(pack.get('region_name') or ''))
    copied: set[str] = set()
    for case in pack.get('benchmark_cases') or []:
        for alias in _region_aliases(str(case.get('case_region') or '')) - selected:
            if alias in value:
                copied.add(alias)
    return copied


def has_unlabeled_fixed_budget_total(text: str) -> bool:
    """출처·가정 표시 없이 총액만 제시하는 임의 예산을 막습니다.

    타 지역의 공식 예산은 참고할 수 있지만, 선택 지역의 확정 예산처럼 복사하면 안 됩니다.
    따라서 수량×단가 식과 별개로 기획 가정/참고 견적 표기가 필요합니다.
    """
    value = str(text or '')
    return bool(_FIXED_TOTAL_BUDGET_PATTERN.search(value) and not _PROVISIONAL_BUDGET_LABEL_PATTERN.search(value))


def _month_keys(text: str) -> list[str]:
    return [year + month.zfill(2) for year, month in _YEAR_MONTH_PATTERN.findall(str(text or ''))]


def timeframe_schedule_issues(strategy: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    """선언한 사업기간 바깥의 집행 단계를 결정적으로 잡습니다."""
    bounds = _month_keys(str(strategy.get('timeframe') or ''))
    if len(bounds) < 2:
        return []
    start_month, end_month = bounds[0], bounds[-1]
    if start_month > end_month:
        return [issue(prefix + '.timeframe', '사업 기간의 시작월이 종료월보다 늦습니다.',
                      'timeframe을 YYYY-MM ~ YYYY-MM, N개월 형식의 실제 집행 기간으로 고치세요.', 'critical')]
    for index, step in enumerate(strategy.get('implementation_steps') or [], 1):
        outside = [month for month in _month_keys(str(step.get('schedule') or ''))
                   if month < start_month or month > end_month]
        if outside:
            return [issue(
                prefix + f'.implementation_steps[{index}].schedule',
                f'선언한 사업 기간({start_month[:4]}-{start_month[4:]}~{end_month[:4]}-{end_month[4:]}) 밖의 집행 월이 있습니다.',
                'timeframe을 실제 준비~평가 종료월까지 늘리거나, 모든 단계 일정을 선언 기간 안으로 재배치하세요.',
                'critical',
            )]
    return []


def measurement_missing(text: str) -> list[str]:
    requirements = {
        '기준기간': r'기준(?:월|기간|선)|전년\s*(?:동기|같은|동월)|운영\s*전',
        '확인 주기': r'매주|주별|주간|월별|매월|매일|일별|분기별|매\s*분기|종료\s*후',
        '원자료·수집방법': r'원자료|수집\s*방법|원장|기록|로그|거래내역|정산(?:자료|대장)|설문|집계표',
        '비교 대상': r'비교|대조|순차\s*도입',
        '분자·분모 또는 금액 합계 정의': r'분자.+분모|분모.+분자|취소.+(?:제외|차감)|순결제\s*(?:액|합계)',
    }
    return [name for name, pattern in requirements.items() if not re.search(pattern, text, re.S)]


_SAFE_ESTIMATE_FORMULA = (
    '기획 가정/미확정 참고 견적: 운영 콘텐츠 수×콘텐츠별 비교견적 + 운영일수×일일 운영·안전 견적 + '
    '참여업체 수×업체 준비비 견적 + 측정 원장 1식×구축 견적. 사업 담당자가 착수 전 수량을 정하고 '
    '회계 담당자가 같은 조건의 비교견적 2건 이상으로 단가·부가세·총액을 확정한다.'
)
_SAFE_MEASUREMENT_PLAN = (
    '유효 참여완료율은 분자=취소·중복을 제외한 완료 ID 수, 분모=승인 참여 ID 수로 계산한다. '
    '운영 전 4주를 기준기간으로 두고 운영 중 매주 예약·참여·취소·결제 원장을 사업 담당자가 집계한다. '
    '같은 콘텐츠의 순차 도입 운영일과 미운영일을 동일 분모로 비교하며, 전후 차이를 사업 인과효과로 확정하지 않는다. '
    '성공·중단 기준은 기준선과 집계 가능성을 확인한 뒤 착수 전에 확정한다.'
)


def _safe_measurement_plan(candidate_type: str) -> str:
    definitions = {
        'spend_conversion': '환급 후 재사용률은 분자=환급 뒤 선택 지역 내 적격 재결제액 합계, 분모=지급한 환급액 합계로 계산한다.',
        'stay_conversion': '숙박 전환율은 분자=숙박 증빙까지 완료한 고유 참여 ID 수, 분모=적격 참여 고유 ID 수로 계산한다.',
        'reservation_conversion': '예약 완료율은 분자=취소·중복을 제외한 이용 완료 ID 수, 분모=승인 예약 ID 수로 계산한다.',
        'return_visit': '재이용률은 분자=측정기간 안에 두 번째 이용을 완료한 고유 ID 수, 분모=첫 이용 완료 고유 ID 수로 계산한다.',
        'access_and_mobility': '혜택 이용률은 분자=교통·숙박 혜택을 한 번 이상 사용한 고유 ID 수, 분모=발급한 고유 ID 수로 계산한다.',
        'experience_product': '체험 완료율은 분자=취소·중복을 제외한 체험 완료 ID 수, 분모=승인 참여 ID 수로 계산한다.',
    }
    return (
        definitions.get(candidate_type, _SAFE_MEASUREMENT_PLAN.split(' 운영 전', 1)[0]) + ' '
        '운영 전 4주를 기준기간으로 두고 운영 중 매주 원자료=신청·승인·취소·이용·결제 원장을 사업 담당자가 집계한다. '
        '같은 콘텐츠·기간의 순차 도입 미운영 집단과 동일 분모로 비교한다. 발전 가능 범위는 시범 대상 수×관측 완료율×건별 측정값의 '
        '가정 시나리오로 제시하고 지역 전체 자연증감과 분리한다. 성공·중단 기준은 기준선·표본수 확인 뒤 착수 전에 확정한다.'
    )


_SAFE_LOCAL_FIT = (
    '선택 지역 관측값은 시범 규모와 사전 기준선을 정하는 자료이며 특정 사업의 적합성·효과 증거가 아니다. '
    '연결된 지역 지표는 기준선으로 사용하고, 공식 사례의 운영 장치는 선택 지역의 자격·가맹점·협약을 확인한 뒤 제한된 시범으로 검증한다. '
    '발전 가능성은 사업 원장의 완료·재사용·결제값과 같은 범위의 미운영 비교집단 차이로 추정한다.'
)


def stabilize_candidate_decision(pack: dict[str, Any], transfer: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """기계적으로 안전하게 고칠 수 있는 후보 오류만 서버 계약으로 보정한다.

    출처가 없는 사례·지역·총액은 삭제하거나 미확정 산식으로 바꾸되, 새 사례·성과·예산을
    만들지 않는다. 의미 판단이 필요한 지역 적합성이나 후보 간 차이는 그대로 남겨 검수한다.
    """
    result = deepcopy(transfer)
    corrections: list[dict[str, str]] = []
    known_case_ids = {
        str(row.get('source_id')) for row in pack.get('benchmark_cases') or [] if row.get('source_id')
    }
    known_source_ids = {
        str(row.get('source_id')) for row in pack.get('sources') or [] if row.get('source_id')
    }
    region_name = str(pack.get('region_name') or '선택 지역').strip()
    selected_region_aliases = _region_aliases(region_name)

    def corrected(field: str, reason: str) -> None:
        corrections.append({'field': field, 'reason': reason})

    for key in ('recommended_case_ids',):
        before = list(result.get(key) or [])
        after = [value for value in before if str(value) in known_case_ids]
        if after != before:
            result[key] = after
            corrected(f'planning_decision.{key}', '등록되지 않은 사례 ID를 제거했습니다.')

    assessments = list(result.get('candidate_assessments') or [])
    kept_assessments = [row for row in assessments if str(row.get('case_source_id') or '') in known_case_ids]
    if kept_assessments != assessments:
        result['candidate_assessments'] = kept_assessments
        corrected('planning_decision.candidate_assessments', '등록되지 않은 사례 평가를 제거했습니다.')

    brief = result.get('strategy_brief')
    if isinstance(brief, dict):
        before = list(brief.get('supporting_case_ids') or [])
        after = [value for value in before if str(value) in known_case_ids]
        if after != before:
            brief['supporting_case_ids'] = after
            corrected('planning_decision.strategy_brief.supporting_case_ids', '등록되지 않은 사례 ID를 제거했습니다.')
        if (has_unlabeled_fixed_budget_total(str(brief.get('budget_formula') or ''))
                or uses_region_wide_refund_budget(str(brief.get('budget_formula') or ''))):
            brief['budget_formula'] = _SAFE_ESTIMATE_FORMULA
            corrected('planning_decision.strategy_brief.budget_formula', '지역 전체 규모 또는 출처 없는 총액 대신 시범 수량·비교견적 산식을 적용했습니다.')
        pilot_scope = str(brief.get('pilot_scope') or '').strip()
        if (_copied_case_region_aliases(pack, pilot_scope)
                and not any(alias in pilot_scope for alias in selected_region_aliases)):
            brief['pilot_scope'] = f'{region_name} 내 참여 관광자원·상권 후보 권역 1곳(현장 확인 후 확정)'
            corrected('planning_decision.strategy_brief.pilot_scope', '타지역 운영 범위를 선택 지역의 조건부 시범 범위로 바꿨습니다.')
        target_users = str(brief.get('target_users') or '').strip()
        if (_copied_case_region_aliases(pack, target_users)
                and not any(alias in target_users for alias in selected_region_aliases)):
            brief['target_users'] = f'{region_name} 방문객'
            corrected('planning_decision.strategy_brief.target_users', '타지역 사례의 이용 대상을 선택 지역 방문객으로 바꿨습니다.')

    candidates = list(result.get('design_candidates') or [])
    safe_titles = {
        'spend_conversion': '방문객 이용·결제 연계 시범',
        'stay_conversion': '방문객 체류 연계 시범',
        'reservation_conversion': '관광 콘텐츠 예약·이용 전환 시범',
        'return_visit': '관광객 재방문 연계 시범',
        'access_and_mobility': '관광 이동·접근 연계 시범',
        'experience_product': '관광 체험 운영 시범',
    }
    for index, candidate in enumerate(candidates, 1):
        prefix = f'planning_decision.design_candidates[{index}]'
        copied_title = _copied_case_region_aliases(pack, str(candidate.get('title') or ''))
        budget_only_mechanism = is_budget_only_mechanism(str(candidate.get('mechanism') or ''))
        if not budget_only_mechanism and (
                copied_title or is_budget_only_title(str(candidate.get('title') or ''))):
            candidate['title'] = f"{region_name} {safe_titles.get(candidate.get('candidate_type'), '관광 이용 전환 시범')}"
            reason = ('타지역 사례명을 선택 지역의 조건부 시범 제목으로 바꿨습니다.' if copied_title
                      else '예산 준비 문구를 실제 이용 흐름이 드러나는 조건부 시범 제목으로 바꿨습니다.')
            corrected(prefix + '.title', reason)
        case_ids = list(candidate.get('case_source_ids') or [])
        valid_case_ids = [value for value in case_ids if str(value) in known_case_ids]
        if valid_case_ids != case_ids:
            candidate['case_source_ids'] = valid_case_ids
            corrected(prefix + '.case_source_ids', '등록되지 않은 사례 ID를 제거했습니다.')
        evidence_ids = list(candidate.get('evidence_source_ids') or [])
        valid_evidence_ids = [value for value in evidence_ids if str(value) in known_source_ids]
        if valid_evidence_ids != evidence_ids:
            candidate['evidence_source_ids'] = valid_evidence_ids
            corrected(prefix + '.evidence_source_ids', '등록되지 않은 근거 ID를 제거했습니다.')
        budget = str(candidate.get('budget_formula') or '')
        if not has_cost_formula(budget) or has_unlabeled_fixed_budget_total(budget) or uses_region_wide_refund_budget(budget):
            candidate['budget_formula'] = _SAFE_ESTIMATE_FORMULA
            corrected(prefix + '.budget_formula', '지역 전체 규모를 예산으로 쓰지 않고 시범 수량·비교견적 기반의 미확정 산식으로 교체했습니다.')
        if measurement_missing(str(candidate.get('measurement_plan') or '')):
            candidate['measurement_plan'] = _safe_measurement_plan(str(candidate.get('candidate_type') or ''))
            corrected(prefix + '.measurement_plan', '분자·분모·수집 원장·비교 기준을 서버 측정 계약으로 보완했습니다.')
        elif re.search(r'전국\s*평균', str(candidate.get('measurement_plan') or '')):
            candidate['measurement_plan'] = _safe_measurement_plan(str(candidate.get('candidate_type') or ''))
            corrected(prefix + '.measurement_plan', '출처 없는 전국 평균 비교를 같은 범위의 순차 도입 비교로 교체했습니다.')
        if overclaims_local_fit(str(candidate.get('local_fit') or '')):
            candidate['local_fit'] = _SAFE_LOCAL_FIT
            corrected(prefix + '.local_fit', '관측 규모를 사업 효과로 해석한 문장을 기준선·시범 검증 설명으로 교체했습니다.')
        rule = str(candidate.get('stop_or_scale_rule') or '')
        if (re.search(r'\d+(?:\.\d+)?\s*%', rule) and re.search(r'성공|중단|확대', rule)
                and not re.search(r'가정|잠정|목표안|착수\s*전|산출\s*근거|출처', rule)):
            candidate['stop_or_scale_rule'] = (
                f'기획 가정 목표안: {rule} 기준선·표본수·집계 가능성을 확인한 뒤 사업 담당자가 착수 전에 확정한다.'
            )
            corrected(prefix + '.stop_or_scale_rule', '근거 없는 수치 문턱을 착수 전 확정할 가정 목표안으로 바꿨습니다.')

    candidate_ids = [str(row.get('candidate_id') or '') for row in candidates if row.get('candidate_id')]
    if candidates and str(result.get('selected_candidate_id') or '') not in candidate_ids:
        result['selected_candidate_id'] = candidate_ids[0] if candidate_ids else ''
        corrected('planning_decision.selected_candidate_id', '후보 목록에 존재하는 ID로 복구했습니다.')
    if isinstance(brief, dict):
        selected = next((row for row in candidates if row.get('candidate_id') == result.get('selected_candidate_id')), {})
        copied_working_title = _copied_case_region_aliases(pack, str(brief.get('working_title') or ''))
        if copied_working_title:
            brief['working_title'] = f"{region_name} {safe_titles.get(selected.get('candidate_type'), '관광 이용 전환 시범')}"
            corrected('planning_decision.strategy_brief.working_title', '타지역 사례명을 선택 지역의 조건부 시범 제목으로 바꿨습니다.')
        # 실제 안전 보정이 있었을 때만 선택 요약의 대응 필드를 동기화한다. 단순한
        # 표현 차이만으로 이미 유효한 ready 판단을 서버가 임의로 낮추지 않는다.
        if corrections:
            for brief_key, candidate_key in (('budget_formula', 'budget_formula'), ('stop_or_scale_rule', 'stop_or_scale_rule')):
                if selected.get(candidate_key) and brief.get(brief_key) != selected.get(candidate_key):
                    brief[brief_key] = selected[candidate_key]
                    corrected(f'planning_decision.strategy_brief.{brief_key}', '보정된 선택 후보와 요약을 동기화했습니다.')
    if corrections:
        result['selection_status'] = 'needs_evidence'
        result['automatic_corrections'] = corrections
    return result, corrections


def candidate_delivery_issues(pack: dict[str, Any], transfer: dict[str, Any]) -> list[dict[str, str]]:
    """재조회/재작성으로 고칠 항목만 찾는다. '근거 부족' 상태 자체는 자동 재시도 사유가 아니다."""
    if 'selection_status' not in transfer:
        return []  # 이전 저장 계약과 호환
    candidates = transfer.get('design_candidates') or []
    local_ids = {str(row.get('source_id')) for row in pack.get('sources') or []
                 if row.get('source_type') in {'dataset', 'nationwide_dataset', 'regional_tourism_status'}
                 or str(row.get('source_id', '')).startswith(('dataset:', 'nationwide:', 'regional-status:'))}
    problems = []
    known_cases = {row.get('source_id') for row in pack.get('benchmark_cases') or []}
    brief = transfer.get('strategy_brief') or {}
    if has_unlabeled_fixed_budget_total(str(brief.get('budget_formula') or '')):
        problems.append(issue('planning_decision.strategy_brief.budget_formula.fixed_total',
                              '선택안에 출처·가정 표시 없는 확정 총예산이 제시됐습니다.',
                              '타지역 예산 총액을 복사하지 말고 수량×단가 산식을 쓰세요. 미확정 금액은 기획 가정/참고 견적과 확보 절차를 명시하세요.', 'critical'))
    if uses_region_wide_refund_budget(str(brief.get('budget_formula') or '')):
        problems.append(issue('planning_decision.strategy_brief.budget_formula.population_scope',
                              '지역 전체 방문객·평균 지출을 시범 환급 예산처럼 계산했습니다.',
                              '시범 승인 신청 건수×건별 환급 상한을 사용하고 운영·정산·홍보는 별도 수량×가정 단가로 추정하세요.', 'critical'))
    # Exact copied operating scope is an error; merely citing another city is not.
    selected_region = str(pack.get('region_name') or '').strip()
    selected_aliases = _region_aliases(selected_region)
    pilot_scope = str(brief.get('pilot_scope') or '').strip()
    if (_copied_case_region_aliases(pack, pilot_scope)
            and not any(alias in pilot_scope for alias in selected_aliases)):
        problems.append(issue('planning_decision.strategy_brief.pilot_scope',
                              '타지역 사례의 운영 지역이 선택 지역의 사업 범위로 복사됐습니다.',
                              '원 사례 지역은 출처에 유지하고 선택 지역에서 확인된 권역 또는 조건부 시범 범위를 작성하세요.', 'critical'))
    target_users = str(brief.get('target_users') or '').strip()
    if (_copied_case_region_aliases(pack, target_users)
            and not any(alias in target_users for alias in selected_aliases)):
        problems.append(issue('planning_decision.strategy_brief.target_users',
                              '타지역 사례의 이용 대상이 선택 지역 사업 대상으로 복사됐습니다.',
                              '원 사례 지역은 출처에만 두고 선택 지역 방문객의 참여 조건을 작성하세요.', 'critical'))
    if _copied_case_region_aliases(pack, str(brief.get('working_title') or '')):
        problems.append(issue('planning_decision.strategy_brief.working_title',
                              '선택안 제목에 타지역 사례명이 그대로 남았습니다.',
                              '가져올 운영 장치는 설명에 두고 제목은 선택 지역의 이용 흐름으로 작성하세요.'))
    cited = set(transfer.get('recommended_case_ids') or []) | set(brief.get('supporting_case_ids') or [])
    cited.update(row.get('case_source_id') for row in transfer.get('candidate_assessments') or [] if row.get('case_source_id'))
    for candidate in candidates:
        cited.update(candidate.get('case_source_ids') or [])
    if cited - known_cases:
        problems.append(issue('planning_decision.case_source_ids', '등록되지 않은 공식 사례 ID가 연결됐습니다.',
                              'benchmark_cases의 source_id를 그대로 사용하고 supporting_case_ids까지 함께 수정하세요.', 'critical'))
    if known_cases and not (set(transfer.get('recommended_case_ids') or []) & known_cases):
        problems.append(issue('planning_decision.recommended_case_ids', '선정안에 실제 비교한 공식 사례가 남아 있지 않습니다.',
                              '보유 사례의 운영 장치 중 적용·변경·제외할 내용을 비교하고 해당 source_id를 연결하세요.'))
    kinds = {row.get('candidate_type') for row in candidates if row.get('candidate_type')}
    required_kinds = 2
    if (pack.get('planning_brief') or {}).get('input_profile') == 'guided_v1':
        from ..case_recommendation import allowed_operation, budget_only
        from ..case_mechanism import case_mechanism_family
        available = {case_mechanism_family(row) for row in pack.get('benchmark_cases') or []
                     if not budget_only(row) and allowed_operation(row, pack['planning_brief'])}
        required_kinds = max(1, min(2, len(available)))
    if len(candidates) >= 2 and len(kinds) < required_kinds:
        problems.append(issue('planning_decision.candidate_type', '후보들의 운영 원리가 구분되지 않았습니다.',
                              '이름만 바꾸지 말고 예약 전환·체류 전환·재방문 등 작동 방식이 다른 후보를 비교하세요.'))
    if candidates and transfer.get('selected_candidate_id') not in {row.get('candidate_id') for row in candidates}:
        problems.append(issue('planning_decision.selected_candidate_id', '선택한 후보가 후보 목록에 없습니다.',
                              '검토한 후보의 candidate_id를 그대로 지정하세요.', 'critical'))
    if len(candidates) < required_kinds:
        problems.append(issue('planning_decision.design_candidates', '서로 다른 사업 후보가 두 개 미만입니다.',
                              '보유 공식 사례에서 운영 원리가 다른 후보를 비교하세요. 없으면 필요한 사례의 운영 방식과 자료를 명시하세요.'))
    for index, candidate in enumerate(candidates, 1):
        prefix = f'planning_decision.design_candidates[{index}]'
        if candidate.get('candidate_type') not in CANDIDATE_TYPES:
            problems.append(issue(prefix + '.candidate_type', '허용된 사업 후보 유형이 아닙니다.',
                                  '사례 비교용 분류를 복사하지 말고 실제 운영 원리에 맞는 ' + ', '.join(CANDIDATE_TYPES) + ' 중 하나를 사용하세요.'))
        if known_cases and not (set(candidate.get('case_source_ids') or []) & known_cases):
            problems.append(issue(prefix + '.case_source_ids', '후보의 운영 방식을 뒷받침하는 공식 사례가 연결되지 않았습니다.',
                                  '유사 사례에서 가져올 운영 장치와 선택 지역에서 바꿀 점을 쓰고 실제 case source_id를 연결하세요.'))
        rule = str(candidate.get('stop_or_scale_rule') or '')
        if (re.search(r'\d+(?:\.\d+)?\s*%', rule) and re.search(r'성공|중단|확대', rule)
                and not re.search(r'가정|잠정|목표안|착수\s*전|산출\s*근거|출처', rule)):
            problems.append(issue(prefix + '.stop_or_scale_rule', '후보의 성공·중단 수치에 근거나 가정 표시가 없습니다.',
                                  '근거 없는 문턱값을 확정하지 말고 출처·산출 방법 또는 가정 목표와 착수 전 확정 절차를 쓰세요.'))
        if is_budget_only_title(str(candidate.get('title') or '')):
            problems.append(issue(prefix + '.title', '후보 제목이 예산 편성만 설명하고 실제 관광사업을 설명하지 않습니다.',
                                  '예산은 산식에만 두고, 방문객의 이용·예약·결제·체험 중 무엇을 어떻게 바꾸는 사업인지 제목과 mechanism을 고치세요.'))
        elif _copied_case_region_aliases(pack, str(candidate.get('title') or '')):
            problems.append(issue(prefix + '.title', '후보 제목에 타지역 사례명이 그대로 남았습니다.',
                                  '사례명은 비교 근거에 두고 제목은 선택 지역에서 실행할 이용 흐름으로 작성하세요.'))
        if is_budget_only_mechanism(str(candidate.get('mechanism') or '')):
            problems.append(issue(prefix + '.mechanism', '후보의 작동 방식이 방문객 행동 없이 예산 편성만 설명합니다.',
                                  '누가 무엇을 이용·예약·결제·체험하고 운영자가 무엇을 확인하는지 작성하세요.'))
        if local_ids and not (set(candidate.get('evidence_source_ids') or []) & local_ids):
            problems.append(issue(prefix + '.local_fit', '후보의 지역 적합성에 선택 지역/전국 비교 지표가 연결되지 않았습니다.',
                                  'get_region_metrics/compare_regions의 실제 지표·기간으로 local_fit을 보완하고 해당 source_id를 evidence_source_ids에 연결하세요. 사례 효과를 지역 근거로 대신 쓰지 마세요.'))
        if not has_cost_formula(str(candidate.get('budget_formula') or '')):
            problems.append(issue(prefix + '.budget_formula', '후보 예산이 비용 항목 나열에 그칩니다.',
                                  '항목별 수량×단가 산식으로 쓰세요. 미확정 단가는 변수와 견적 확보 담당·시점을 적고 금액을 꾸미지 마세요.'))
        if has_unlabeled_fixed_budget_total(str(candidate.get('budget_formula') or '')):
            problems.append(issue(prefix + '.budget_formula.fixed_total',
                                  '후보에 출처·가정 표시 없는 확정 총예산이 제시됐습니다.',
                                  '수량×단가가 있어도 타지역 총액을 선택 지역 확정 예산으로 복사하지 마세요. 기획 가정/참고 견적과 확인 절차를 명시하세요.', 'critical'))
        if uses_region_wide_refund_budget(str(candidate.get('budget_formula') or '')):
            problems.append(issue(prefix + '.budget_formula.population_scope',
                                  '지역 전체 방문객·평균 지출을 시범 공공비용으로 계산했습니다.',
                                  '시범 승인 신청 건수×건별 상한으로 최대 지원액을 계산하고, 모든 수량·단가는 기획 가정으로 표시하세요.', 'critical'))
        if overclaims_local_fit(str(candidate.get('local_fit') or '')):
            problems.append(issue(prefix + '.local_fit.interpretation',
                                  '지역 관측 규모만으로 이 사업이 적합하거나 효과적이라고 해석했습니다.',
                                  '관측값은 기준선·시범 규모에만 사용하고, 사례에서 가져올 장치와 선택 지역에서 바꿀 조건 및 발전 가능성 측정식을 쓰세요.'))
        missing = measurement_missing(str(candidate.get('measurement_plan') or ''))
        if missing:
            problems.append(issue(prefix + '.measurement_plan', '후보 측정 설계 누락: ' + ', '.join(missing),
                                  '지표 정의, 기준기간, 주기, 원자료, 같은 범위의 비교집단을 짧게 명시하세요. 없는 자료는 수집 담당·확보 시점을 쓰세요.'))
        elif re.search(r'전국\s*평균', str(candidate.get('measurement_plan') or '')):
            problems.append(issue(prefix + '.measurement_plan.comparison_source',
                                  '출처와 동일 분모가 확인되지 않은 전국 평균을 비교집단으로 사용했습니다.',
                                  '같은 콘텐츠·기간의 순차 도입 미운영 집단이나 비교 가능한 지역 원자료와 수집 담당을 명시하세요.'))
    return problems


def execution_delivery_issues(strategy: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    problems = []
    if is_budget_only_title(str(strategy.get('title') or '')):
        problems.append(issue(prefix + '.title', '기획안 제목이 예산 편성만 설명하고 실제 관광사업을 설명하지 않습니다.',
                              '예산은 실행을 위한 수단으로만 두고, 대상·참여 조건·이용 또는 결제 흐름이 드러나는 사업 제목으로 고치세요.'))
    problems.extend(timeframe_schedule_issues(strategy, prefix))
    budget = str(strategy.get('budget') or '')
    if has_unlabeled_fixed_budget_total(budget):
        problems.append(issue(prefix + '.budget.fixed_total', '선택 지역의 근거·가정 표시 없이 확정 총예산처럼 보이는 금액이 제시됐습니다.',
                              '타 지역 예산 총액을 복사하지 마세요. 항목별 수량×단가 식을 쓰고, 금액이 필요하면 모든 변수에 기획 가정/미확정 참고 견적과 확인 절차를 표시하세요.', 'critical'))
    if uses_region_wide_refund_budget(budget):
        problems.append(issue(prefix + '.budget.population_scope',
                              '지역 전체 방문객·평균 지출을 시범 사업비로 계산했습니다.',
                              '시범 승인 신청 건수×건별 지원 상한과 운영 항목별 수량×가정 단가로 임시 예산을 다시 계산하세요.', 'critical'))
    kpi = str(strategy.get('kpi') or '')
    missing = measurement_missing(kpi)
    if missing:
        problems.append(issue(prefix + '.kpi', '성과 측정 설계 누락: ' + ', '.join(missing),
                              '누락 요소를 채우세요. 취소 제외 결제액/적격 참여자 등 대상 정의와 자료 수집 담당을 적고 전후 변화와 사업 효과를 구분하세요.'))
    if ('증가율' in kpi and re.search(r'/|÷|분자.+분모', kpi)
            and not re.search(r'[-−－]|차이|증가분|차감', kpi)):
        problems.append(issue(prefix + '.kpi.growth_formula', '증가율 식에 기준값을 빼는 과정이 없습니다.',
                              '증가율=(사업기간 값-전년 같은 기간 값)/전년 같은 기간 값×100. 전년 값이 0이면 산정 불가로 표시하세요.', 'critical'))
    if (re.search(r'\d+(?:\.\d+)?\s*%', kpi) and re.search(r'성공|중단|확대', kpi)
            and not re.search(r'가정|잠정|목표안|착수\s*전|산출\s*근거|출처', kpi)):
        problems.append(issue(prefix + '.kpi.threshold_basis', '성공·중단 수치의 근거나 가정 표시가 없습니다.',
                              '근거 없는 20%/5% 같은 문턱값을 확정하지 마세요. 근거 출처·산출 방법 또는 목표안/착수 전 확정 절차를 적으세요.'))
    steps = strategy.get('implementation_steps') or []
    for index, step in enumerate(steps, 1):
        if not re.search(r'담당|운영자|운영팀|사업팀|업체|시청|군청|구청|사업자|평가자|협력사', str(step.get('task') or '')):
            problems.append(issue(prefix + f'.implementation_steps[{index}].task', '실행 단계의 담당 역할이 없습니다.',
                                  '누가 어떤 입력·확인 조건으로 실제 작업을 하는지 task에 적고 deliverable을 구체적으로 유지하세요.'))
    return problems


def build_completion_checklist(review: dict, pack: dict, draft: dict) -> list[dict[str, Any]]:
    """누락 판정을 자료 부재로 둔갑시키지 않는 후속 조치표. API 추가 비용은 없다."""
    issues = list(review.get('issues') or [])
    text = json.dumps(draft, ensure_ascii=False)
    case_ids = [row.get('source_id') for row in pack.get('benchmark_cases') or [] if row.get('source_id')]
    rows: list[dict[str, Any]] = []

    def add(key: str, title: str, action: str, required: list[str], owner: str, status: str) -> None:
        rows.append({'id': key, 'title': title, 'action': action, 'required_materials': required,
                     'owner': owner, 'status': status})

    fields = ' '.join(str(row.get('field') or '') for row in issues)
    if 'planning_decision' in fields or (pack.get('transfer_assessment') or {}).get('selection_status') == 'needs_evidence':
        add('case_fit', '지역 적합성·후보 선정',
            f'이번 요청에는 사례 카드 {len(case_ids)}건이 있습니다. 먼저 보유 자료로 비교·선정 근거를 보완하고 확인되지 않은 운영 조건만 추가 확보합니다.',
            ['선택/비교 사업의 공식 운영지침·결과보고서(사업 지역, 시행기간, 대상, 비용, 성과 정의, URL/페이지)',
             '선택 지역에서 동일 운영 방식이 가능한지 확인할 참여 조건·협약 자료'],
            'AI 재비교 + 담당자 공식 문서 확인', '보유 근거 재검토 / 적용 조건 확인')
    if any(word in fields for word in ('budget', 'budget_formula')):
        add('budget', '예산 산식·단가', '보유 근거로 수량×단가 식을 작성합니다. 금액의 확정이 필요할 때만 견적을 추가 받습니다.',
            ['예산 상한(미정 가능), 적격 지급 건수/운영일수 가정',
             '인력·운영대행·정산·홍보 견적서 또는 공식 계약 내역(수량, 단가, 부가세 포함 여부, 기준일)'],
            'AI 산식 보완 + 운영/회계 담당', '설계 보완 / 확정 단가 별도 확인')
    if any(word in fields for word in ('kpi', 'measurement', 'expected_effect')):
        add('measurement', '성과 측정·추가 효과', '자료가 있는데 본문에 빠진 것인지 먼저 확인합니다. 관광 월간 통계만으로 사업 참여·재사용·순증 소비를 계산하지 않습니다.',
            ['동일 범위 전년 동기/운영 전 기준기간과 사업 기간의 취소 제외 결제액·건수(가능한 집계표)',
             '익명·집계된 신청/적격/지급/재사용 건수, 측정 주기, 비교집단 정의',
             '사후 수집 항목은 사업 전에 존재할 수 없으므로 수집 담당·방법·예정일만 먼저 확정'],
            'AI 측정 설계 + 사업/정산 담당', '집계 가능 여부 확인 / 사후 수집 계획')
    if 'implementation_steps' in fields:
        add('execution', '단계별 실행 방법', '담당 역할·작업·입력 조건·산출물·미확보 시 대안을 재작성합니다. 원자료를 다시 업로드할 문제는 아닙니다.',
            ['실제 담당 부서/인력, 협력 가능 업체, 시스템 사용 가능 여부(모르면 협의 조건으로 남김)'],
            'AI 재작성 + 운영 담당 확인', '작성 보완')
    if re.search(r'환급|상품권', text) and issues:
        add('voucher_rules', '환급·상품권 운영 가능 여부', '현재 응답의 문구만으로 지급 허용·즉시 정산을 확인할 수 없습니다. 공식 지침을 대조해야 합니다.',
            ['선택 지역 상품권 운영지침/공고: 관광 환급 허용 여부, 가맹점·업종, 수수료, 지급 시점, 취소·중복 수혜 규칙',
             '자료 제공 가능 항목 안내(개인정보·카드번호·이름은 보내지 않음)'],
            '지자체 상품권/관광 담당', '적용 조건 확인 필요')
    if any('no_free_search_api_key' in str(row) or '검색 API 키가 설정되지' in str(row)
           for row in pack.get('research_gaps') or []):
        add('web_candidates', '새 공식 웹 자료 탐색', '이번 요청은 무료 검색 연결이 없어 저장 자료를 사용했습니다. 공식 URL/PDF를 보내는 방법으로도 보완할 수 있습니다.',
            ['공식 원문 URL 또는 PDF, 또는 기존 지원 무료 검색 서비스 키를 개발 PC .env에 설정(채팅으로 키 전송 금지)'],
            '개발 담당', '선택 사항 / 원문 검수 후 근거 사용')
    return rows
