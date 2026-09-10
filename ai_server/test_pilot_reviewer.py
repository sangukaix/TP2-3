import json
from pathlib import Path
import unittest
from ai_server.app.scripts.evaluate_pilot_reviewer import build_request, deterministic_issues


class PilotReviewerTest(unittest.TestCase):
    def test_request_contains_exact_server_contract_and_gemma_draft(self):
        planner = json.loads((Path(__file__).resolve().parents[1] / 'storage' /
            'candidate_pilot_planner_6917d3fa759f47f09efc378c7f1db45b.json').read_text(encoding='utf-8'))
        request = build_request(planner, 'qwen3:14b')
        payload = json.loads(request['messages'][1]['content'])
        self.assertEqual(payload['server_owned_contract'], planner['server_owned_contract'])
        self.assertEqual(payload['gemma_draft'], planner['answer'])
        self.assertEqual(request['max_output_tokens'], 2600)

    def test_rejects_unfinished_planner_artifact(self):
        with self.assertRaises(ValueError):
            build_request({'status': 'failed'}, 'qwen3:14b')

    def test_deterministic_audit_catches_actual_overclaims(self):
        planner = json.loads((Path(__file__).resolve().parents[1] / 'storage' /
            'candidate_pilot_planner_6917d3fa759f47f09efc378c7f1db45b.json').read_text(encoding='utf-8'))
        issues = deterministic_issues(planner)
        self.assertIn('temporary_budget_total_missing_from_text', issues)
        self.assertIn('unsupported_realtime_operation', issues)
        self.assertIn('unsupported_system_build', issues)


if __name__ == '__main__':
    unittest.main()
