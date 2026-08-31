"""OpenAI Responses API를 일관된 오류 처리와 구조화 출력으로 호출합니다."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import quote

import httpx


class OpenAIResponseError(RuntimeError):
    """에이전트 단계에서 발생한 OpenAI 요청 오류입니다."""

    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


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
    if include:
        body['include'] = include

    try:
        # 고추론 보고서 모델의 재작성은 2분 이상 걸릴 수 있어 운영 환경에서 조정할 수 있게 합니다.
        timeout_seconds = max(30.0, float(os.getenv('AI_AGENT_TIMEOUT_SECONDS', '300')))
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                'https://api.openai.com/v1/responses',
                headers={'Authorization': f'Bearer {api_key}'},
                json=body,
            )
    except httpx.TimeoutException as exc:
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

    payload = response.json()
    if payload.get('status') != 'completed':
        reason = (payload.get('incomplete_details') or {}).get('reason')
        raise OpenAIResponseError(
            'OPENAI_INCOMPLETE_RESPONSE',
            f'AI 에이전트가 응답을 완료하지 못했습니다.{f" ({reason})" if reason else ""}',
        )

    try:
        return json.loads(output_text(payload))
    except json.JSONDecodeError as exc:
        raise OpenAIResponseError('OPENAI_INVALID_OUTPUT', 'AI 에이전트의 구조화 응답을 해석하지 못했습니다.') from exc
