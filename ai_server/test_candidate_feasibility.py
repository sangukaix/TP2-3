import copy
import json
from pathlib import Path
import unittest
from ai_server import test_candidate_flow
from ai_server.app.scripts.evaluate_candidate_feasibility import (
    request_for, request_for_development, request_for_pilot,
    request_for_pilot_repair, request_for_pilot_contract, REGIONAL_PILOT_CONTRACT_SCHEMA,
    select_pilot_case_cards, regional_context_for_pilot, pilot_contract, apply_pilot_contract,
    pilot_semantic_issues, pilot_reference_issues, arithmetic,
)


class FeasibilityTest(unittest.TestCase):
    def test_comparison_changes_only_reviewed_example_message(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        example = json.loads((Path(__file__).resolve().parents[1] /
                              'docs/examples/wonju_candidate_flow_draft.json').read_text(encoding='utf-8'))
        baseline = request_for(frozen)
        treatment = request_for(frozen, example)
        treatment['messages'].pop(-2)
        self.assertEqual(treatment, baseline)
        example['review_status'] = 'unreviewed'
        with self.assertRaises(ValueError):
            request_for(frozen, example)

    def test_preserves_frozen_evidence_and_limits(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        original = copy.deepcopy(frozen)
        request = request_for(frozen)
        self.assertEqual(frozen, original)
        self.assertEqual(request['messages'][1:-1], frozen['request']['messages'][1:-1])
        self.assertEqual(request['max_output_tokens'], frozen['request']['max_output_tokens'])
        frozen['request']['model'] = 'tampered'
        with self.assertRaises(ValueError):
            request_for(frozen)

    def test_decimal_math_is_not_semantic_approval(self):
        answer = {'candidates': [{'id': 'a', 'budget': {'total_krw': 0.3, 'items': [
            {'name': 'test', 'quantity': 3, 'unit_price_krw': 0.1, 'subtotal_krw': 0.3}]}}]}
        result = arithmetic(answer)[0]
        self.assertEqual(result['arithmetic_issues'], [])
        self.assertFalse(result['semantic_approval'])
        answer['candidates'][0]['budget']['items'][0]['subtotal_krw'] = 1
        self.assertEqual(len(arithmetic(answer)[0]['arithmetic_issues']), 2)

    def test_temporary_estimate_field_is_calculated(self):
        answer = {'candidates': [{'id': 'pilot', 'budget': {'total_krw': 5500000, 'items': [
            {'name': 'operation', 'quantity': 2, 'assumed_unit_price_krw': 1000000, 'subtotal_krw': 2000000},
            {'name': 'partners', 'quantity': 5, 'assumed_unit_price_krw': 500000, 'subtotal_krw': 2500000},
            {'name': 'measurement', 'quantity': 1, 'assumed_unit_price_krw': 1000000, 'subtotal_krw': 1000000}]}}]}
        self.assertEqual(arithmetic(answer)[0]['arithmetic_issues'], [])

    def test_missing_cost_is_not_zero_cost(self):
        answer = {'candidates': [{'id': 'a', 'budget': {'total_krw': None, 'items': [
            {'name': 'unknown', 'quantity': None, 'unit_price_krw': None, 'subtotal_krw': None}]}}]}
        self.assertEqual(len(arithmetic(answer)[0]['arithmetic_issues']), 2)

    def test_development_request_keeps_evidence_and_uses_all_case_cards(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        frozen['evidence_pack'] = {'benchmark_cases': [
            {'source_id': 'case:a'}, {'source_id': 'case:b'}]}
        original = copy.deepcopy(frozen)
        request = request_for_development(frozen)
        self.assertEqual(frozen, original)
        self.assertEqual(request['messages'][1:-1], frozen['request']['messages'][1:-1])
        self.assertIn('case:a, case:b', request['messages'][-1]['content'])
        self.assertEqual(request['max_output_tokens'], 5600)

    def test_pilot_request_is_a_smaller_task(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        frozen['evidence_pack'] = {'benchmark_cases': []}
        request = request_for_pilot(frozen)
        self.assertEqual(request['max_output_tokens'], 3600)
        schema = request['schema']['properties']
        self.assertIn('title', schema)
        self.assertNotIn('directions', schema)
        self.assertIn('미확인-시범 전 조사', request['messages'][0]['content'])
        self.assertIn('2026-09-08', request['messages'][0]['content'])

    def test_repair_uses_only_selected_registered_cards(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        frozen['evidence_pack'] = {'benchmark_cases': [
            {'source_id': 'case:a', 'secret': 'a'}, {'source_id': 'case:b', 'secret': 'b'},
            {'source_id': 'case:unused', 'secret': 'unused'}]}
        draft = {
            'title': 'draft', 'compared_case_ids': ['case:a', 'case:b'], 'case_comparison': 'x',
            'wonju_pilot': 'x', 'operating_flow': [{'actor': 'a', 'action': 'b', 'record': 'c'}] * 4,
            'budget': {'estimate_label': 'temporary_planning_estimate', 'volume_assumption': 'x',
                       'items': [{'name': 'n', 'quantity': 1, 'unit': 'u', 'assumed_unit_price_krw': 1,
                                  'subtotal_krw': 1, 'basis_and_limit': 'x'}] * 3,
                       'total_krw': 3, 'excluded_costs': ['x']},
            'development_potential': [{'name': 'n', 'current_baseline': 'unknown', 'pilot_target': '1',
                                       'calculation': 'x', 'data_record': 'x', 'interpretation_limit': 'x'}] * 2,
            'why_this_can_develop_wonju_tourism': 'x', 'limits': ['x']}
        request = request_for_pilot_repair(frozen, {'content': json.dumps(draft)})
        payload = request['messages'][1]['content']
        self.assertIn('case:a', payload)
        self.assertIn('case:b', payload)
        self.assertNotIn('case:unused', payload)
        self.assertEqual(request['max_output_tokens'], 3000)

    def test_contract_pilot_has_fixed_budget_and_measurement(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        frozen['evidence_pack'] = {'benchmark_cases': [
            {'source_id': 'case:night_festival_2025'},
            {'source_id': 'case:night_tourism_cities_2024'}],
            'region_code': '11680', 'region_name': '서울특별시 강남구',
            'period': '2025-08 ~ 2026-07',
            'sources': [
                {'source_type': 'dataset', 'source_id': 'dataset:11680:4',
                 'summary': '외지인 숙박 방문 비율: 3.1%', 'observation_period': '2026-07'},
                {'source_type': 'open_api', 'source_id': 'tour-api:2456536',
                 'title': '강남 마이스 관광특구', 'address': '서울특별시 강남구 영동대로 513',
                 'content_type_id': '12'},
            ]}
        request = request_for_pilot_contract(frozen)
        payload = json.loads(request['messages'][1]['content'])
        self.assertEqual(payload['pilot_contract']['budget_total_krw'], 17500000)
        self.assertEqual(payload['pilot_contract']['region_name'], '서울특별시 강남구')
        self.assertIn('서울특별시 강남구', request['messages'][0]['content'])
        self.assertNotIn('원주', request['messages'][0]['content'])
        self.assertIn('regional_pilot', REGIONAL_PILOT_CONTRACT_SCHEMA['required'])
        self.assertIn('regional_evidence_source_ids', REGIONAL_PILOT_CONTRACT_SCHEMA['required'])
        self.assertIn('case_application', REGIONAL_PILOT_CONTRACT_SCHEMA['required'])
        self.assertEqual(payload['regional_context']['observed_metrics'][0]['source_id'],
                         'dataset:11680:4')
        self.assertEqual(payload['regional_context']['registered_tourism_resources'][0]['source_id'],
                         'tour-api:2456536')
        self.assertEqual(len(payload['pilot_contract']['measurement_contract']), 2)
        self.assertEqual(request['max_output_tokens'], 3000)

    def test_case_selection_prefers_saved_official_night_case_summary(self):
        frozen = {'evidence_pack': {
            'benchmark_cases': [
                {'source_id': 'case:night_tourism_cities_2024'},
                {'source_id': 'case:night_festival_2025'},
            ],
            'sources': [
                {'source_type': 'benchmark_case', 'source_id': 'case:incheon',
                 'title': '인천 야간관광', 'summary': '야시장과 상권쿠폰을 결합',
                 'source_url': 'https://example.invalid/official'},
            ],
        }}
        cards = select_pilot_case_cards(frozen)
        self.assertEqual([card['source_id'] for card in cards],
                         ['case:night_tourism_cities_2024', 'case:incheon'])
        self.assertEqual(cards[1]['detail_level'], 'saved_official_source_summary')

    def test_regional_context_rejects_name_only_input(self):
        with self.assertRaises(ValueError):
            regional_context_for_pilot({'evidence_pack': {
                'region_code': '11680', 'region_name': '서울특별시 강남구'}})

    def test_reference_check_requires_exact_case_dataset_and_place_ids(self):
        payload = {
            'case_cards': [{'source_id': 'case:a'}, {'source_id': 'case:b'}],
            'regional_context': {
                'observed_metrics': [{'source_id': 'dataset:11680:4'}],
                'popular_places': [{'source_id': 'regional-status:abc'}],
                'registered_tourism_resources': [{'source_id': 'tour-api:1'}],
            },
        }
        answer = {'compared_case_ids': ['case:a', 'case:b'],
                  'case_application': [{'source_id': 'case:a'}, {'source_id': 'case:b'}],
                  'regional_evidence_source_ids': ['dataset:11680:4', 'tour-api:1']}
        self.assertEqual(pilot_reference_issues(answer, payload), [])
        answer['regional_evidence_source_ids'] = ['dataset:11680:4', 'tour-api:invented']
        self.assertIn('unknown_regional_source_id', pilot_reference_issues(answer, payload))
        self.assertIn('missing_regional_place_source', pilot_reference_issues(answer, payload))

    def test_pilot_semantic_checks_required_flow_and_ledger_terms(self):
        answer = {'operating_flow': [], 'budget': {'items': [{'name': '기타 비용'}]},
                  'development_potential': [{'current_baseline': '0'}]}
        issues = pilot_semantic_issues(answer)
        self.assertIn('visitor_reservation', issues)
        self.assertIn('generic_budget_item', issues)
        self.assertIn('invented_zero_baseline', issues)

    def test_contract_schema_requires_measurement_fields(self):
        frozen = test_candidate_flow.CandidateFlowTest().frozen()
        frozen['evidence_pack'] = {'benchmark_cases': [
            {'source_id': 'case:night_festival_2025'},
            {'source_id': 'case:night_tourism_cities_2024'}],
            'region_code': '11680', 'region_name': '서울특별시 강남구',
            'sources': [
                {'source_type': 'dataset', 'source_id': 'dataset:11680:4',
                 'summary': '외지인 숙박 방문 비율: 3.1%', 'observation_period': '2026-07'},
                {'source_type': 'open_api', 'source_id': 'tour-api:2456536',
                 'title': '강남 마이스 관광특구', 'address': '서울특별시 강남구 영동대로 513',
                 'content_type_id': '12'},
            ]}
        schema = request_for_pilot_contract(frozen)['schema']
        metric_required = schema['properties']['development_potential']['items']['required']
        self.assertIn('numerator', metric_required)
        self.assertIn('denominator', metric_required)
        self.assertIn('data_record_fields', metric_required)

    def test_server_contract_restores_numbers_and_ledgers(self):
        result = apply_pilot_contract({'title': 'LLM narrative'}, pilot_contract('서울특별시 강남구'))
        self.assertEqual(result['budget']['total_krw'], 17500000)
        self.assertIn('100건', result['development_potential'][0]['pilot_target'])
        self.assertIn('결제ID', result['development_potential'][1]['data_record_fields'])
        self.assertIn('서울특별시 강남구 전체',
                      result['development_potential'][0]['interpretation_limit'])
        self.assertNotIn('원주시 전체',
                         result['development_potential'][0]['interpretation_limit'])
        self.assertEqual(arithmetic({'candidates': [{'id': 'pilot', 'budget': result['budget']} ]})[0]['arithmetic_issues'], [])
        self.assertEqual(pilot_semantic_issues({**result, 'operating_flow': [
            {'actor': '방문객', 'action': '예약·결제·이용완료', 'record': '취소·중복 확인'}]}), [])


if __name__ == '__main__':
    unittest.main()
