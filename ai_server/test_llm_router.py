"""Hybrid Router의 capability 잠금·로컬 폴백을 네트워크 없이 검증합니다."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.models import LLMRequest, LLMResult, ProviderHealth
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.llm.router import LLMRouter


class FakeProvider:
    def __init__(self, name: str, *, fails: bool = False) -> None:
        self.name, self.fails, self.requests = name, fails, []
        self.default_model = f'{name}-default'

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        if self.fails:
            raise LLMProviderError(f'{self.name.upper()}_DOWN', '테스트 연결 실패')
        return LLMResult(payload={'provider': self.name}, provider=self.name, model=request.model or self.default_model, duration_ms=1)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, 'active', 'ok', [self.default_model], [])


def sample_request(task: str, *, web: bool = False) -> LLMRequest:
    return LLMRequest(task=task, instructions='test', input_payload={}, schema_name='test',
                      schema={'type': 'object'}, requires_web_search=web)


class LLMRouterTests(unittest.TestCase):
    def router(self, root: Path) -> LLMRouter:
        router = LLMRouter(project_root=root, env_values={'LLM_MODE': 'hybrid', 'OPENAI_MODEL': 'gpt-test'})
        router.providers = {'openai': FakeProvider('openai'), 'qwen': FakeProvider('qwen'), 'gemma': FakeProvider('gemma')}
        return router

    def test_web_search_task_is_locked_to_openai(self) -> None:
        with TemporaryDirectory() as directory:
            router = self.router(Path(directory))
            result = asyncio.run(router.generate(sample_request('evidence', web=True)))
            self.assertEqual(result['provider'], 'openai')
            self.assertEqual(len(router.providers['qwen'].requests), 0)

    def test_local_failure_falls_back_to_openai(self) -> None:
        with TemporaryDirectory() as directory:
            router = self.router(Path(directory))
            router.providers['qwen'] = FakeProvider('qwen', fails=True)
            result = asyncio.run(router.generate(sample_request('transferability')))
            self.assertEqual(result['provider'], 'openai')
            trace = router.consume_trace()[-1]
            self.assertTrue(trace['fallback'])
            self.assertEqual(trace['fallback_reason'], 'QWEN_DOWN')

    def test_openai_only_overrides_local_route(self) -> None:
        with TemporaryDirectory() as directory:
            router = self.router(Path(directory))
            router.config['mode'] = 'openai_only'
            result = asyncio.run(router.generate(sample_request('planner')))
            self.assertEqual(result['provider'], 'openai')

    def test_local_only_refuses_web_search(self) -> None:
        with TemporaryDirectory() as directory:
            router = self.router(Path(directory))
            router.config['mode'] = 'local_only'
            with self.assertRaisesRegex(LLMProviderError, 'local_only'):
                asyncio.run(router.generate(sample_request('evidence', web=True)))

    def test_local_only_moves_non_search_reviewer_to_qwen(self) -> None:
        with TemporaryDirectory() as directory:
            router = self.router(Path(directory))
            router.config['mode'] = 'local_only'
            result = asyncio.run(router.generate(sample_request('reviewer')))
            self.assertEqual(result['provider'], 'qwen')

    def test_status_labels_qwen_and_gemma_separately(self) -> None:
        """같은 Ollama backend라도 화면에서는 역할별 카드가 분리되어야 합니다."""
        with TemporaryDirectory() as directory:
            router = self.router(Path(directory))
            status = asyncio.run(router.status())
            providers = {row['role']: row for row in status['providers']}
            self.assertEqual(set(providers), {'openai', 'qwen', 'gemma'})
            self.assertEqual(providers['qwen']['backend'], 'qwen')
            self.assertEqual(providers['gemma']['backend'], 'gemma')


class OllamaStructuredOutputTests(unittest.TestCase):
    def test_korean_context_estimate_does_not_treat_each_utf8_byte_as_a_token(self) -> None:
        """한글 근거 원문은 보존하되, UTF-8 3바이트를 3토큰으로 오인하지 않습니다."""
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test', context_length=40960)
        messages = [{'role': 'user', 'content': '관광근거' * 3000}]
        # 이전 바이트 방식은 36,000바이트 + 7,000 출력으로 실행 전 차단했지만,
        # 실제 한국어 tokenizer에 맞춘 보수 추정에서는 문맥 안에 들어갑니다.
        provider._check_context(messages, {'type': 'object'}, 7000)

    def test_genuinely_oversized_korean_context_is_still_blocked(self) -> None:
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test', context_length=40960)
        messages = [{'role': 'user', 'content': '관광근거' * 10000}]
        with self.assertRaisesRegex(LLMProviderError, '문맥 예산'):
            provider._check_context(messages, {'type': 'object'}, 7000)

    def test_invalid_json_is_retried_once(self) -> None:
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test')
        outputs = iter(['설명 문장', '{"answer":"ok"}'])

        async def fake_call(**_kwargs: object) -> tuple:
            return next(outputs), {'input_tokens': 10, 'output_tokens': 4, 'total_tokens': 14}

        provider._call = fake_call  # type: ignore[method-assign]
        result = asyncio.run(provider.generate(sample_request('chat_explain')))
        self.assertEqual(result.payload, {'answer': 'ok'})

    def test_web_search_is_not_sent_to_ollama(self) -> None:
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test')
        with self.assertRaisesRegex(LLMProviderError, 'Web Search'):
            asyncio.run(provider.generate(sample_request('evidence', web=True)))

    def test_schema_failure_is_retried_once(self) -> None:
        provider = OllamaProvider(base_url='http://example.invalid', default_model='qwen-test')
        outputs = iter(['{"wrong":true}', '{"answer":"ok"}'])

        async def fake_call(**_kwargs: object) -> tuple:
            return next(outputs), {'input_tokens': 10, 'output_tokens': 4, 'total_tokens': 14}

        provider._call = fake_call  # type: ignore[method-assign]
        request = LLMRequest(task='chat_explain', instructions='test', input_payload={}, schema_name='test',
                             schema={'type': 'object', 'properties': {'answer': {'type': 'string'}}, 'required': ['answer']})
        self.assertEqual(asyncio.run(provider.generate(request)).payload, {'answer': 'ok'})


if __name__ == '__main__':
    unittest.main()
