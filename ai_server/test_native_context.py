"""Strict native context: preserve input; reject old servers and oversize errors."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.llm.router import LLMRouter


class NativeContextTests(unittest.TestCase):
    def run_request(self, version='0.34.0', error=None, incomplete=False):
        seen = []
        messages = [{'role': 'user', 'content': '원문 보존 ' * 10000}]
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test',
                                  native_context_validation=True)
        provider._check_context(messages, {}, 8000)

        def handler(request):
            seen.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'version': version})
            body = json.loads(request.content)
            self.assertEqual(body['messages'], messages)
            self.assertIs(body['truncate'], False)
            self.assertIs(body['shift'], False)
            self.assertEqual(body['options']['num_predict'], 8000)
            if error:
                return httpx.Response(400, json={'error': error})
            return httpx.Response(200, json={'done': True,
                'done_reason': 'length' if incomplete else 'stop',
                'prompt_eval_count': 30052, 'eval_count': 2847,
                'message': {'content': '{"answer":"ok"}'}})

        real_client = httpx.AsyncClient
        with patch('ai_server.app.llm.ollama_provider.httpx.AsyncClient',
                   side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            try:
                result = asyncio.run(provider._call(model='qwen-test', messages=messages,
                                                   schema={'type': 'object'}, max_output_tokens=8000))
                return result, seen
            except LLMProviderError as exc:
                return exc, seen

    def test_native_fit_uses_actual_tokens_without_altering_evidence(self):
        result, seen = self.run_request()
        self.assertEqual(result[1]['input_tokens'], 30052)
        self.assertEqual([r.method for r in seen], ['GET', 'POST'])

    def test_unsupported_or_unknown_version_never_sends_prompt(self):
        for version in ['0.33.3', '', 'unknown', None, '0.34.0-dev']:
            with self.subTest(version=version):
                result, seen = self.run_request(version)
                self.assertEqual(result.code, 'OLLAMA_NATIVE_CONTEXT_UNSUPPORTED')
                self.assertEqual([r.method for r in seen], ['GET'])

    def test_server_context_rejection_is_not_retried_or_accepted(self):
        result, seen = self.run_request(error='{"error":{"type":"exceed_context_size_error"}}')
        self.assertEqual(result.code, 'OLLAMA_CONTEXT_BUDGET_EXCEEDED')
        self.assertEqual(len(seen), 2)

    def test_incomplete_output_is_not_accepted(self):
        result, _ = self.run_request(incomplete=True)
        self.assertEqual(result.code, 'OLLAMA_INCOMPLETE_RESPONSE')
        self.assertEqual(result.usage['input_tokens'], 30052)

    def test_opt_in_and_default_conservative_guard(self):
        with TemporaryDirectory() as folder:
            router = LLMRouter(project_root=Path(folder), env_values={
                'OLLAMA_NATIVE_CONTEXT_VALIDATION': 'true', 'OPENAI_MODEL': 'unchanged'})
            self.assertTrue(router.providers['qwen'].native_context_validation)
            self.assertTrue(router.providers['gemma'].native_context_validation)
            self.assertEqual(router.providers['openai'].default_model, 'unchanged')
        provider = OllamaProvider(base_url='', default_model='test')
        with self.assertRaises(LLMProviderError):
            provider._check_context([{'content': '원문 ' * 30000}], {}, 8000)
        provider.native_context_validation = True
        with self.assertRaises(LLMProviderError):
            provider._check_context([], {}, 40960)


if __name__ == '__main__':
    unittest.main()
