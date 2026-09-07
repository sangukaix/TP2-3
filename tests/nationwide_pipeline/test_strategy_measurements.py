"""기획안 사후 측정은 실제 기준값만 저장하는지 단위 검증한다."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_server.app.strategy_store import save_strategy_measurement_baseline


class _FakeCursor:
    """DB 없이 executemany 입력값만 확인하는 최소 가짜 cursor입니다."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def executemany(self, _sql: str, rows: list[dict[str, object]]) -> None:
        self.rows.extend(rows)


class _FakeConnection:
    """실제 MySQL 연결 없이 저장 함수의 데이터 계약을 확인합니다."""

    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance


class StrategyMeasurementBaselineTest(unittest.TestCase):
    """LLM 문장 대신 snapshot의 실제 관측값만 baseline으로 쓰는지 확인합니다."""

    def test_saves_only_supported_observed_metrics(self) -> None:
        snapshot = {
            "latest_month": "2026-07",
            "nationwide_comparison": {"available": False},
            "observations": [
                {"metric": "월간 순 방문자 수", "value": "1,234명", "source": "공식 원자료 방문"},
                {"metric": "월간 외지인 관광소비 총액", "value": "9,876,000원", "source": "공식 원자료 소비"},
                {"metric": "외지인 숙박 방문 비율", "value": "12.5%", "source": "공식 원자료 숙박"},
                {"metric": "외지인 평균 숙박일수", "value": "1.75일", "source": "공식 원자료 체류"},
                {"metric": "LLM 기대효과", "value": "+30%", "source": "생성 문장"},
            ],
        }
        connection = _FakeConnection()

        with patch("ai_server.app.strategy_store._connect", return_value=connection):
            saved_count = save_strategy_measurement_baseline("report-1", "11680", snapshot)

        self.assertEqual(saved_count, 4)
        self.assertEqual(
            {str(row["metric_name"]) for row in connection.cursor_instance.rows},
            {"monthly_unique_visitors", "monthly_tourism_spend", "overnight_ratio", "average_stay_days"},
        )
        self.assertNotIn("LLM 기대효과", str(connection.cursor_instance.rows))
