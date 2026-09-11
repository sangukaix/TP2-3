"""LAN의 Ollama /api/chat을 구조화 출력 Provider로 사용합니다."""

from __future__ import annotations

import json
import math
from time import perf_counter
from typing import Any

import httpx
from jsonschema import Draft202012Validator, ValidationError

from .errors import LLMProviderError
from .models import LLMRequest, LLMResult, ProviderHealth


class OllamaProvider:
    """Qwen·Gemma 등 로컬 모델을 실행하며 Web Search는 제공하지 않습니다."""

    name = 'ollama'
    capabilities = ('structured_output', 'local_inference', 'read_only_evidence_tools')

    def __init__(self, *, base_url: str, default_model: str, timeout_seconds: float = 180,
                 context_length: int = 40960) -> None:
        self.base_url = str(base_url or '').rstrip('/')
        self.default_model = str(default_model or '').strip()
        self.timeout_seconds = max(15.0, float(timeout_seconds))
        self.context_length = max(4096, int(context_length))

    async def _chat(self, *, model: str, messages: list[dict[str, Any]], schema: dict | None,
                    max_output_tokens: int, tools: list[dict] | None = None,
                    think: bool | None = None) -> tuple[dict, dict[str, int]]:
        """Ollama 네이티브 함수 호출과 최종 JSON을 별도 요청으로 처리합니다."""
        if not self.base_url:
            raise LLMProviderError('OLLAMA_URL_MISSING', '로컬 LLM 주소가 설정되지 않았습니다.', status_code=503)
        body = {
            'model': model,
            'messages': messages,
            'stream': False,
            # Qwen/Gemma가 각 Agent 호출 사이에 모델을 다시 올리지 않게 해 LAN GPU의
            # 첫 응답 지연을 줄입니다. 개인 노트북을 끄면 이 값도 자동으로 사라집니다.
            'keep_alive': '15m',
            'options': {'temperature': 0.15, 'num_predict': max_output_tokens, 'num_ctx': self.context_length},
        }
        if schema is not None:
            body['format'] = schema
        if tools:
            body['tools'] = tools
        if think is not None:
            body['think'] = think
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f'{self.base_url}/api/chat', json=body)
        except httpx.TimeoutException as exc:
            raise LLMProviderError('OLLAMA_TIMEOUT', '로컬 LLM 응답 시간이 초과되었습니다.', status_code=504) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError('OLLAMA_CONNECTION_ERROR', '로컬 Ollama 서버에 연결하지 못했습니다.', status_code=503) from exc
        if response.status_code >= 400:
            # 원격 GPU 쪽의 모델명·요청 형식 오류를 단순 "승인 실패"처럼 보이지 않게
            # 짧은 서버 오류만 전달합니다. 요청 본문·환경변수·개인 IP는 포함하지 않습니다.
            try:
                detail = str((response.json() or {}).get('error') or '').strip()
            except ValueError:
                detail = ''
            suffix = f' {detail[:180]}' if detail else ''
            raise LLMProviderError('OLLAMA_REQUEST_ERROR', f'Ollama 요청이 실패했습니다. ({response.status_code}){suffix}')
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMProviderError('OLLAMA_INVALID_RESPONSE', 'Ollama 응답 JSON을 해석하지 못했습니다.') from exc
        if not isinstance(payload, dict) or not isinstance(payload.get('message'), dict):
            raise LLMProviderError('OLLAMA_INVALID_RESPONSE', 'Ollama 응답 형식이 올바르지 않습니다.')
        usage = {'input_tokens': int(payload.get('prompt_eval_count') or 0),
                 'output_tokens': int(payload.get('eval_count') or 0)}
        usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
        if payload.get('done') is not True or payload.get('done_reason') == 'length':
            # 잘린 JSON이 우연히 파싱돼도 미완료 기획안을 정상 결과로 취급하지 않습니다.
            raise LLMProviderError('OLLAMA_INCOMPLETE_RESPONSE', '로컬 LLM이 출력 한도 내에 응답을 완료하지 못했습니다.', usage=usage)
        message = payload['message']
        if not message.get('content') and not (tools and message.get('tool_calls')):
            raise LLMProviderError('OLLAMA_OUTPUT_MISSING', 'Ollama 응답에 내용이 없습니다.', usage=usage)
        return message, usage

    async def _call(self, *, model: str, messages: list[dict[str, Any]], schema: dict,
                    max_output_tokens: int) -> tuple[str, dict[str, int]]:
        message, usage = await self._chat(model=model, messages=messages, schema=schema,
                                           max_output_tokens=max_output_tokens, think=False)
        return str(message.get('content') or '').strip(), usage

    @staticmethod
    def _estimated_context_tokens(value: Any) -> int:
        """한국어·영문이 섞인 JSON의 보수적 토큰 상한을 계산합니다.

        이전에는 UTF-8 바이트 한 개를 토큰 한 개로 보아 한글 한 글자를 세 토큰으로
        계산했습니다. Qwen/Gemma의 실제 prompt_eval_count보다 지나치게 크게 잡혀,
        40k 문맥에 충분히 들어가는 근거 묶음까지 실행 전에 차단하는 문제가 있었습니다.
        여기서는 비ASCII 문자는 1.5토큰, ASCII 문자는 3.2문자당 1토큰으로 넉넉히
        추정하고 채팅·스키마 여유를 별도로 더합니다. 이 값은 원문을 줄이지 않습니다.
        """
        serialized = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        non_ascii = sum(ord(character) > 127 for character in serialized)
        ascii_count = len(serialized) - non_ascii
        return math.ceil(non_ascii * 1.5 + ascii_count / 3.2) + 1024

    def _check_context(self, messages: list[dict[str, Any]], schema: dict, output_limit: int,
                       measured_prefix: tuple[list[dict], int] | None = None) -> None:
        """원문을 보존하면서 실제 모델 문맥보다 먼저 멈추지 않도록 입력 예산을 확인합니다."""
        input_budget = self._estimated_context_tokens({'messages': messages, 'schema': schema})
        # 같은 모델이 직전 요청에서 실제 계수한 입력 토큰이 있으면 그 동일 접두부만 재사용합니다.
        # 새 도구 결과·스키마는 여전히 바이트 상한으로 계산합니다. 출력 예산을 줄이거나
        # 한국어 바이트/토큰 비율을 추정하지 않으며, 누락·접두부 불일치는 기존 검사로 돌아갑니다.
        if measured_prefix:
            prefix, tokens = measured_prefix
            if prefix and isinstance(tokens, int) and 0 < tokens < self.context_length and messages[:len(prefix)] == prefix:
                # Ollama가 직전 호출에서 알려 준 실제 입력 토큰을 기준으로 삼고, 이후에
                # 붙은 도구 결과·스키마만 같은 한국어 추정식으로 더합니다.
                added = {'messages': messages[len(prefix):], 'schema': schema}
                input_budget = tokens + self._estimated_context_tokens(added)
        if input_budget + output_limit > self.context_length:
            raise LLMProviderError('OLLAMA_CONTEXT_BUDGET_EXCEEDED',
                                   '근거 전체와 출력의 안전한 문맥 예산이 로컬 한도를 넘습니다. 근거를 자르지 않습니다.')

    async def generate(self, request: LLMRequest) -> LLMResult:
        if request.requires_web_search or request.tools:
            raise LLMProviderError('CAPABILITY_WEB_SEARCH_REQUIRED', '이 작업은 OpenAI Web Search가 필요합니다.', status_code=409)
        model = str(request.model or self.default_model).strip()
        if not model:
            raise LLMProviderError('OLLAMA_MODEL_MISSING', '로컬 LLM 모델이 설정되지 않았습니다.', status_code=503)
        if request.local_evidence_tools:
            from .local_agent import run_local_agent
            from .local_prompts import LOCAL_ROLES
            if request.task not in LOCAL_ROLES:
                raise LLMProviderError('LOCAL_TASK_NOT_SUPPORTED', '로컬 근거 도구를 지원하지 않는 작업입니다.')
            return await run_local_agent(self, request, model)
        messages = [
            {'role': 'system', 'content': request.instructions},
            {'role': 'user', 'content': json.dumps(request.input_payload, ensure_ascii=False)},
        ]
        started = perf_counter()
        def parse_and_validate(value: str) -> dict:
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError('JSON object required')
            Draft202012Validator(request.schema).validate(parsed)
            return parsed

        self._check_context(messages, request.schema, request.max_output_tokens)
        content, usage = await self._call(model=model, messages=messages, schema=request.schema,
                                          max_output_tokens=request.max_output_tokens)
        try:
            parsed = parse_and_validate(content)
        except (json.JSONDecodeError, ValidationError, ValueError):
            # JSON 파싱과 Schema 검증 모두 실패 시 한 번만 교정해 무한 재시도를 막습니다.
            repair_messages = messages + [{'role': 'user', 'content': '설명 없이 지정 JSON Schema에 맞는 JSON 객체만 반환하세요.'}]
            self._check_context(repair_messages, request.schema, request.max_output_tokens)
            content, repair_usage = await self._call(
                model=model,
                messages=repair_messages,
                schema=request.schema,
                max_output_tokens=request.max_output_tokens,
            )
            usage = {key: usage.get(key, 0) + repair_usage.get(key, 0) for key in set(usage) | set(repair_usage)}
            try:
                parsed = parse_and_validate(content)
            except json.JSONDecodeError as exc:
                raise LLMProviderError('OLLAMA_INVALID_JSON', '로컬 LLM이 유효한 JSON을 반환하지 않았습니다.') from exc
            except (ValidationError, ValueError) as exc:
                # 보고서 최종 결과는 FastAPI/Pydantic 모델도 다시 검증합니다. 이 단계는 Agent 계약을 먼저 지킵니다.
                raise LLMProviderError('OLLAMA_SCHEMA_VALIDATION_FAILED', '로컬 LLM 응답이 Agent JSON 계약을 충족하지 않습니다.') from exc
        return LLMResult(payload=parsed, provider=self.name, model=model,
                         usage=usage, duration_ms=round((perf_counter() - started) * 1000))

    async def health(self) -> ProviderHealth:
        if not self.base_url:
            return ProviderHealth(self.name, 'inactive', '로컬 LLM 주소가 설정되지 않았습니다.', [], list(self.capabilities))
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f'{self.base_url}/api/tags')
            if response.status_code >= 400:
                return ProviderHealth(self.name, 'inactive', 'Ollama 모델 목록을 읽지 못했습니다.', [], list(self.capabilities))
            models = [str(item.get('name') or '') for item in (response.json().get('models') or []) if item.get('name')]
            selected = [item for item in models if item == self.default_model]
            return ProviderHealth(self.name, 'active' if selected else 'inactive',
                                  'Ollama 서버와 모델 연결을 확인했습니다.' if selected else 'Ollama 서버는 연결됐지만 선택 모델이 없습니다.',
                                  models, list(self.capabilities))
        except (httpx.HTTPError, ValueError):
            return ProviderHealth(self.name, 'inactive', 'Ollama 서버에 연결하지 못했습니다.', [], list(self.capabilities))
