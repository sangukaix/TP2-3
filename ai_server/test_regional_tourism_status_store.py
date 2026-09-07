"""지역별 관광 현황 context는 원본 ZIP 대신 작은 사실표만 제공하는지 확인한다."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_server.app.regional_tourism_status_store import load_regional_tourism_status


class RegionalTourismStatusStoreTest(unittest.TestCase):
    def test_load_reads_only_selected_region(self) -> None:
        with TemporaryDirectory() as directory:
            context_path = Path(directory) / "context_by_region.json"
            context_path.write_text(
                json.dumps(
                    {
                        "regions": {
                            "11680": {
                                "available": True,
                                "region_code": "11680",
                                "region_name": "서울특별시 강남구",
                                "inflow_outflow": {"top_inflow_origins": [{"related_region_name": "서울 서초구"}]},
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = load_regional_tourism_status("11680", context_path=context_path)

            self.assertIsNotNone(result)
            self.assertEqual(result["region_name"], "서울특별시 강남구")
            self.assertEqual(result["inflow_outflow"]["top_inflow_origins"][0]["related_region_name"], "서울 서초구")
            self.assertIsNone(load_regional_tourism_status("99999", context_path=context_path))
