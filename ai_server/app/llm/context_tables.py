"""Lossless row-table encoding for repeated evidence fields; never truncates values."""
from __future__ import annotations

import json
from typing import Any

TABLE = '__evidence_table_v1__'
MAPPING = '__evidence_mapping_v1__'
TABLE_READING_RULE = (
    '\n근거의 __evidence_table_v1__는 무손실 표다. columns가 열 이름, rows의 각 배열이 같은 순서의 한 행이다. '
    '각 셀의 원수치·문자열·null을 그대로 읽으며 집계/요약이 아니다. '
    '__evidence_mapping_v1__는 [키, 값] 쌍의 원래 객체다. 출처와 단위도 같은 규칙으로 복원해 해석한다.'
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def encode_tables(value: Any) -> Any:
    if isinstance(value, dict):
        # Escape real user/source objects with our reserved names, preserving all keys.
        if TABLE in value or MAPPING in value:
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
    if TABLE in value:
        table = value[TABLE]
        return [{key: decode_tables(cell) for key, cell in zip(table['columns'], row, strict=True)}
                for row in table['rows']]
    if MAPPING in value:
        return {key: decode_tables(item) for key, item in value[MAPPING]}
    return {key: decode_tables(item) for key, item in value.items()}


def evidence_json(value: Any) -> str:
    return _json(encode_tables(value))


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
