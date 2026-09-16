"""Source-bound planning rationale; binding is not a quality or causal verdict."""
from copy import deepcopy
import hashlib
import json


VERSION = 'source-bound-rationale-v1'
COMPARISON_CRITERIA = {
    'visitor_action': '이용 행동 · 방문객이 무엇을 하고 어떤 조건으로 혜택을 받는가',
    'operating_requirements': '운영 준비 · 참여처·인력·시간·시스템 중 무엇을 준비하는가',
    'measurement': '성과 확인 · 어떤 원장과 분자·분모로 이용 결과를 확인하는가',
}


def _candidate_fingerprint(candidate):
    basis = {key: candidate.get(key) for key in
             ('mechanism', 'local_fit', 'differentiation', 'prerequisites', 'measurement_plan', 'reasoning')}
    return hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode('utf8')).hexdigest()


def fact_catalog(pack):
    """Use source records, never candidate prose; stable IDs survive list reordering."""
    facts = {}
    for source in pack.get('sources') or []:
        sid = source.get('source_id')
        if sid and source.get('source_type') == 'dataset':
            facts[sid] = {'kind': 'observed', 'source_id': sid,
                          'record': deepcopy(source)}
    for signal in ((pack.get('snapshot') or {}).get('ml_analysis') or {}).get('signals') or []:
        if not signal.get('source_id') or not signal.get('metric') or not signal.get('period'):
            continue
        identity = [signal.get(k) for k in ('source_id', 'metric', 'period', 'aggregation')]
        fid = 'forecast:' + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf8')).hexdigest()[:16]
        facts[fid] = {'kind': 'forecast', 'source_id': signal['source_id'],
                      'record': deepcopy(signal)}
    return facts


def reasoning_guide(pack):
    # The mandatory tools already deliver every original value. This is an ID
    # index, not a second copy of the source records and forecast arrays.
    index = {}
    for fid, fact in fact_catalog(pack).items():
        row = fact['record']
        index[fid] = ({'kind': 'observed', 'summary': row.get('summary') or row.get('title')}
                      if fact['kind'] == 'observed' else
                      {'kind': 'forecast', **{key: row.get(key) for key in
                        ('source_id', 'metric', 'period', 'aggregation')}})
    return {'version': VERSION, 'facts': index,
            'originals': {'observed': 'get_region_metrics', 'forecast': 'get_ml_forecast'},
            'comparison_criteria': dict(COMPARISON_CRITERIA),
            'instruction': 'fact_ids에서 관측과 ML 전망을 구분해 선택한다. 수치·기간은 서버가 원문으로 연결한다. '
            'application_hypothesis는 확인된 사실이 아닌 제안이다. 각 후보를 같은 세 기준으로 비교하고 '
            'tradeoff에는 선택 시 감수할 불리한 점을 쓴다. 월별 지표만으로 소비 전환율·미방문 원인을 확인했다고 쓰지 않는다. '
            '사례의 운영 원문과 적용 제안·위험 검토도 구분한다. 목록 순서는 추천 순위가 아니다.'}


def bind_rationale(decision, pack):
    """Attach exact input records without rewriting the model's hypothesis or approval."""
    result = deepcopy(decision)
    catalog = fact_catalog(pack)
    bindings = {}
    for candidate in result.get('design_candidates') or []:
        reasoning = candidate.get('reasoning')
        if not isinstance(reasoning, dict):
            continue  # Older reports have no inferred reasoning trace.
        ids = list(dict.fromkeys(reasoning.get('fact_ids') or []))
        bindings[candidate['candidate_id']] = {
            'facts': {fid: deepcopy(catalog[fid]) for fid in ids if fid in catalog},
            'unresolved_fact_ids': [fid for fid in ids if fid not in catalog],
            'case_source_ids': list(candidate.get('case_source_ids') or []),
            'candidate_fingerprint': _candidate_fingerprint(candidate),
        }
        # Keep normal citations available to Planner and source validation too.
        sources = list(candidate.get('evidence_source_ids') or [])
        candidate['evidence_source_ids'] = list(dict.fromkeys(sources + [
            catalog[fid]['source_id'] for fid in ids if fid in catalog]))
    if bindings:
        result['rationale_evidence'] = {'version': VERSION, 'candidates': bindings,
                                      'selection_at_binding': {
                                          'candidate_id': result.get('selected_candidate_id'),
                                          'reason': result.get('selection_reason')},
                                      'comparison_criteria': dict(COMPARISON_CRITERIA)}
    return result


def report_rationale(report):
    """Read only a trace actually saved with the selected candidate and citations."""
    decision = report.get('planning_decision') or {}
    selected_id = decision.get('selected_candidate_id')
    selected = next((c for c in decision.get('design_candidates') or []
                     if c.get('candidate_id') == selected_id), {})
    evidence = decision.get('rationale_evidence') or {}
    selection_at_binding = evidence.get('selection_at_binding')
    if selection_at_binding and selection_at_binding != {
            'candidate_id': selected_id, 'reason': decision.get('selection_reason')}:
        return None
    bound = (evidence.get('candidates') or {}).get(selected_id)
    if not bound or not bound.get('facts') or not selected.get('reasoning'):
        return None
    if bound.get('unresolved_fact_ids') or set(bound.get('case_source_ids') or []) != set(selected.get('case_source_ids') or []):
        return None  # Citation repair must not validate the superseded explanation.
    if any(selected.get(key) != value for key, value in (bound.get('candidate_basis') or {}).items()):
        return None  # A later edited design needs its own comparison rationale.
    if bound.get('candidate_fingerprint') and bound['candidate_fingerprint'] != _candidate_fingerprint(selected):
        return None
    return {'title': selected.get('title', ''), 'facts': deepcopy(bound['facts']),
            'reasoning': deepcopy(selected['reasoning']),
            'selection_reason': decision.get('selection_reason') or '',
            'case_source_ids': list(bound.get('case_source_ids') or []),
            'comparison_criteria': dict(COMPARISON_CRITERIA)}


def rationale_sections(report):
    rationale = report_rationale(report)
    if not rationale:
        return []
    fact_lines = []
    for fact in rationale['facts'].values():
        row = fact['record']
        if fact['kind'] == 'observed':
            fact_lines.append('관측 · ' + str(row.get('summary') or row.get('title') or '') +
                              ' · 출처 ' + fact['source_id'])
        else:
            fact_lines.append(f"ML 전망 · {row.get('metric')} · {row.get('period')} · "
                              f"{row.get('forecast_value')} {row.get('unit', '')} · 집계 {row.get('aggregation', '')} · "
                              f"모델 평가 {row.get('model_reliability', '')} · 출처 {fact['source_id']}")
    reasoning = rationale['reasoning']
    return [('선정에 연결한 관측·전망', '\n'.join(fact_lines)),
            ('우리 지역에 적용할 가설', reasoning.get('application_hypothesis') or ''),
            ('같은 기준의 후보 비교', '\n'.join(
                label + '\n' + str(reasoning.get(key) or '') for key, label in COMPARISON_CRITERIA.items())),
            ('선택 이유와 감수할 조건', rationale['selection_reason'] + '\n' +
             str(reasoning.get('tradeoff') or '') + '\n선정 이유는 기획 판단이며 사업 효과의 예측·보장이 아닙니다.')]
