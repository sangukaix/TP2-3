"""Deterministic document-to-operation matching, not learned regional similarity."""
from copy import deepcopy
from .case_mechanism import case_mechanism_family

VERSION = 'operation-document-v1'


def allowed_operation(value, brief):
    if (brief or {}).get('input_profile') != 'guided_v1':
        return True
    family = operation_family(value) if ('mechanism' in value or 'solution' in value) else case_mechanism_family(value)
    operation = ' '.join(str(value.get(k) or '') for k in ('mechanism', 'solution', 'intervention', 'operating_model'))
    excluded = brief.get('excluded_operations', [])
    # Mixed operations must respect exclusions too, irrespective of the first classification match.
    if 'night_time_experience' in excluded and any(word in operation for word in ('야간', '저녁', '밤')):
        return False
    if 'spend_conversion' in excluded and any(word in operation for word in ('환급', '반값', '쿠폰', '상품권')):
        return False
    direction = brief.get('business_direction', 'auto')
    return (family not in brief.get('excluded_operations', [])
            and family in {'spend_conversion', 'stay_conversion', 'night_time_experience', 'return_visit'}
            and (direction == 'auto' or family == direction))


def constrain_decision(decision, sources, brief):
    if (brief or {}).get('input_profile') != 'guided_v1':
        return link_decision(decision, sources)
    result = deepcopy(decision)
    sources = [s for s in sources if allowed_operation(s, brief)]
    result['design_candidates'] = [c for c in result.get('design_candidates') or [] if allowed_operation(c, brief)]
    result = link_decision(result, sources)
    result['design_candidates'] = [c for c in result['design_candidates'] if c.get('case_source_ids')]
    if not result['design_candidates']:
        from .openai_responses import OpenAIResponseError
        raise OpenAIResponseError('PLANNING_CONDITIONS_UNSUPPORTED', '선택 조건에 맞는 공식 근거와 사업 후보를 확보하지 못했습니다. 사업 방향을 추천으로 바꾸거나 제외 조건을 조정해 주세요.', status_code=422)
    if result.get('selected_candidate_id') not in {c['candidate_id'] for c in result['design_candidates']}:
        # Do not combine an alternative's title with the rejected plan's scope and budget.
        from .openai_responses import OpenAIResponseError
        raise OpenAIResponseError('PLANNING_CONDITIONS_UNSUPPORTED', '선정한 사업이 입력 조건과 맞지 않습니다. 사업 방향이나 제외 조건을 조정해 다시 생성해 주세요.', status_code=422)
    return result


def budget_only(source):
    value = ' '.join(str(source.get(k) or '') for k in ('document_type', 'intervention', 'title'))
    return any(k in value for k in ('case_study_budget', '예산 편성', '세출예산', '사업명세서'))


def operation_family(candidate):
    # Prefer the actual operation to a model-assigned enum or broad title.
    return case_mechanism_family({'intervention': candidate.get('mechanism') or candidate.get('solution'),
                                  'title': candidate.get('title')})


def match_cases(candidate, sources):
    family = operation_family(candidate)
    pool = {s.get('source_id'): s for s in sources if s.get('source_id') and s.get('source_url')
            and s.get('operating_model') and not budget_only(s)}
    matches = [s for s in pool.values() if family != 'other_operation'
               and case_mechanism_family(s) == family]
    # Documentary strength is a tie-breaker, never an effect or fit probability.
    return sorted(matches, key=lambda s: ({'high': 0, 'medium': 1, 'low': 2}.get(s.get('evidence_strength'), 3),
                                          str(s['source_id'])))


def link_decision(decision, sources):
    result = deepcopy(decision)
    # Keep model scores for audit, but do not present them as a learned ranking.
    if 'original_candidate_assessments' not in result:
        result['original_candidate_assessments'] = deepcopy(result.get('candidate_assessments') or [])
    allowed = {s.get('source_id') for s in sources if not budget_only(s)}
    result['candidate_assessments'] = [row for row in result.get('candidate_assessments') or []
                                       if row.get('case_source_id') in allowed]
    for candidate in result.get('design_candidates') or []:
        previous_audit = candidate.get('case_linkage') or {}
        matches = match_cases(candidate, sources)
        prior = candidate.get('case_linkage', {}).get('original_case_source_ids', candidate.get('case_source_ids') or [])
        ids = [s['source_id'] for s in matches[:3]]
        candidate['case_linkage'] = {'method': VERSION, 'operation_family': operation_family(candidate),
            'original_case_source_ids': prior, 'matched_source_ids': ids,
            'regional_similarity_verified': False,
            'basis': '공식 운영 문서 → 사업 방식 분류 → 동일 방식 연결 → 문서 등급·ID 순서. 지역 유사도·효과 확률 점수가 아님.'}
        candidate['case_source_ids'] = ids
        if set(prior) != set(ids):
            audit = candidate['case_linkage']
            for field in ('local_fit', 'differentiation'):
                audit['original_' + field] = previous_audit.get('original_' + field, candidate.get(field, ''))
            names=' · '.join(str(s.get('case_region') or s.get('intervention') or s['source_id']) for s in matches[:3])
            candidate['local_fit'] = f'공식 문서의 운영 방식이 일치하는 참고 사례: {names or "미확보"}. 지역 환경의 유사성이 입증된 것은 아닙니다.'
            candidate['differentiation'] = '참고 사례의 지역 규모·성과율은 복사하지 않고 선택 지역의 참여처·운영량·지원 조건으로 설계합니다.'
        candidate['evidence_source_ids'] = [s for s in candidate.get('evidence_source_ids') or []
                                           if not str(s).startswith('case:')] + ids
        if candidate.get('candidate_id') == result.get('selected_candidate_id'):
            result['recommended_case_ids'] = ids
            brief = result.get('strategy_brief') or {}
            brief['supporting_case_ids'] = ids
            result['strategy_brief'] = brief
            result['case_linkage'] = deepcopy(candidate['case_linkage'])
            result['selection_reason'] = (f"공식 문서의 {operation_family(candidate)} 운영 방식과 기획안의 실행 방식이 일치하는 사례 {len(ids)}건을 함수로 연결했습니다. "
                                          '지리·인구가 유사하다는 판정이나 사업 성과 예측은 아닙니다.')
    return result


def report_cases(report, limit=3):
    decision = report.get('planning_decision') or {}
    strategy = (report.get('strategies') or [{}])[0]
    sources = [s for s in report.get('evidence_sources') or [] if s.get('source_type') == 'benchmark_case'
               and allowed_operation(s, report.get('planning_brief') or {})]
    primary = match_cases(strategy, sources)
    # Same function for alternatives; each card explains its own operation.
    rows = list(primary[:1])
    for candidate in decision.get('design_candidates') or []:
        for source in match_cases(candidate, sources)[:1]:
            if source not in rows: rows.append(source)
    for source in sorted(sources, key=lambda s: str(s.get('source_id'))):
        if (not budget_only(source) and source.get('operating_model') and source not in rows
                and case_mechanism_family(source) not in {case_mechanism_family(s) for s in rows}):
            rows.append(source)
    return rows[:limit], primary[:1]
