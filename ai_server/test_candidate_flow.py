import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from ai_server.app.scripts.compare_candidate_flow import build_request, SCHEMA


class CandidateFlowTest(unittest.TestCase):
    def frozen(self):
        request = {'model': 'qwen3:14b', 'max_output_tokens': 5600, 'schema': {},
                   'messages': [{'role': 'system', 'content': 'old instruction'},
                                {'role': 'user', 'content': 'unmodified official evidence'},
                                {'role': 'tool', 'content': 'unmodified tool reply'},
                                {'role': 'user', 'content': 'old final task'}]}
        return {'request': request, 'read_case_ids': ['case:a'],
                'request_sha256': hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}

    def test_preserves_evidence_and_budget_without_mutating_parent(self):
        frozen = self.frozen()
        before = json.dumps(frozen)
        request = build_request(frozen)
        self.assertEqual(request['messages'][1:-1], frozen['request']['messages'][1:-1])
        self.assertEqual(request['max_output_tokens'], 5600)
        self.assertEqual(json.dumps(frozen), before)
        self.assertNotIn('old final task', json.dumps(request))

    def test_rejects_modified_frozen_input(self):
        frozen = self.frozen()
        frozen['request']['messages'][1]['content'] = 'changed facts'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build_request(frozen)

    def test_example_schema_and_unreviewed_example_rejected(self):
        example = json.loads((Path(__file__).resolve().parents[1] /
                              'docs/examples/wonju_candidate_flow_draft.json').read_text(encoding='utf-8'))
        Draft202012Validator(SCHEMA).validate(example['answer'])
        example['review_status'] = 'ai_draft_pending_human_review'
        with self.assertRaisesRegex(ValueError, 'human content review'):
            build_request(self.frozen(), example)

    def test_reviewed_example_adds_only_example_message(self):
        example = json.loads((Path(__file__).resolve().parents[1] /
                              'docs/examples/wonju_candidate_flow_draft.json').read_text(encoding='utf-8'))
        example['review_status'] = 'human_reviewed_writing_example'  # Test fixture only.
        baseline = build_request(self.frozen())
        treatment = build_request(self.frozen(), example)
        treatment['messages'].pop(-2)
        self.assertEqual(treatment, baseline)
