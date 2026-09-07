"""Provider 공통 요청·결과·상태 모델입니다.

에이전트는 OpenAI/Ollama의 HTTP 형식을 직접 알지 않고 이 모델만 사용합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMRequest:
    """구조화 출력 한 번을 실행하기 위한 공통 입력입니다."""

    task: str
    instructions: str
    input_payload: dict[str, Any]
    schema_name: str
    schema: dict[str, Any]
    model: str | None = None
    reasoning_effort: str = 'medium'
    max_output_tokens: int = 8000
    verbosity: str = 'medium'
    tools: list[dict[str, Any]] | None = None
    include: list[str] | None = None
    requires_web_search: bool = False
    report_id: str | None = None
    agent: str | None = None
    # 토큰 부족일 때만 OpenAI를 한 번 더 호출합니다. None이면 자동 재시도하지 않습니다.
    retry_max_output_tokens: int | None = None
    openai_timeout_seconds: float | None = None
    # 클라우드 출력 예산 확대로 개인 GPU의 입력 문맥 여유가 줄지 않게 분리합니다.
    local_max_output_tokens: int | None = None
    # 승인된 기획 단계만 요청별 읽기 전용 근거 도구를 사용합니다. 웹검색 권한과 다릅니다.
    local_evidence_tools: bool = False


@dataclass
class LLMResult:
    """Provider 실행 결과와 운영 추적 정보를 함께 보관합니다."""

    payload: dict[str, Any]
    provider: str
    model: str
    duration_ms: int
    usage: dict[str, int] = field(default_factory=dict)
    requested_provider: str = ''
    fallback: bool = False
    fallback_reason: str = ''
    web_search_used: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    input_preparation: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderHealth:
    """프런트 관리자 화면에 보여줄 비밀정보 없는 상태입니다."""

    provider: str
    status: str
    message: str
    models: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            'provider': self.provider,
            'status': self.status,
            'message': self.message,
            'models': self.models,
            'capabilities': self.capabilities,
        }
