"""Lossless row-table encoding for repeated evidence fields; never truncates values."""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from typing import Any

TABLE = '__evidence_table_v1__'
MAPPING = '__evidence_mapping_v1__'
SHARED = '__evidence_shared_v1__'
REF = '__evidence_ref_v1__'
TABLE_READING_RULE = (
    '\n근거의 __evidence_table_v1__는 무손실 표다. columns가 열 이름, rows의 각 배열이 같은 순서의 한 행이다. '
    '각 셀의 원수치·문자열·null을 그대로 읽으며 집계/요약이 아니다. '
    '__evidence_mapping_v1__는 [키, 값] 쌍의 원래 객체다. 출처와 단위도 같은 규칙으로 복원해 해석한다. '
    '__evidence_shared_v1__가 있으면 data가 원문이고 values는 공통 내용 사전이다. '
    '__evidence_ref_v1__: N은 values[N]의 내용 전체를 그 자리에 대입한다. '
    '생략/요약이 아니라 동일 내용의 중복만 제거한 것이며 prefetched_evidence 인덱스는 복원한 data 기준이다.'
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def encode_tables(value: Any) -> Any:
    if isinstance(value, dict):
        # Escape real user/source objects with our reserved names, preserving all keys.
        if any(key in value for key in (TABLE, MAPPING, SHARED, REF)):
            return {MAPPING: [[key, encode_tables(item)] for key, item in value.items()]}
        return {key: encode_tables(item) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    encoded = [encode_tables(item) for item in value]
    if len(value) < 3 or not all(isinstance(item, dict) for item in value):
        return encoded
    columns = list(value[0])
    if len(columns) < 2 or any(set(item) != set(columns) for item in value):
        return encoded
    packed = {TABLE: {'columns': columns,
                       'rows': [[encode_tables(item[key]) for key in columns] for item in value]}}
    return packed if len(_json(packed)) + 80 < len(_json(encoded)) else encoded


def decode_tables(value: Any) -> Any:
    """Verification helper: restore exact values/types without an LLM."""
    if isinstance(value, list):
        return [decode_tables(item) for item in value]
    if not isinstance(value, dict):
        return value
    if SHARED in value:
        bundle = value[SHARED]

        def expand(node: Any) -> Any:
            if isinstance(node, list):
                return [expand(item) for item in node]
            if isinstance(node, dict):
                if set(node) == {REF}:
                    return expand(bundle['values'][node[REF]])
                return {key: expand(item) for key, item in node.items()}
            return node

        return decode_tables(expand(bundle['data']))
    if TABLE in value:
        table = value[TABLE]
        return [{key: decode_tables(cell) for key, cell in zip(table['columns'], row, strict=True)}
                for row in table['rows']]
    if MAPPING in value:
        return {key: decode_tables(item) for key, item in value[MAPPING]}
    return {key: decode_tables(item) for key, item in value.items()}


def evidence_json(value: Any) -> str:
    return _json(encode_tables(value))


def shared_evidence_json(value: Any) -> str:
    """Exact repeated long values only; no compression of distinct evidence.

    Used for the complete server-prefetched batch, where source and case cards
    repeat the same statistics. All definitions travel in the same message.
    """
    encoded = encode_tables(value)
    counts: Counter[str] = Counter()

    def scan(node: Any) -> None:
        if isinstance(node, (dict, list, str)):
            serialized = _json(node)
            if len(serialized) >= 200:
                counts[serialized] += 1
        if isinstance(node, dict):
            for child in node.values():
                scan(child)
        elif isinstance(node, list):
            for child in node:
                scan(child)

    scan(encoded)
    values: list[Any] = []
    indexes: dict[str, int] = {}

    def children(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: visit(item) for key, item in node.items()}
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    def visit(node: Any) -> Any:
        serialized = _json(node) if isinstance(node, (dict, list, str)) else ''
        if counts.get(serialized, 0) >= 2:
            if serialized not in indexes:
                index = len(values)
                indexes[serialized] = index
                values.append(None)
                values[index] = children(node)
            return {REF: indexes[serialized]}
        return children(node)

    data = visit(encoded)
    original = _json(encoded)
    packed = _json({SHARED: {'values': values, 'data': data}})
    return packed if values and len(packed) + 80 < len(original) else original


def reassemble_prefetched_pages(rows: list[dict]) -> tuple[list[dict], list[int]]:
    """Join only complete ordered JSON pages already verified by EvidenceTools.

    Returns original-page -> reconstructed-row indexes for exact duplicate-read
    references. Partial/malformed pages remain byte-for-byte values in the list.
    """
    result: list[dict] = []
    indexes: list[int] = []
    offset = 0
    while offset < len(rows):
        row = rows[offset]
        page = row.get('result') or {}
        count = page.get('segment_count')
        if page.get('segment_index') == 0 and isinstance(count, int) and count > 0:
            pages = rows[offset:offset + count]
            if len(pages) == count and all(
                item.get('tool') == row.get('tool')
                and item.get('result', {}).get('segment_index') == index
                and item.get('result', {}).get('segment_count') == count
                and item.get('result', {}).get('source_id') == page.get('source_id')
                and item.get('result', {}).get('path') == page.get('path')
                and isinstance(item.get('result', {}).get('serialized_json_segment'), str)
                and 'error' not in item.get('result', {})
                for index, item in enumerate(pages)
            ):
                try:
                    content = json.loads(''.join(p['result']['serialized_json_segment'] for p in pages))
                except ValueError:
                    pass
                else:
                    indexes.extend([len(result)] * count)
                    result.append({**row, 'result': content})
                    offset += count
                    continue
        indexes.append(len(result))
        result.append(deepcopy(row))
        offset += 1
    return result, indexes


def schema_field_guidance(schema: dict) -> str:
    """Transmit field semantics to the prompt; format alone only constrains syntax."""
    descriptions = {}

    def visit(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        if isinstance(node.get('description'), str) and node['description'].strip():
            descriptions[path] = node['description']
        for key, child in (node.get('properties') or {}).items():
            visit(child, path + '.' + key)
        if isinstance(node.get('items'), dict):
            visit(node['items'], path + '[]')
        for key in ('anyOf', 'oneOf', 'allOf'):
            for index, child in enumerate(node.get(key) or []):
                visit(child, path + '/' + key + '/' + str(index))

    visit(schema, '$')
    if not descriptions:
        return ''
    return ('\n이번 출력 필드의 뜻은 다음과 같다. format은 형태만 제한하므로 이 설명도 반드시 따른다. '
            '요청하지 않은 기획 본문을 문자열 필드 안에 대신 넣지 마라.\n' + _json(descriptions))


def schema_without_guided_descriptions(schema: dict) -> dict:
    """이미 system 지시문에 전달한 설명만 format에서 중복 제거한다.

    검증 키워드·필드명·enum은 그대로 둔다. guidance가 방문하지 않는 $defs 등은
    설명까지 보존한다. 원본 Schema는 최종 검증과 다른 공급자 경로에서 계속 사용한다.
    """
    result = deepcopy(schema)

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if isinstance(node.get('description'), str) and node['description'].strip():
            node.pop('description')
        for child in (node.get('properties') or {}).values():
            visit(child)
        if isinstance(node.get('items'), dict):
            visit(node['items'])
        for key in ('anyOf', 'oneOf', 'allOf'):
            for child in node.get(key) or []:
                visit(child)

    visit(result)
    return result
