"""No model/network: verify table packing preserves every evidence value and type."""
from copy import deepcopy
import json
import unittest

from ai_server.app.llm.context_tables import TABLE, MAPPING, encode_tables, decode_tables, evidence_json, schema_field_guidance
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.scripts.check_local_agent_smoke import semantic_errors


class ContextTableTests(unittest.TestCase):
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
