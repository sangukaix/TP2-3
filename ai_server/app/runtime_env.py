"""프로젝트 .env와 실행 환경을 안전하게 합치는 작은 설정 도우미입니다.

빈 Windows 사용자 환경변수가 .env에 있는 LAN Ollama 주소를 덮어쓰면,
AI Server가 개인 노트북 모델을 찾지 못할 수 있습니다. 실제 값만 우선합니다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


def load_project_env(project_root: Path) -> dict[str, Any]:
    """`.env` 기본값에 비어 있지 않은 실행 환경값만 덮어씁니다."""
    values = {
        key: value
        for key, value in dotenv_values(project_root / '.env').items()
        if value is not None
    }
    for key, value in os.environ.items():
        # 명시적으로 값이 있는 환경변수는 CI·배포 환경을 위해 우선합니다.
        # 빈 값은 .env의 실제 설정을 지우지 않도록 무시합니다.
        if str(value).strip() or key not in values:
            values[key] = value
    return values
