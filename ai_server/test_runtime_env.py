"""로컬 Ollama 설정이 Windows 빈 환경변수 때문에 사라지지 않는지 확인합니다."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_server.app.runtime_env import load_project_env


class RuntimeEnvTests(unittest.TestCase):
    def test_blank_process_value_does_not_erase_dotenv_value(self) -> None:
        """개발 PC의 빈 환경변수보다 프로젝트 .env의 LAN URL을 우선합니다."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('LOCAL_LLM_BASE_URL=http://192.168.50.92:11434\n', encoding='utf-8')
            with patch.dict(os.environ, {'LOCAL_LLM_BASE_URL': ''}, clear=False):
                values = load_project_env(root)
        self.assertEqual(values['LOCAL_LLM_BASE_URL'], 'http://192.168.50.92:11434')

    def test_real_process_value_overrides_dotenv_value(self) -> None:
        """배포·CI처럼 실제 값이 지정된 경우에는 실행 환경을 우선합니다."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('LOCAL_LLM_BASE_URL=http://old-host:11434\n', encoding='utf-8')
            with patch.dict(os.environ, {'LOCAL_LLM_BASE_URL': 'http://new-host:11434'}, clear=False):
                values = load_project_env(root)
        self.assertEqual(values['LOCAL_LLM_BASE_URL'], 'http://new-host:11434')


if __name__ == '__main__':
    unittest.main()
