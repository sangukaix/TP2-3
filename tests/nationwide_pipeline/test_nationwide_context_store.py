"""전국 비교 출처 JSON 파싱의 안전 경로를 검증한다."""

from __future__ import annotations

import unittest

from ai_server.app.nationwide_context_store import _source_ids


class NationwideContextStoreTest(unittest.TestCase):
    """잘못된 DB JSON이 AI 보고서 생성을 중단시키지 않는지 확인합니다."""

    def test_invalid_source_json_returns_empty_list(self) -> None:
        self.assertEqual(_source_ids("not-json"), [])
        self.assertEqual(_source_ids(["dataset:1", ""]), ["dataset:1"])

