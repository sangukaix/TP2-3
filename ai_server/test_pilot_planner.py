import copy
import json
from pathlib import Path
import unittest

from ai_server.app.scripts.evaluate_pilot_planner import build_request


class PilotPlannerTest(unittest.TestCase):
    def test_handoff_preserves_contract_and_selected_cases(self):
        composed = json.loads((Path(__file__).resolve().parents[1] / 'storage' /
            'candidate_pilot_composed_400d234574eb446794ed552a61eb2249.json').read_text(encoding='utf-8'))
        frozen = json.loads((Path(__file__).resolve().parents[1] / 'storage' /
            'candidate_comparison_input_5207b2af04f74b3d909b4cd2abf7dd14.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(composed)
        request = build_request(composed, frozen, 'gemma4:26b')
        self.assertEqual(composed, before)
        payload = json.loads(request['messages'][1]['content'])
        self.assertEqual(payload['server_owned_contract']['budget']['total_krw'], 17500000)
        self.assertEqual({case['source_id'] for case in payload['case_cards']},
                         set(composed['answer']['compared_case_ids']))
        self.assertEqual(request['max_output_tokens'], 3500)

    def test_rejects_approved_or_noncomposed_input(self):
        with self.assertRaises(ValueError):
            build_request({'deterministic_contract_applied': False, 'report_approved': False}, {}, 'gemma4:26b')


if __name__ == '__main__':
    unittest.main()
