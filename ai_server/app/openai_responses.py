"""OpenAI Responses API를 일관된 오류 처리와 구조화 출력으로 호출합니다."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from time import perf_counter
from typing import Any
from urllib.parse import quote
from urllib.parse import urldefrag

import httpx
from jsonschema import Draft202012Validator, ValidationError


class OpenAIResponseError(RuntimeError):
    """에이전트 단계에서 발생한 OpenAI 요청 오류입니다."""

    def __init__(self, code: str, message: str, *, status_code: int = 502,
                 usage: dict[str, int] | None = None, attempts: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.usage = usage or {}
        self.attempts = attempts or []


LOGGER = logging.getLogger(__name__)


# 학습 페이지 3곳이 동시에 열려도 같은 상태 점검을 반복 호출하지 않도록 짧게 캐시합니다.
_READINESS_CACHE: dict[str, Any] = {'checked_at': 0.0, 'model': '', 'result': None}


async def check_openai_readiness(*, api_key: str, model: str) -> dict[str, str]:
    """키·선택 모델·네트워크 연결을 비용 없이 확인해 상태 배지에 사용합니다.

    실제 답변을 생성하지 않고 Models API만 조회하므로 토큰을 사용하지 않습니다.
    이후 실제 채팅 요청이 실패하면 프런트엔드가 즉시 Inactive로 전환합니다.
    """
    safe_key = str(api_key or '').strip()
    safe_model = str(model or '').strip()
    if not safe_key:
        return {'status': 'inactive', 'message': 'OpenAI API 키가 설정되지 않았습니다.'}
    now = asyncio.get_running_loop().time()
    cached = _READINESS_CACHE.get('result')
    if cached and _READINESS_CACHE.get('model') == safe_model and now - float(_READINESS_CACHE.get('checked_at', 0)) < 45:
        return cached
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(
                f'https://api.openai.com/v1/models/{quote(safe_model, safe="")}',
                headers={'Authorization': f'Bearer {safe_key}'},
            )
    except httpx.HTTPError:
        result = {'status': 'inactive', 'message': 'OpenAI API 서버에 연결하지 못했습니다.'}
    else:
        if 200 <= response.status_code < 300:
            result = {'status': 'active', 'message': 'AI Server와 OpenAI 모델 연결을 확인했습니다.'}
        elif response.status_code == 401:
            result = {'status': 'inactive', 'message': 'OpenAI API 키 인증에 실패했습니다.'}
        elif response.status_code == 429:
            result = {'status': 'inactive', 'message': 'OpenAI 요청 한도 또는 결제 상태를 확인해 주세요.'}
        else:
            result = {'status': 'inactive', 'message': '선택한 OpenAI 모델을 사용할 수 없습니다.'}
    _READINESS_CACHE.update({'checked_at': now, 'model': safe_model, 'result': result})
    return result


def output_text(payload: dict[str, Any]) -> str:
    """Responses API 출력 배열에서 최종 텍스트를 안전하게 찾습니다."""
    for item in payload.get('output') or []:
        for content in item.get('content') or []:
            if content.get('type') == 'output_text' and content.get('text'):
                return str(content['text'])
    raise OpenAIResponseError('OPENAI_OUTPUT_MISSING', 'OpenAI 응답에서 구조화 출력 텍스트를 찾지 못했습니다.')


def _source_urls(value: Any, *, key_names: tuple[str, ...] = ('source_url',)) -> set[str]:
    """본문 지시문이 아니라 구조화된 출처 필드의 URL만 수집합니다."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in key_names and isinstance(item, str) and item.startswith(('https://', 'http://')):
                found.add(urldefrag(item)[0].rstrip('/'))
            elif isinstance(item, (dict, list)):
                found.update(_source_urls(item, key_names=key_names))
    elif isinstance(value, list):
        for item in value:
            found.update(_source_urls(item, key_names=key_names))
    return found


