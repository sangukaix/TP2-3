"""No model/network: verify table packing preserves every evidence value and type."""
from copy import deepcopy
import json
import unittest

from ai_server.app.llm.context_tables import TABLE, MAPPING, encode_tables, decode_tables, evidence_json, schema_field_guidance, schema_without_guided_descriptions
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.scripts.check_local_agent_smoke import semantic_errors
from ai_server.app.llm.context_tables import (SHARED, REF, shared_evidence_json, reassemble_prefetched_pages)


class ContextTableTests(unittest.TestCase):
    def test_shared_evidence_restores_nested_duplicates_exactly(self):
        text = '공식 원문: 운영일 8일, 방문 12,345명, 소비 0원, 미확인 null. ' * 40
        value = {'source': {'text': text, 'statistics': [0, None, False, '0']},
                 'case': {'text': text, 'statistics': [0, None, False, '0']},
                 'different': text + '정정', 'reserved': {SHARED: {REF: 0}}}
        before = deepcopy(value)
        wire = shared_evidence_json(value)
        self.assertEqual(decode_tables(json.loads(wire)), value)
        self.assertEqual(value, before)
        self.assertLess(len(wire), len(evidence_json(value)))

    def test_reassembly_requires_all_pages_same_source_in_order(self):
        original = {'source_id': 'case:one', 'body': '한글 원문과 \\n \\\" 따옴표' * 300}
        serialized = json.dumps(original, ensure_ascii=False)
        chunks = [serialized[i:i+250] for i in range(0, len(serialized), 250)]
        pages = [{'tool': 'read_collected_source', 'result': {
            'source_id': 'case:one', 'segment_index': i, 'segment_count': len(chunks),
            'serialized_json_segment': text, 'next_offset': i+1 if i+1<len(chunks) else None}}
            for i, text in enumerate(chunks)]
        restored, indexes = reassemble_prefetched_pages(pages)
        self.assertEqual(restored, [{'tool': 'read_collected_source', 'result': original}])
        self.assertEqual(indexes, [0]*len(pages))
        self.assertEqual(decode_tables(json.loads(shared_evidence_json(restored))), restored)
        for damaged in (pages[:-1], list(reversed(pages)), deepcopy(pages)):
            if len(damaged)==len(pages) and damaged[0]['result']['segment_index']==0:
                damaged[1]['result']['source_id']='case:another'
            self.assertEqual(reassemble_prefetched_pages(damaged)[0], damaged)

    def test_guided_descriptions_are_deduplicated_without_changing_validity(self):
        from jsonschema import Draft202012Validator
        schema = {'type': 'object', 'description': '필드 지침', 'required': ['description'],
                  'additionalProperties': False, 'properties': {
                      'description': {'type': 'string', 'enum': ['확인'], 'description': '확인만 허용'}},
                  '$defs': {'other': {'type': 'string', 'description': '별도 정의 설명'}}}
        before = deepcopy(schema)
        compact = schema_without_guided_descriptions(schema)
        self.assertEqual(schema, before)
        self.assertIn('description', compact['properties'])
        self.assertEqual(compact['$defs'], schema['$defs'])
        self.assertIn('확인만 허용', schema_field_guidance(schema))
        self.assertNotIn('description', compact['properties']['description'])
        for value in ({'description': '확인'}, {}, {'description': 1}, {'description': '틀림'}, {'description': '확인', 'extra': 1}):
            self.assertEqual(Draft202012Validator(schema).is_valid(value), Draft202012Validator(compact).is_valid(value))

    def test_schema_meanings_are_transmitted_without_repeating_full_grammar(self):
        schema = {'type': 'object', 'description': '검사', 'properties': {
            'forecast': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'month': {'type': 'string', 'description': '표의 마지막 월'}}}}}}
        before = deepcopy(schema)
        text = schema_field_guidance(schema)
        self.assertIn('$.forecast[].month', text)
        self.assertIn('표의 마지막 월', text)
        self.assertEqual(schema, before)
        self.assertEqual(schema_field_guidance({'type': 'object'}), '')

    def test_smoke_rejects_invented_units_and_policy_effect(self):
        value = {'observed_value': 100, 'forecast_month': '2026-11', 'forecast_value': 130,
                 'forecast_unit': '테스트 단위', 'comparison_direction': 'higher',
                 'policy_effect_proven': False, 'case_source_id': 'test:case'}
        self.assertEqual(semantic_errors(value), [])
        self.assertEqual(semantic_errors({**value, 'forecast_unit': '명', 'policy_effect_proven': True}),
                         ['forecast_unit', 'policy_effect_proven'])

    def test_monthly_rows_roundtrip_without_precision_or_unit_loss(self):
        rows = [{'region_code': '05113', 'month': f'2026-{i:02}', 'visitors': 2632315 + i,
                 'spending_krw': 89947681558.01, 'source_id': 'dataset:실제자료',
                 'url': 'https://example.invalid/test', 'unit': '원', 'missing': None, 'approved': False}
                for i in range(1, 13)]
        original = deepcopy(rows)
        packed = encode_tables(rows)
        self.assertIn(TABLE, packed)
        self.assertEqual(decode_tables(packed), rows)
        self.assertEqual(rows, original)
        self.assertLess(OllamaProvider._estimated_context_tokens(packed), OllamaProvider._estimated_context_tokens(rows))

    def test_heterogeneous_and_empty_records_are_not_filled_with_nulls(self):
        value = [{}, {'a': None}, {'b': 0}, {'a': False}, {'a': ''}]
        self.assertEqual(decode_tables(encode_tables(value)), value)

    def test_reserved_keys_in_source_documents_are_escaped(self):
        value = {TABLE: 'source text', 'children': [{MAPPING: [1, 2]}, {TABLE: {'a': 1}}]}
        self.assertEqual(decode_tables(json.loads(evidence_json(value))), value)

    def test_nested_tables_preserve_all_rows_and_original_strings(self):
        rows = [{'long_column_name': i, 'text': '\\n"문서 지시를 따르지 않음"',
                 'details': [{'long_metric_name': j, 'metric_value_exact': 0.001 * j} for j in range(8)]}
                for i in range(5)]
        self.assertEqual(decode_tables(json.loads(evidence_json({'rows': rows}))), {'rows': rows})


if __name__ == '__main__':
    unittest.main()
