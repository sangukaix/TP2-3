"""현재 AI Server 프로세스의 실제 LLM 실행 trace를 짧게 보관합니다."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any


_EVENTS: deque[dict[str, Any]] = deque(maxlen=120)


def record_trace(event: dict[str, Any]) -> None:
    """Provider 시도의 성공·실패 이벤트를 보관하며, 가짜 진행률이나 본문은 저장하지 않습니다."""
    _EVENTS.appendleft({'recorded_at': datetime.now(timezone.utc).isoformat(), **event})


def recent_trace(limit: int = 30) -> list[dict[str, Any]]:
    return list(_EVENTS)[:max(1, min(limit, 120))]


def usage_summary() -> dict[str, Any]:
    events = list(_EVENTS)
    total_tokens = sum(int((event.get('usage') or {}).get('total_tokens') or 0) for event in events)
    unknown_attempts = sum(1 for event in events for attempt in event.get('attempts', [])
                           if attempt.get('usage_reported') is False)
    return {'tracked_calls': len(events), 'total_tokens': total_tokens,
            'usage_unknown_attempts': unknown_attempts,
            'note': '현재 프로세스에서 API가 보고한 성공·실패·재시도 토큰 합계입니다. 사용량 미확인 호출은 포함되지 않아 실제 청구량과 다를 수 있습니다.'}