def _verify_web_grounding(payload: dict[str, Any], data: dict[str, Any], input_payload: dict[str, Any]) -> bool:
    """도구가 실제 실행됐는지와 반환 출처가 조회 기록/검수 입력에 있는지를 확인합니다.

    URL 확인은 주장의 사실성 보장과 다릅니다. 본문·수치 타당성은 별도 Reviewer가 검수합니다.
    """
    calls = [item for item in payload.get('output') or []
             if item.get('type') == 'web_search_call' and item.get('status') == 'completed']
    if not calls:
        raise OpenAIResponseError('OPENAI_WEB_SEARCH_NOT_EXECUTED', '필수 공식 웹 검색이 실제 수행되지 않았습니다.')
    consulted = _source_urls(calls, key_names=('url',))
    consulted.update(_source_urls(payload.get('output') or [], key_names=('url',)))
    # 사용자가 첨부한 임의 URL은 검수 입력으로 승격하지 않습니다.
    trusted_input = {key: input_payload.get(key) for key in ('curated_case_cards', 'case_rag_candidates')}
    known = consulted | _source_urls(trusted_input)
    if _source_urls(data) - known:
        raise OpenAIResponseError('OPENAI_UNVERIFIED_WEB_SOURCE', '검색 기록에 없는 출처가 반환되어 조사 결과를 채택하지 않았습니다.')
    return True


