from __future__ import annotations

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from data_pipeline.tools.build_nationwide_bigdata_context import build_nationwide_bigdata_context


class NationwideBigdataContextTests(unittest.TestCase):
    def _write_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "지역별 방문자 수(기초지자체별).csv",
                "광역지자체명,기초지자체명,광역지자체 방문자 수,광역지자체 방문자 비율,기초지자체 방문자 수,기초지자체 방문자 비율\n서울특별시,강남구,1000,10,300,30\n세종특별자치시,세종특별자치시,100,1,100,100\n",
            )
            archive.writestr(
                "방문자 수 추이.csv",
                "기준년월,광역지자체,방문자 구분,방문자 수\n202301,전국,외지인,5000\n",
            )
            # 광역 단위 표는 시군구 비교층에 잘못 섞이면 안 된다.
            archive.writestr("지역별 방문자 수(광역별).csv", "광역지자체명,광역지자체 방문자 수\n서울특별시,1000\n")

    def _write_mapping(self, path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["region_code", "province_name", "municipality_name"])
            writer.writeheader()
            writer.writerow({"region_code": "11680", "province_name": "서울특별시", "municipality_name": "강남구"})

    def test_builds_separate_municipal_and_national_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot" / "이동통신" / "내국인" / "지역별 방문자수"
            snapshot.mkdir(parents=True)
            self._write_zip(snapshot / "sample_202301-202312_데이터랩_다운로드.zip")
            mapping = root / "regions.csv"
            self._write_mapping(mapping)
            output = root / "output"

            summary = build_nationwide_bigdata_context(snapshot_root=root / "snapshot", mapping_path=mapping, output_dir=output)

            self.assertEqual("ready_for_nationwide_bigdata_mysql_import", summary["status"])
            self.assertEqual(1, summary["municipal_period_metric_count"])
            self.assertEqual(1, summary["national_monthly_context_count"])
            self.assertEqual(1, summary["rejection_count"])
            self.assertEqual(0, summary["blocking_rejection_count"])
            self.assertEqual("excluded_period_aggregate_and_national_context", summary["ml_training_usage"])
            with (output / "municipal_period_metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
                municipal = list(csv.DictReader(stream))
            self.assertEqual("11680", municipal[0]["region_code"])
            self.assertEqual("300", municipal[0]["metric_value"])
            with (output / "national_monthly_context.csv").open(encoding="utf-8-sig", newline="") as stream:
                national = list(csv.DictReader(stream))
            self.assertEqual("2023-01", national[0]["year_month"])
            self.assertEqual("5000", national[0]["metric_value"])
            self.assertEqual(1, len(json.loads((output / "summary.json").read_text(encoding="utf-8"))["municipal_metric_counts"]))


if __name__ == "__main__":
    unittest.main()
