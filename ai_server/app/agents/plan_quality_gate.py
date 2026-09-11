"""OpenAI 호출 전후에 실행하는 결정적 기획안 품질 점검입니다.

LLM 검토만으로는 출처 ID 누락·단계 수·비용 산식처럼 코드로 확정할 수 있는 오류가
통과할 수 있습니다. 이 모듈은 새로운 기획 내용을 만들지 않고, 재작성해야 할 항목만
짧은 구조화 오류로 반환합니다.
"""

from __future__ import annotations

from typing import Any
import re
from .decision_facts import comparison_direction_issues, past_execution_month_issues
from .planning_requirements import (
    QUALITY_CONTRACT_VERSION, candidate_delivery_issues, execution_delivery_issues, has_cost_formula,
)


CONCRETE_OPERATION_WORDS = (
    '쿠폰', '환급', '예약', '혜택', '참여', '운영시간', '상품권', '인증', '지급',
    '모집', '체험', '프로그램', 'QR', '코스', '발급', '할인',
)
KPI_MEASUREMENT_WORDS = ('기준월', '원자료', '측정', '월별', '주별', '전후', '비교')
MINIMUM_REVIEW_SCORE = 82
_WEAK_ML_RELIABILITY = {'below_baseline_on_test', 'mixed_recursive_performance', 'no_test_improvement'}


def cited_source_ids(text: str, known_ids: set[str]) -> set[str]:
    """dataset:1을 dataset:10 또는 dataset:1_fake의 인용으로 잘못 세지 않습니다."""
    return {source_id for source_id in known_ids
            if re.search(r'(?<![\w:./-])' + re.escape(source_id) + r'(?![\w:/-]|\.[\w])', text)}


