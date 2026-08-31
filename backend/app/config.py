"""서버 전용 환경변수 로딩 모듈입니다. 비밀 값 자체를 로그에 출력하지 않습니다."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import dotenv_values


# backend/app/config.py → backend → 프로젝트 루트 순으로 올라가 루트 .env를 읽습니다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / '.env'


@dataclass(frozen=True)
class Settings:
    """Backend가 사용하는 서버 전용 설정입니다. 비밀 값은 React로 전달하지 않습니다."""

    vworld_api_key: str
    vworld_wfs_base_url: str
    vworld_domain: str


def get_settings() -> Settings:
    """환경변수 우선, 없으면 프로젝트 루트 .env 순서로 읽습니다."""
    values = dotenv_values(ENV_PATH)
    def setting(name: str, default: str = '') -> str:
        return str(os.getenv(name) or values.get(name) or default).strip()
    return Settings(
        vworld_api_key=setting('VWORLD_API_KEY'),
        vworld_wfs_base_url=setting('VWORLD_WFS_BASE_URL', 'https://api.vworld.kr/req/wfs'),
        # VWorld 개발 키에서 localhost를 허용 도메인으로 등록한 경우를 기본값으로 둡니다.
        vworld_domain=setting('VWORLD_ALLOWED_DOMAIN', 'localhost'),
    )
