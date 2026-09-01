"""OpenAI 호출 전후에 실행하는 결정적 기획안 품질 점검입니다.

LLM 검토만으로는 출처 ID 누락·단계 수·비용 산식처럼 코드로 확정할 수 있는 오류가
통과할 수 있습니다. 이 모듈은 새로운 기획 내용을 만들지 않고, 재작성해야 할 항목만
짧은 구조화 오류로 반환합니다.
"""

from __future__ import annotations

from typing import Any


CONCRETE_OPERATION_WORDS = (
    '쿠폰', '환급', '예약', '혜택', '참여', '운영시간', '상품권', '인증', '지급',
    '모집', '체험', '프로그램', 'QR', '코스', '발급', '할인',
)
BUDGET_FORMULA_WORDS = ('×', '비교견적', '단가', '수량', '산식', '견적')
KPI_MEASUREMENT_WORDS = ('기준월', '원자료', '측정', '월별', '주별', '전후', '비교')
MINIMUM_REVIEW_SCORE = 82


def _issue(severity: str, field: str, problem: str, revision_instruction: str) -> dict[str, str]:
    """Reviewer JSON과 같은 필드로 반환해 LLM 재작성 지시에 바로 재사용합니다."""
    return {
        'severity': severity,
        'field': field,
        'problem': problem,
        'revision_instruction': revision_instruction,
    }


def build_plan_quality_precheck(evidence_pack: dict[str, Any], draft_report: dict[str, Any]) -> dict[str, Any]:
    """출처·집행 단계·운영 방식·예산·KPI의 최소 실무 요건을 점검합니다.

    실제 OpenAI가 만든 정상 JSON만 대상으로 합니다. 단위 테스트의 간단한 가짜 초안처럼
    전략 배열 자체가 없는 입력은 이 모듈의 대상이 아니므로 빈 결과를 반환합니다.
    """
    strategies = draft_report.get('strategies') or []
    if not strategies:
        return {'checked': False, 'issues': []}

    known_source_ids = {
        str(source.get('source_id')) for source in (evidence_pack.get('sources') or []) if source.get('source_id')
    }
    ml_source_id = str(((evidence_pack.get('snapshot') or {}).get('ml_analysis') or {}).get('source_id') or '')
    if ml_source_id:
        known_source_ids.add(ml_source_id)

    issues: list[dict[str, str]] = []
    for index, strategy in enumerate(strategies, start=1):
        prefix = f'strategies[{index}]'
        evidence = str(strategy.get('evidence') or '')
        cited_sources = [source_id for source_id in known_source_ids if source_id in evidence]
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
        if not any(word in budget for word in BUDGET_FORMULA_WORDS):
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

    # 같은 오류가 여러 전략에 반복돼도 Reviewer 입력이 지나치게 길어지지 않게 최대 8개만 보냅니다.
    return {'checked': True, 'issues': issues[:8]}


def merge_quality_precheck(review: dict[str, Any], precheck: dict[str, Any]) -> dict[str, Any]:
    """결정적 오류를 Reviewer 결과에 합쳐, 승인 상태가 코드 규칙을 우회하지 못하게 합니다."""
    merged = dict(review)
    existing = list(merged.get('issues') or [])
    existing_keys = {(str(item.get('field')), str(item.get('problem'))) for item in existing}
    deterministic_issues = list(precheck.get('issues') or []) if precheck.get('checked') else []
    for issue in deterministic_issues:
        key = (issue['field'], issue['problem'])
        if key not in existing_keys and len(existing) < 8:
            existing.append(issue)
            existing_keys.add(key)

    # critical·major는 한 번의 자동 재작성 기회를 주기 위해 통과를 막습니다.
    if any(issue['severity'] in {'critical', 'major'} for issue in deterministic_issues):
        merged['approved'] = False
        merged['overall_score'] = min(int(merged.get('overall_score') or 0), 81)
        merged['summary'] = f"{merged.get('summary') or '검토 필요'} · 코드 점검에서 실행·근거 보완 항목이 확인되었습니다."

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
    if any(str(issue.get('severity')) == 'critical' for issue in existing):
        merged['approved'] = False
    merged['issues'] = existing
    return merged
