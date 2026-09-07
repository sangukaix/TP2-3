"""외부 API 비용 없이 출력 한도 회복·중복 과금 집계·Hybrid 폴백을 검증합니다."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from ai_server.app.agents.planner_agent import PlannerAgent
from ai_server.app.agents.reviewer_agent import ReviewerAgent
from ai_server.app.agents.transferability_agent import TransferabilityAgent
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.openai_provider import OpenAIProvider
from ai_server.app.llm.trace_store import _EVENTS, usage_summary
from ai_server.app.openai_responses import OpenAIResponseError, create_structured_response
from ai_server import test_llm_router as router_fixture
from ai_server.test_llm_router import FakeProvider, sample_request


SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'}},
          'required': ['answer'], 'additionalProperties': False}


def response_payload(*, status='completed', reason=None, answer='{"answer":"ok"}', output_tokens=13):
    """미완료여도 사용량과 부분 JSON이 있는 실제 Responses 형태를 재현합니다."""
    return {'id': 'unit-test-response', 'status': status, 'incomplete_details': {'reason': reason},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': answer}]}],
            'usage': {'input_tokens': 20, 'output_tokens': output_tokens, 'total_tokens': 20 + output_tokens,
                      'input_tokens_details': {'cached_tokens': 10},
                      'output_tokens_details': {'reasoning_tokens': 7}}}


class OpenAITokenRecoveryTest(unittest.TestCase):
    """HTTP를 대역으로 교체해 재시도 횟수와 두 번째 요청의 내용을 직접 검사합니다."""

    def call(self, replies, **overrides):
        self.requests, self.timeouts = [], []
        iterator = iter(replies)
        actual_client = httpx.AsyncClient

        def handler(request):
            self.requests.append(json.loads(request.content))
            reply = next(iterator)
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json=reply)

        def client(**kwargs):
            self.timeouts.append(kwargs['timeout'])
            return actual_client(transport=httpx.MockTransport(handler), **kwargs)

        kwargs = {'api_key': 'unit-test-placeholder', 'model': 'test-model', 'instructions': '근거 유지',
                  'input_payload': {'sources': [{'source_id': 'case:1', 'text': '원문 근거'}]},
                  'schema_name': 'test', 'schema': SCHEMA, 'reasoning_effort': 'medium',
                  'max_output_tokens': 16000, 'retry_max_output_tokens': 24000,
                  'timeout_seconds': 600, 'return_metadata': True, **overrides}
        with patch('ai_server.app.openai_responses.httpx.AsyncClient', side_effect=client):
            return asyncio.run(create_structured_response(**kwargs))

    def test_success_needs_only_one_call(self):
        result = self.call([response_payload()])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(result['usage']['total_tokens'], 33)
        self.assertEqual(self.timeouts, [600])

    def test_token_limit_retries_same_evidence_once_and_sums_usage(self):
        partial = response_payload(status='incomplete', reason='max_output_tokens',
                                   answer='{"answer":', output_tokens=16000)
        result = self.call([partial, response_payload()])
        self.assertEqual([row['max_output_tokens'] for row in self.requests], [16000, 24000])
        self.assertEqual({k: v for k, v in self.requests[0].items() if k != 'max_output_tokens'},
                         {k: v for k, v in self.requests[1].items() if k != 'max_output_tokens'})
        self.assertEqual(result['data'], {'answer': 'ok'})
        self.assertEqual(result['usage']['total_tokens'], 16053)
        self.assertEqual(result['usage']['reasoning_tokens'], 14)
        self.assertEqual(len(result['attempts']), 2)
        self.assertFalse(self.requests[1]['store'])

    def test_second_token_limit_stops_even_if_partial_json_parses(self):
        incomplete = response_payload(status='incomplete', reason='max_output_tokens')
        with self.assertRaises(OpenAIResponseError) as captured:
            self.call([incomplete, incomplete])
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(captured.exception.code, 'OPENAI_INCOMPLETE_RESPONSE')
        self.assertEqual(captured.exception.usage['total_tokens'], 66)

    def test_non_token_incomplete_and_failed_status_do_not_retry(self):
        for status, reason in [('incomplete', 'content_filter'), ('failed', 'max_output_tokens')]:
            with self.subTest(status=status, reason=reason):
                with self.assertRaises(OpenAIResponseError):
                    self.call([response_payload(status=status, reason=reason)])
                self.assertEqual(len(self.requests), 1)

    def test_auth_quota_bad_request_and_timeout_do_not_retry(self):
        replies = [httpx.Response(code, json={'error': {'message': 'test error'}}) for code in (401, 429, 400)]
        replies.extend([httpx.ReadTimeout('test timeout'), asyncio.TimeoutError('test deadline')])
        for reply in replies:
            with self.subTest(reply=type(reply).__name__):
                with self.assertRaises(OpenAIResponseError):
                    self.call([reply])
                self.assertEqual(len(self.requests), 1)

    def test_retry_timeout_preserves_first_attempt_cost(self):
        first = response_payload(status='incomplete', reason='max_output_tokens', output_tokens=16000)
        with self.assertRaises(OpenAIResponseError) as captured:
            self.call([first, httpx.ReadTimeout('test timeout')])
        error = captured.exception
        self.assertEqual(error.code, 'OPENAI_TIMEOUT')
        self.assertEqual(error.usage['total_tokens'], 16020)
        self.assertFalse(error.attempts[-1]['usage_reported'])

    def test_chat_or_disabled_retry_keeps_single_call(self):
        for retry_limit in (None, 800):
            with self.subTest(retry_limit=retry_limit):
                with self.assertRaises(OpenAIResponseError):
                    self.call([response_payload(status='incomplete', reason='max_output_tokens')],
                              max_output_tokens=800, retry_max_output_tokens=retry_limit)
                self.assertEqual(len(self.requests), 1)

    def test_schema_failure_keeps_usage_without_expensive_retry(self):
        with self.assertRaises(OpenAIResponseError) as captured:
            self.call([response_payload(answer='{"wrong":true}')])
        self.assertEqual(captured.exception.code, 'OPENAI_SCHEMA_VALIDATION_FAILED')
        self.assertEqual(captured.exception.usage['total_tokens'], 33)
        self.assertEqual(len(self.requests), 1)

    def test_web_search_and_domain_restrictions_survive_retry(self):
        first = response_payload(status='incomplete', reason='max_output_tokens')
        second = response_payload()
        second['output'].append({'type': 'web_search_call', 'status': 'completed', 'action': {'sources': []}})
        tools = [{'type': 'web_search', 'filters': {'allowed_domains': ['gangnam.go.kr']}}]
        result = self.call([first, second], tools=tools, require_web_search=True,
                           include=['web_search_call.action.sources'])
        self.assertTrue(result['web_search_used'])
        self.assertEqual(self.requests[1]['tools'], tools)
        self.assertEqual(self.requests[1]['tool_choice'], 'required')

    def test_retry_cannot_pass_without_real_web_search(self):
        with self.assertRaises(OpenAIResponseError) as captured:
            self.call([response_payload(status='incomplete', reason='max_output_tokens'), response_payload()],
                      require_web_search=True)
        self.assertEqual(captured.exception.code, 'OPENAI_WEB_SEARCH_NOT_EXECUTED')
        self.assertEqual(captured.exception.usage['total_tokens'], 66)


class HybridTokenRecoveryTest(unittest.TestCase):
    """로컬 오류 뒤 OpenAI까지 실패한 경우도 누락 없이 추적합니다."""

    def test_fallback_failure_keeps_actual_cost_and_separate_local_budget(self):
        class IncompleteProvider(FakeProvider):
            async def generate(self, request):
                self.requests.append(request)
                raise LLMProviderError('OPENAI_INCOMPLETE_RESPONSE', 'test',
                                       usage={'total_tokens': 42}, attempts=[{'usage_reported': True}, {'usage_reported': False}])

        previous = list(_EVENTS)
        _EVENTS.clear()
        try:
            with TemporaryDirectory() as directory:
                router = router_fixture.LLMRouterTests().router(Path(directory))
                router.providers['qwen'] = FakeProvider('qwen', fails=True)
                router.providers['openai'] = IncompleteProvider('openai')
                request = replace(sample_request('transferability'), max_output_tokens=16000,
                                  local_max_output_tokens=7000, retry_max_output_tokens=24000)
                with self.assertRaises(LLMProviderError):
                    asyncio.run(router.generate(request))
                self.assertEqual(router.providers['qwen'].requests[0].max_output_tokens, 7000)
                self.assertEqual(router.providers['openai'].requests[0].max_output_tokens, 16000)
                trace = router.consume_trace()
                self.assertEqual(len(trace), 2)
                self.assertEqual(trace[-1]['error_code'], 'OPENAI_INCOMPLETE_RESPONSE')
                self.assertTrue(trace[-1]['fallback'])
                self.assertEqual(trace[-1]['retry_count'], 1)
                self.assertEqual(usage_summary()['total_tokens'], 42)
                self.assertEqual(usage_summary()['usage_unknown_attempts'], 1)
        finally:
            _EVENTS.clear()
            _EVENTS.extend(previous)

    def test_openai_provider_preserves_attempt_metadata(self):
        provider = OpenAIProvider(api_key='unit-test-placeholder', default_model='test')
        error = OpenAIResponseError('OPENAI_INCOMPLETE_RESPONSE', 'test',
                                    usage={'total_tokens': 99}, attempts=[{'attempt': 1}])
        with patch('ai_server.app.llm.openai_provider.create_structured_response', side_effect=error):
            with self.assertRaises(LLMProviderError) as captured:
                asyncio.run(provider.generate(sample_request('transferability')))
        self.assertEqual(captured.exception.usage['total_tokens'], 99)
        self.assertEqual(len(captured.exception.attempts), 1)

    def test_agents_use_larger_budgets_without_lowering_reasoning(self):
        class CaptureRouter:
            async def generate(self, request):
                self.request = request
                return {}

        router = CaptureRouter()
        asyncio.run(TransferabilityAgent(api_key='', model='test', llm_router=router).assess(
            evidence_pack={'benchmark_cases': [{'source_id': 'case:1'}]}))
        self.assertEqual((router.request.max_output_tokens, router.request.retry_max_output_tokens), (16000, 24000))
        self.assertEqual(router.request.reasoning_effort, 'medium')
        planner = PlannerAgent(api_key='', model='test', report_schema={}, llm_router=router)
        asyncio.run(planner.write({}))
        self.assertEqual((router.request.max_output_tokens, router.request.retry_max_output_tokens), (24000, 32000))
        self.assertEqual(router.request.reasoning_effort, 'high')
        asyncio.run(planner.write({}, revision_feedback={'overall_score': 70}, previous_draft={}))
        self.assertEqual((router.request.max_output_tokens, router.request.retry_max_output_tokens), (20000, 28000))
        asyncio.run(ReviewerAgent(api_key='', model='test', llm_router=router).review(evidence_pack={}, draft_report={}))
        self.assertEqual((router.request.max_output_tokens, router.request.retry_max_output_tokens), (12000, 20000))
        self.assertEqual(router.request.reasoning_effort, 'high')


if __name__ == '__main__':
    unittest.main()
