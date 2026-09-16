"""Deterministic document-to-operation matching, not learned regional similarity."""
from copy import deepcopy
from .case_mechanism import case_mechanism_family

VERSION = 'operation-document-v2'


def allowed_operation(value, brief):
    if (brief or {}).get('input_profile') not in ('guided_v1', 'guided_v2'):
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
            and family in {'spend_conversion', 'stay_conversion', 'night_time_experience', 'return_visit',
                           'reservation_conversion', 'access_and_mobility', 'experience_product'}
            and (direction == 'auto' or family == direction))


def constrain_decision(decision, sources, brief, *, defer_repair=False):
    if (brief or {}).get('input_profile') not in ('guided_v1', 'guided_v2'):
        return link_decision(decision, sources)
    result = deepcopy(decision)
    sources = [s for s in sources if allowed_operation(s, brief)]
    result['design_candidates'] = [c for c in result.get('design_candidates') or [] if allowed_operation(c, brief)]
    result = link_decision(result, sources)
    result['design_candidates'] = [c for c in result['design_candidates'] if c.get('case_source_ids')]
    valid_ids = {c['candidate_id'] for c in result['design_candidates']}
    if not valid_ids or result.get('selected_candidate_id') not in valid_ids:
        # A model selection error must reach the existing one-shot local repair.
        # Preserve the complete original decision; never select the first survivor
        # while retaining the rejected plan's title, scope or budget.
        message = '모델이 선택한 사업을 허용된 운영 방식과 공식 사례에 연결하지 못했습니다.'
        if defer_repair:
            pending = deepcopy(decision)
            pending['selection_status'] = 'needs_evidence'
            pending['constraint_repair'] = {
                'problem': message,
                'selected_candidate_id': decision.get('selected_candidate_id'),
                'eligible_candidate_ids': sorted(valid_ids),
                'allowed_case_ids': [s.get('source_id') for s in sources],
                'required_fix': '제공된 공식 사례의 운영 방식과 사용자 조건에 맞게 후보를 다시 비교하고 selected_candidate_id, strategy_brief, 출처를 함께 수정하세요. 기존 제목·예산을 다른 후보에 붙이지 마세요.',
            }
            return pending
        from .openai_responses import OpenAIResponseError
        automatic = brief.get('business_direction', 'auto') == 'auto' and not brief.get('excluded_operations')
        raise OpenAIResponseError(
            'TRANSFERABILITY_SELECTION_UNSUPPORTED' if automatic else 'PLANNING_CONDITIONS_UNSUPPORTED',
            message + (' 사용자 입력 오류가 아닙니다. 후보 보완 후에도 연결이 확인되지 않아 본문 작성을 시작하지 않았습니다.'
                       if automatic else ' 지정한 사업 방향·제외 조건을 충족하는 후보 보완이 필요합니다.'),
            status_code=422,
        )
    result.pop('constraint_repair', None)
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
    # Preserve valid cited evidence. Never replace a model's documented choice with
    # the first alphabetic ID. Geography is retrieval context, not proven suitability.
    cited = candidate.get('case_source_ids') or []
    scope_order = {'selected_region': 0, 'same_province': 1, 'cross_province_peer': 2,
                   'cross_province': 3, 'national_or_unresolved': 4}
    return sorted(matches, key=lambda source: (
        cited.index(source['source_id']) if source['source_id'] in cited else len(cited),
        scope_order.get((source.get('retrieval_context') or {}).get('scope'), 5),
        {'high': 0, 'medium': 1, 'low': 2}.get(source.get('evidence_strength'), 3),
        str(source['source_id'])))


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
        valid = {source['source_id'] for source in matches}
        cited = [sid for sid in candidate.get('case_source_ids') or [] if sid in valid]
        ids = list(dict.fromkeys(cited))[:3] or [source['source_id'] for source in matches[:1]]
        current_ids = candidate.get('case_source_ids') or []
        candidate['case_linkage'] = {'method': VERSION, 'operation_family': operation_family(candidate),
            'original_case_source_ids': prior, 'matched_source_ids': ids,
            'regional_similarity_verified': False,
            'basis': '같은 운영 방식의 유효한 인용을 유지. 인용 누락·오류일 때만 지역 검색 맥락·문서 등급으로 참고 사례 1건 연결. 지역 적합성 순위나 효과 확률이 아님.'}
        candidate['case_source_ids'] = ids
        # Historical citation repair is an audit, not a reason to overwrite a
        # later explanation again during stabilization or export preparation.
        for field in ('local_fit', 'differentiation'):
            if 'original_' + field in previous_audit:
                candidate['case_linkage']['original_' + field] = previous_audit['original_' + field]
        if set(current_ids) != set(ids):
            audit = candidate['case_linkage']
            for field in ('local_fit', 'differentiation'):
                audit['original_' + field] = previous_audit.get('original_' + field, candidate.get(field, ''))
            names=' · '.join(str(s.get('case_region') or s.get('intervention') or s['source_id']) for s in matches if s['source_id'] in ids)
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
            if set(current_ids) != set(ids):
                result.setdefault('original_selection_reason', result.get('selection_reason', ''))
                result['selection_reason'] = '선택 후보의 운영 방식과 일치하는 공식 문서로 인용을 보완했습니다. 후보 간 우열은 보완된 근거를 바탕으로 다시 비교할 수 있습니다.'
            if not result.get('selection_reason'):
                result['selection_reason'] = (f"공식 문서의 {operation_family(candidate)} 운영 방식과 기획안의 실행 방식이 일치하는 사례 {len(ids)}건을 함수로 연결했습니다. "
                                          '지리·인구가 유사하다는 판정이나 사업 성과 예측은 아닙니다.')
    return result


def report_cases(report, limit=3):
    decision = report.get('planning_decision') or {}
    strategy = (report.get('strategies') or [{}])[0]
    sources = [s for s in report.get('evidence_sources') or [] if s.get('source_type') == 'benchmark_case'
               and allowed_operation(s, report.get('planning_brief') or {})]
    selected = next((row for row in decision.get('design_candidates') or [] if row.get('candidate_id') == decision.get('selected_candidate_id')), {})
    primary = match_cases({**strategy, 'case_source_ids': selected.get('case_source_ids') or decision.get('recommended_case_ids') or []}, sources)
    # Same function for alternatives; each card explains its own operation.
    rows = list(primary[:1])
    for candidate in decision.get('design_candidates') or []:
        for source in match_cases(candidate, sources)[:1]:
            if source not in rows: rows.append(source)
    for source in sorted(sources, key=lambda s: (
            {'selected_region': 0, 'same_province': 1, 'cross_province_peer': 2, 'cross_province': 3}.get((s.get('retrieval_context') or {}).get('scope'), 4),
            {'high': 0, 'medium': 1, 'low': 2}.get(s.get('evidence_strength'), 3), str(s.get('source_id')))):
        if (not budget_only(source) and source.get('operating_model') and source not in rows
                and case_mechanism_family(source) not in {case_mechanism_family(s) for s in rows}):
            rows.append(source)
    return rows[:limit], primary[:1]


def case_reference_role(report, source):
    """A filler reference is not a candidate the model compared."""
    decision = report.get('planning_decision') or {}
    source_id = source.get('source_id')
    if source in report_cases(report)[1]:
        return '핵심 운영 참고'
    if any(source_id in (row.get('case_source_ids') or []) for row in decision.get('design_candidates') or []):
        return '후보 비교에 사용한 사례'
    return '추가 운영 참고'
