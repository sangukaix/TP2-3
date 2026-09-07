"""기존 Responses API 헬퍼를 Provider 인터페이스로 감쌉니다."""

from __future__ import annotations

from ..openai_responses import OpenAIResponseError, check_openai_readiness, create_structured_response
from .errors import LLMProviderError
from .models import LLMRequest, LLMResult, ProviderHealth


class OpenAIProvider:
    """OpenAI 구조화 출력과 Web Search를 담당하는 원격 Provider입니다."""

    name = 'openai'
    capabilities = ('structured_output', 'reasoning', 'web_search')

    def __init__(self, *, api_key: str, default_model: str) -> None:
        self.api_key = str(api_key or '').strip()
        self.default_model = str(default_model or '').strip()

    async def generate(self, request: LLMRequest) -> LLMResult:
        if not self.api_key:
            raise LLMProviderError('OPENAI_KEY_MISSING', 'OpenAI API 키가 설정되지 않았습니다.', status_code=503)
        model = str(request.model or self.default_model).strip()
        try:
            result = await create_structured_response(
                api_key=self.api_key, model=model, instructions=request.instructions,
                input_payload=request.input_payload, schema_name=request.schema_name,
                schema=request.schema, reasoning_effort=request.reasoning_effort,
                max_output_tokens=request.max_output_tokens, verbosity=request.verbosity,
                tools=request.tools, include=request.include, return_metadata=True,
                require_web_search=request.requires_web_search,
                retry_max_output_tokens=request.retry_max_output_tokens,
                timeout_seconds=request.openai_timeout_seconds,
            )
        except OpenAIResponseError as exc:
            raise LLMProviderError(exc.code, exc.message, status_code=exc.status_code,
                                   usage=exc.usage, attempts=exc.attempts) from exc
        return LLMResult(
            payload=result['data'], provider=self.name, model=model, duration_ms=0,
            usage=result.get('usage') or {}, web_search_used=bool(result.get('web_search_used')),
            attempts=result.get('attempts') or [],
        )

    async def health(self) -> ProviderHealth:
        result = await check_openai_readiness(api_key=self.api_key, model=self.default_model)
        return ProviderHealth(
            provider=self.name, status=result['status'], message=result['message'],
            models=[self.default_model] if self.default_model else [], capabilities=list(self.capabilities),
        )