def _rank_issues(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    """출력 개수를 줄이더라도 심각한 오류가 뒤에서 잘리지 않도록 먼저 정렬합니다."""
    return sorted(issues, key=lambda item: {'critical': 0, 'major': 1, 'minor': 2}.get(item.get('severity', ''), 3))


def _issue(severity: str, field: str, problem: str, revision_instruction: str) -> dict[str, str]:
    """Reviewer JSON과 같은 필드로 반환해 LLM 재작성 지시에 바로 재사용합니다."""
    return {
        'severity': severity,
        'field': field,
        'problem': problem,
        'revision_instruction': revision_instruction,
    }


def _weak_ml_effect_issue(snapshot: dict[str, Any], strategy: dict[str, Any], prefix: str) -> dict[str, str] | None:
    """기준선보다 약한 ML 전망을 사업 선택/성과 약속처럼 쓰지 못하게 합니다."""
    ml = snapshot.get('ml_analysis') or {}
    metrics = (ml.get('evaluation') or {}).get('metrics') or {}
    weak = [name for name, result in metrics.items()
            if str((result or {}).get('model_reliability') or '') in _WEAK_ML_RELIABILITY]
    weak.extend(str(signal.get('metric') or '') for signal in ml.get('signals') or []
                if str(signal.get('model_reliability') or '') in _WEAK_ML_RELIABILITY)
    if not weak:
        return None
    effect = str(strategy.get('expected_effect') or '')
    cites_ml_percentage = bool(re.search(r'(?:ML|머신러닝|자연추세).{0,120}\d+(?:\.\d+)?\s*%.{0,30}(?:증가|감소|전망)', effect, re.S))
    safe_caution = re.search(r'탐색적\s*참고|성과\s*목표로\s*사용하지\s*않|단독\s*선정\s*근거로\s*사용하지\s*않|기준선보다\s*오차', effect)
    if cites_ml_percentage and not safe_caution:
        return _issue(
            'major', prefix + '.expected_effect.ml_reliability',
            '기준선보다 약한 ML 전망의 증가율이 사업 선택 또는 성과 기대처럼 제시됐습니다.',
            '해당 전망은 탐색적 참고값이며 성과 목표·사업 효과가 아님을 명시하거나, 검증된 관측 지표와 사후 측정 가설로 바꾸세요.',
        )
    return None


def _unapproved_case_result_issues(evidence_pack: dict[str, Any], strategy: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    """정량 성과 사용이 보류된 사례의 증가율·실적을 본문에 되살리지 못하게 합니다."""
    issues: list[dict[str, str]] = []
    performance_pattern = re.compile(
        r'(?:\d[\d,.]*\s*(?:%|배|억\s*원|만\s*원|명|건).{0,100}(?:증가|감소|성과|효과|달성|매출|소비)|'
        r'(?:증가|감소|성과|효과|달성|매출|소비).{0,100}\d[\d,.]*\s*(?:%|배|억\s*원|만\s*원|명|건))',
        re.S,
    )
    for field in ('comparison_analysis', 'expected_effect'):
        text = str(strategy.get(field) or '')
        if not performance_pattern.search(text):
            continue
        for case in evidence_pack.get('benchmark_cases') or []:
            if case.get('quantitative_result_approved') is not False:
                continue
            region = str(case.get('case_region') or '').strip()
            aliases = {region, re.split(r'\s+', region)[-1]} if region else set()
            if any(alias and alias in text for alias in aliases):
                issues.append(_issue(
                    'major', f'{prefix}.{field}.unapproved_case_result',
                    '정량 성과 인용이 보류된 타지역 사례의 실적·증가율을 본문에 사용했습니다.',
                    '해당 수치는 삭제하고 사례에서는 이용 절차·운영 장치만 비교하세요. 발전 가능성은 선택 지역 시범의 대상 수×완료율×건별 측정값과 미운영 비교로 제시하세요.',
                ))
                break
    return issues


def build_plan_quality_precheck(evidence_pack: dict[str, Any], draft_report: dict[str, Any], *, limit: int | None = 8) -> dict[str, Any]:
    """출처·집행 단계·운영 방식·예산·KPI의 최소 실무 요건을 점검합니다.

    Provider와 무관하게 빈 초안·출처 변조·핵심 누락이 승인되는 것을 막습니다.
    """
    strategies = draft_report.get('strategies') or []
    if not strategies:
        return {'checked': True, 'issues': [_issue('critical', 'strategies', '실행 기획안이 없습니다.',
                                                   '근거에 연결된 통합 실행안 한 개를 작성하세요.')]}

    known_source_ids = {
        str(source.get('source_id')) for source in (evidence_pack.get('sources') or []) if source.get('source_id')
    }
    ml_source_id = str(((evidence_pack.get('snapshot') or {}).get('ml_analysis') or {}).get('source_id') or '')
    if ml_source_id:
        known_source_ids.add(ml_source_id)

    issues: list[dict[str, str]] = comparison_direction_issues(evidence_pack.get('snapshot') or {}, draft_report)
    issues.extend(past_execution_month_issues(evidence_pack.get('snapshot') or {}, draft_report))
    transfer = evidence_pack.get('transfer_assessment') or {}
    # 새 생성 계약의 후보 선정 내용을 검증합니다. 과거 저장 기획안에는 필드가 없을 수 있습니다.
    if 'selection_status' in transfer:
        candidates = transfer.get('design_candidates') or []
        ids = [candidate.get('candidate_id') for candidate in candidates]
        if (len(candidates) < 2
                or len(ids) != len(set(ids)) or not all(ids)
                or transfer.get('selected_candidate_id') not in ids or not transfer.get('selection_reason')):
            issues.append(_issue('major', 'planning_decision', '비교 가능한 사업 후보와 선정 근거가 충분하지 않습니다.',
                                 '근거 부족을 명시하고 검증 가능한 후보·선정 이유를 확인한 뒤 집행 여부를 판단하세요.'))
        if transfer.get('selection_status') != 'ready':
            issues.append(_issue('major', 'planning_decision.selection_status',
                                 '선택 후보의 지역 적용 조건이 미확인 상태입니다.',
                                 '후보 수 부족과 구분하세요. prerequisites/selection_reason의 미확인 조건과 필요한 공식 문서를 명시하고, 확인 전 집행 승인이나 ready 변경을 하지 마세요.'))
        candidate_types = [str(candidate.get('candidate_type') or '').strip() for candidate in candidates]
        if len(candidates) >= 2 and (not all(candidate_types) or len(set(candidate_types)) < 2):
            issues.append(_issue('major', 'planning_decision.candidate_type',
                                 '후보들이 서로 다른 운영 원리로 비교되지 않았습니다.',
                                 '방문→소비, 체류 전환, 예약 전환, 재방문, 접근성 등 실제 작동 원리가 다른 후보를 비교하고 candidate_type을 명시하세요.'))
        case_ids = {str(case.get('source_id')) for case in evidence_pack.get('benchmark_cases') or []}
        references = list(transfer.get('recommended_case_ids') or [])
        references += list((transfer.get('strategy_brief') or {}).get('supporting_case_ids') or [])
        references += [row.get('case_source_id') for row in transfer.get('candidate_assessments') or []]
        for candidate in candidates:
            references += list(candidate.get('case_source_ids') or [])
            if any(ref not in known_source_ids for ref in candidate.get('evidence_source_ids') or []):
                issues.append(_issue('critical', 'planning_decision.evidence_source_ids', '후보에 미등록 근거가 연결됐습니다.',
                                     '실제 sources에 있는 source_id만 사용하세요.'))
        if any(ref not in case_ids for ref in references):
            issues.append(_issue('critical', 'planning_decision.case_source_ids', '후보에 미등록 사례가 연결됐습니다.',
                                 'benchmark_cases에 없는 사례 인용을 제거하고 근거를 재확인하세요.'))
    if evidence_pack.get('quality_contract_version') == QUALITY_CONTRACT_VERSION:
        issues.extend(candidate_delivery_issues(evidence_pack, transfer))
    for index, strategy in enumerate(strategies, start=1):
        prefix = f'strategies[{index}]'
        evidence = str(strategy.get('evidence') or '')
        cited_sources = cited_source_ids(evidence, known_source_ids)
        named_ids = {match.rstrip('.') for match in re.findall(r'(?<![\w/])[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9_:.-]+', evidence)
                     if not match.startswith(('http:', 'https:'))}
        if named_ids - known_source_ids:
            issues.append(_issue('critical', f'{prefix}.evidence', '등록되지 않은 source_id가 포함됐습니다.',
                                 '정상 인용과 섞여 있어도 미등록 ID는 삭제하거나 실제 출처로 교체하세요.'))
        if not cited_sources:
            issues.append(_issue(
                'critical', f'{prefix}.evidence', '사용 가능한 근거 source_id가 기획안에 연결되지 않았습니다.',
                'evidence에 실제 사용한 source_id와 기준기간을 넣고, 근거 밖의 사실은 삭제하세요.',
            ))

        steps = strategy.get('implementation_steps') or []
        if len(steps) != 5:
            issues.append(_issue(
                'major', f'{prefix}.implementation_steps', '집행 단계가 정확히 5개가 아닙니다.',
                '준비→모집/선정→운영 준비→시범 운영→성과 판단 순서의 5단계로 작성하세요.',
            ))
        else:
            for step_number, step in enumerate(steps, start=1):
                if step.get('step') != step_number:
                    issues.append(_issue('major', f'{prefix}.implementation_steps[{step_number}].step',
                                         '단계 번호가 1~5 순서와 다릅니다.', '단계 번호를 중복 없이 1~5로 작성하세요.'))
                if not str(step.get('schedule') or '').strip() or not str(step.get('task') or '').strip() or not str(step.get('deliverable') or '').strip():
                    issues.append(_issue(
                        'major', f'{prefix}.implementation_steps[{step_number}]', '일정·해야 할 일·완료 산출물 중 하나가 비어 있습니다.',
                        '각 단계에 기간, 실제 행동, 눈으로 확인 가능한 결과물 1개를 모두 작성하세요.',
                    ))

        solution = str(strategy.get('solution') or '')
        if not any(word in solution for word in CONCRETE_OPERATION_WORDS):
            issues.append(_issue(
                'major', f'{prefix}.solution', '실제 사업이 어떻게 작동하는지 확인하기 어렵습니다.',
                '대상, 참여 조건, 혜택 또는 예약·지급 방식, 운영 범위 중 최소 2가지를 구체적으로 쓰세요.',
            ))

        budget = str(strategy.get('budget') or '')
        if not has_cost_formula(budget):
            issues.append(_issue(
                'major', f'{prefix}.budget', '예산 산정 방식이 보이지 않습니다.',
                '비용 항목×수량×공식 단가 또는 비교견적 확보 방식으로 예산을 적으세요.',
            ))

        kpi = str(strategy.get('kpi') or '')
        if not any(word in kpi for word in KPI_MEASUREMENT_WORDS):
            issues.append(_issue(
                'major', f'{prefix}.kpi', '성과 확인의 기준·주기·데이터 출처가 부족합니다.',
                '기준월, 확인 주기, 원자료, 성공 여부를 판단할 비교 방식을 함께 쓰세요.',
            ))

        if evidence_pack.get('quality_contract_version') == QUALITY_CONTRACT_VERSION:
            issues.extend(execution_delivery_issues(strategy, prefix))
            issues.extend(_unapproved_case_result_issues(evidence_pack, strategy, prefix))
            weak_ml_issue = _weak_ml_effect_issue(evidence_pack.get('snapshot') or {}, strategy, prefix)
            if weak_ml_issue:
                issues.append(weak_ml_issue)

    # Reviewer 입력은 8개로 제한하고, 최종 화면용 검사에서는 전체 목록을 반환한다.
    ranked = _rank_issues(issues)
    return {'checked': True, 'issues': ranked if limit is None else ranked[:limit], 'issue_count': len(ranked)}


def merge_quality_precheck(review: dict[str, Any], precheck: dict[str, Any], *, limit: int | None = 8) -> dict[str, Any]:
    """결정적 오류를 Reviewer 결과에 합쳐, 승인 상태가 코드 규칙을 우회하지 못하게 합니다."""
    merged = dict(review)
    existing = list(merged.get('issues') or [])
    existing_keys = {(str(item.get('field')), str(item.get('problem'))) for item in existing}
    deterministic_issues = list(precheck.get('issues') or []) if precheck.get('checked') else []
    for issue in deterministic_issues:
        key = (issue['field'], issue['problem'])
        if key not in existing_keys:
            existing.append(issue)
            existing_keys.add(key)

    # critical·major는 한 번의 자동 재작성 기회를 주기 위해 통과를 막습니다.
    if any(issue['severity'] in {'critical', 'major'} for issue in deterministic_issues):
        merged['approved'] = False
        merged['overall_score'] = min(int(merged.get('overall_score') or 0), 81)
        notice = '코드 점검에서 실행·근거 보완 항목이 확인되었습니다.'
        if notice not in str(merged.get('summary') or ''):
            merged['summary'] = f"{merged.get('summary') or '검토 필요'} · {notice}"

    # 프롬프트에만 있던 82점 규칙을 코드에서도 강제합니다. 모델이 approved=true를
    # 잘못 반환해도 점수가 낮거나 critical 이슈가 있으면 최종 통과할 수 없습니다.
    score = int(merged.get('overall_score') or 0)
    if score < MINIMUM_REVIEW_SCORE:
        merged['approved'] = False
        score_key = ('quality_review.overall_score', f'최종 검수 점수가 {MINIMUM_REVIEW_SCORE}점 미만입니다.')
        if score_key not in existing_keys and len(existing) < 8:
            existing.append(_issue(
                'major', 'quality_review.overall_score',
                f'최종 검수 점수가 {MINIMUM_REVIEW_SCORE}점 미만입니다.',
                '근거 연결, 실행 단계, 예산 산식, KPI 측정 방법을 보완한 뒤 다시 검수하세요.',
            ))
    if any(str(issue.get('severity')) in {'critical', 'major'} for issue in existing):
        merged['approved'] = False
    ranked = _rank_issues(existing)
    merged['issues'] = ranked if limit is None else ranked[:limit]
    return merged
