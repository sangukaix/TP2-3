"""Preserve report evidence, omit execution telemetry, encode repeated text once."""
from collections import Counter
import json
from .context_tables import encode_tables, decode_tables, TABLE_READING_RULE

REF = '__chat_text_ref_v1__'
ESCAPE = '__chat_map_v1__'
READING_RULE = TABLE_READING_RULE + (
    '\ncurrent_report의 shared_text는 반복 원문 사전이다. data 안의 '
    '__chat_text_ref_v1__:n은 shared_text[n]의 원문 전체와 같다. 요약이 아니다. '
    '__chat_map_v1__는 원래 객체의 [키, 값] 쌍이다. '
    '보고서 수정은 저장 당시 관측·ML·근거로 수행한다. 최신 자료를 조회·재학습했다고 말하지 않는다. '
    '실행 로그(agent_trace)는 수정 근거가 아니므로 전송하지 않는다.'
)


def revision_report(report):
    """기존 본문 보완에 한정: 미인용 RAG는 원문 대신 보존된 출처 목록으로 구분합니다."""
    result = dict(report)
    cited_context = json.dumps({key: report.get(key) for key in
                               ('strategies', 'planning_decision', 'observed_findings')}, ensure_ascii=False)
    evidence, reference_only = [], []
    for source in report.get('evidence_sources') or []:
        if source.get('source_type') == 'rag' and (not source.get('source_id') or str(source['source_id']) not in cited_context):
            reference_only.append({key: source[key] for key in
                                   ('source_id', 'title', 'source_url', 'chunk_id', 'page_start', 'page_end') if key in source})
        else:
            evidence.append(source)
    result['evidence_sources'] = evidence
    result['reference_only_not_read'] = reference_only
    return result


def pack_report(report):
    payload = {key: value for key, value in report.items() if key != 'agent_trace'}
    counts = Counter()
    def count(value):
        if isinstance(value, str) and len(value) >= 60:
            counts[value] += 1
        elif isinstance(value, dict):
            for item in value.values(): count(item)
        elif isinstance(value, list):
            for item in value: count(item)
    count(payload)
    shared = [value for value, times in counts.items() if times > 1]
    indexes = {value: index for index, value in enumerate(shared)}
    def encode(value):
        if isinstance(value, str) and value in indexes:
            return {REF: indexes[value]}
        if isinstance(value, list):
            return [encode(item) for item in value]
        if isinstance(value, dict):
            if REF in value or ESCAPE in value:
                return {ESCAPE: [[key, encode(item)] for key, item in value.items()]}
            return {key: encode(item) for key, item in value.items()}
        return value
    return {'shared_text': shared, 'data': encode_tables(encode(payload))}


def unpack_report(packed):
    def decode(value):
        if isinstance(value, list): return [decode(item) for item in value]
        if not isinstance(value, dict): return value
        if REF in value: return packed['shared_text'][value[REF]]
        if ESCAPE in value: return {key: decode(item) for key, item in value[ESCAPE]}
        return {key: decode(item) for key, item in value.items()}
    return decode(decode_tables(packed['data']))
