"""공통 LLM Provider 오류 타입입니다."""

from __future__ import annotations

from typing import Any


class LLMProviderError(RuntimeError):
    """모델 연결·출력·능력 부족을 구분하기 위한 오류입니다."""

    def __init__(self, code: str, message: str, *, status_code: int = 502,
                 usage: dict[str, int] | None = None, attempts: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        # 실패한 응답도 과금될 수 있으므로 API가 알려준 사용량을 버리지 않습니다.
        self.usage = usage or {}
        self.attempts = attempts or []