async def create_structured_response(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_payload: dict[str, Any],
    schema_name: str,
    schema: dict[str, Any],
    reasoning_effort: str = 'medium',
    max_output_tokens: int = 8000,
    verbosity: str = 'medium',
    tools: list[dict[str, Any]] | None = None,
    include: list[str] | None = None,
    return_metadata: bool = False,
    require_web_search: bool = False,
    retry_max_output_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """JSON Schema를 강제한 Responses API 호출 결과를 dict로 반환합니다."""
    body: dict[str, Any] = {
        'model': model,
        'store': False,
        'max_output_tokens': max_output_tokens,
        'reasoning': {'effort': reasoning_effort},
        'instructions': instructions,
        'input': json.dumps(input_payload, ensure_ascii=False),
        'text': {
            # 보고서와 학습 챗봇은 필요한 설명 길이가 다르므로 호출자가 조절합니다.
            'verbosity': verbosity,
            'format': {
                'type': 'json_schema',
                'name': schema_name,
                'strict': True,
                'schema': schema,
            },
        },
    }
    if tools:
        body['tools'] = tools
        body['max_tool_calls'] = 6
    if require_web_search:
        body['tool_choice'] = 'required'
    if include:
        body['include'] = include

    # 동일 단계만 처음부터 다시 생성하며, 잘린 JSON을 이어 붙이거나 근거를 삭제하지 않습니다.
    # 재시도는 명시적으로 허용한 더 큰 상한으로 딱 한 번입니다. 챗봇은 기존 단일 호출을 유지합니다.
    limits = [max_output_tokens]
    if retry_max_output_tokens is not None and retry_max_output_tokens > max_output_tokens:
        limits.append(retry_max_output_tokens)
    attempts: list[dict[str, Any]] = []
    total_usage: dict[str, int] = {}
    for index, limit in enumerate(limits):
        body['max_output_tokens'] = limit
        started = perf_counter()
        try:
            payload = await _post_response(api_key, body, timeout_seconds)
        except OpenAIResponseError as exc:
            attempts.append({'attempt': index + 1, 'max_output_tokens': limit, 'status': 'failed',
                             'reason': exc.code, 'usage': {}, 'usage_reported': False,
                             'duration_ms': round((perf_counter() - started) * 1000)})
            exc.usage, exc.attempts = total_usage, attempts
            raise
        usage = _response_usage(payload)
        for key, value in usage.items():
            total_usage[key] = total_usage.get(key, 0) + value
        reason = (payload.get('incomplete_details') or {}).get('reason')
        attempts.append({'attempt': index + 1, 'max_output_tokens': limit,
                         'status': payload.get('status'), 'reason': reason,
                         'usage': usage, 'usage_reported': bool(payload.get('usage')),
                         'duration_ms': round((perf_counter() - started) * 1000)})
        if payload.get('status') == 'completed':
            break
        if payload.get('status') == 'incomplete' and reason == 'max_output_tokens' and index + 1 < len(limits):
            LOGGER.warning('OpenAI token retry: schema=%s model=%s limit=%s next_limit=%s',
                           schema_name, model, limit, limits[index + 1])
            continue
        # 인증·결제·콘텐츠 필터·통신 오류는 상한을 늘려도 해결되지 않아 자동 반복하지 않습니다.
        retry_note = ' 토큰 상한을 늘린 1회 재시도 후에도 완료되지 않았습니다.' if index else ''
        raise OpenAIResponseError('OPENAI_INCOMPLETE_RESPONSE',
                                 f'AI 에이전트가 응답을 완료하지 못했습니다. ({reason or "unknown"}){retry_note}',
                                 usage=total_usage, attempts=attempts)

    try:
        data = json.loads(output_text(payload))
    except json.JSONDecodeError as exc:
        raise OpenAIResponseError('OPENAI_INVALID_OUTPUT', 'AI 에이전트의 구조화 응답을 해석하지 못했습니다.',
                                 usage=total_usage, attempts=attempts) from exc
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as exc:
        raise OpenAIResponseError('OPENAI_SCHEMA_VALIDATION_FAILED', 'AI 응답이 Agent JSON 계약을 충족하지 않습니다.',
                                 usage=total_usage, attempts=attempts) from exc
    if not isinstance(data, dict):
        raise OpenAIResponseError('OPENAI_INVALID_OUTPUT', 'AI 에이전트가 JSON 객체를 반환하지 않았습니다.',
                                 usage=total_usage, attempts=attempts)
    web_search_used = any(item.get('type') == 'web_search_call' and item.get('status') == 'completed'
                          for item in payload.get('output') or [])
    if require_web_search:
        try:
            web_search_used = _verify_web_grounding(payload, data, input_payload)
        except OpenAIResponseError as exc:
            exc.usage, exc.attempts = total_usage, attempts
            raise
    if return_metadata:
        # 재시도 전후를 합산합니다. reasoning_tokens는 output_tokens에 포함되므로 총합에 다시 더하지 않습니다.
        return {'data': data, 'response_id': payload.get('id'), 'usage': total_usage,
                'web_search_used': web_search_used, 'attempts': attempts}
    return data


def _response_usage(payload: dict[str, Any]) -> dict[str, int]:
    """성공/미완료 모두 API가 보고한 사용량만 읽습니다. 누락값을 실제 0토큰으로 단정하지 않습니다."""
    raw = payload.get('usage') or {}
    usage = {key: int(raw[key]) for key in ('input_tokens', 'output_tokens', 'total_tokens') if raw.get(key) is not None}
    for details, key in (('input_tokens_details', 'cached_tokens'), ('output_tokens_details', 'reasoning_tokens')):
        value = (raw.get(details) or {}).get(key)
        if value is not None:
            usage[key] = int(value)
    return usage


async def _post_response(api_key: str, body: dict[str, Any], timeout_seconds: float | None) -> dict[str, Any]:
    """HTTP 한 번만 수행합니다. 재시도 판단은 상위 함수에 모아 숨은 중복 호출을 방지합니다."""
    timeout = max(30.0, float(timeout_seconds if timeout_seconds is not None else os.getenv('AI_AGENT_TIMEOUT_SECONDS', '300')))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # HTTP 소켓별 timeout뿐 아니라 요청 전체에도 마감 시간을 둡니다.
            response = await asyncio.wait_for(
                client.post('https://api.openai.com/v1/responses',
                            headers={'Authorization': f'Bearer {api_key}'}, json=body),
                timeout=timeout,
            )
    except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
        raise OpenAIResponseError('OPENAI_TIMEOUT', 'AI 에이전트 처리 시간이 초과되었습니다.', status_code=504) from exc
    except httpx.HTTPError as exc:
        raise OpenAIResponseError('OPENAI_CONNECTION_ERROR', 'OpenAI API 서버에 연결하지 못했습니다.') from exc
    if response.status_code == 401:
        raise OpenAIResponseError('OPENAI_AUTH_ERROR', 'AI 서버의 OpenAI API 키 인증에 실패했습니다.', status_code=503)
    if response.status_code >= 400:
        error_payload = response.json().get('error', {}) if response.headers.get('content-type', '').startswith('application/json') else {}
        raise OpenAIResponseError(
            'OPENAI_MODEL_OR_REQUEST_ERROR' if response.status_code in (400, 404) else 'OPENAI_RESPONSE_ERROR',
            str(error_payload.get('message') or 'OpenAI가 에이전트 요청을 처리하지 못했습니다.'),
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenAIResponseError('OPENAI_INVALID_OUTPUT', 'OpenAI 응답 JSON을 해석하지 못했습니다.') from exc
    if not isinstance(payload, dict):
        raise OpenAIResponseError('OPENAI_INVALID_OUTPUT', 'OpenAI 응답 형식이 올바르지 않습니다.')
    return payload
