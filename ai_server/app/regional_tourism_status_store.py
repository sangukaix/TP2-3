"""지역별 관광 현황의 작은 기획 근거 context를 안전하게 읽는다.

AI Server는 바깥 ZIP이나 50만 행 인기장소 원본을 요청마다 열지 않는다. 오프라인
검증 과정에서 생성한 지역별 사실표만 mtime 기반 캐시로 읽고, 파일이 없으면 기존
대시보드·기획안 흐름을 그대로 유지한다.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_PATH = PROJECT_ROOT / "data" / "processed" / "regional_tourism_status" / "context_by_region.json"
_LOCK = RLock()
_CACHE_FINGERPRINT: tuple[int, int] | None = None
_CACHE: dict[str, Any] | None = None


def _load_context(path: Path = CONTEXT_PATH) -> dict[str, Any]:
    """내용이 갱신된 경우에만 파일을 다시 읽고, 깨진 context는 호출자에게 전달하지 않는다."""

    global _CACHE_FINGERPRINT, _CACHE
    if not path.is_file():
        return {}
    stat = path.stat()
    fingerprint = (stat.st_mtime_ns, stat.st_size)
    with _LOCK:
        if _CACHE is not None and _CACHE_FINGERPRINT == fingerprint:
            return _CACHE
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(parsed, dict) or not isinstance(parsed.get("regions"), dict):
            return {}
        _CACHE, _CACHE_FINGERPRINT = parsed, fingerprint
        return parsed


def load_regional_tourism_status(region_code: str, *, context_path: Path = CONTEXT_PATH) -> dict[str, Any] | None:
    """선택 지역의 유입·핫플레이스·집중률 보조 근거만 반환한다.

    이 반환값에는 원본 raw 행·파일 경로·비밀값이 없고, 반드시 ML과 다른 관측 보조
    근거라는 한계를 포함한다.
    """

    record = _load_context(context_path).get("regions", {}).get(str(region_code))
    return deepcopy(record) if isinstance(record, dict) else None
