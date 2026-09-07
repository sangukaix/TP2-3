"""category ZIP 형태 원본이 CSV 지역과 같은 7개 target으로 읽히는지 검증한다."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from ai_server.ml.regional_datalab_data import StandardDatalabRegion, load_standard_datalab_monthly_demand


def _months(year: int) -> list[str]:
    return [f"{year}{month:02d}" for month in range(1, 13)]


def _write_archive(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in rows.items():
            archive.writestr(name, content.encode("utf-8-sig"))


class RegionalDatalabArchiveTest(unittest.TestCase):
    def test_category_zip_source_builds_twenty_four_months_and_excludes_national_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "서울특별시_테스트구"
            for year in (2024, 2025):
                months = _months(year)
                visitor_rows = "기준연월,순 방문자수\n" + "\n".join(f"{month},{100 + index}" for index, month in enumerate(months))
                nights_rows = "기준연월,평균 숙박일수\n" + "\n".join(f"{month},2.0" for month in months)
                rate_rows = "기준연월,지역명,숙박방문자 비율\n" + "\n".join(f"{month},테스트구,10.0" for month in months)
                stay_rows = "기준연월,지역명,체류시간(분)\n" + "\n".join(f"{month},테스트구,120" for month in months)
                search_rows = "기준연월,검색건수\n" + "\n".join(f"{month},50" for month in months)
                _write_archive(root / "숙박_체류시간" / f"{year}_01_12.zip", {
                    "순 방문자 수 및 숙박 비율.csv": visitor_rows,
                    "평균 숙박일.csv": nights_rows,
                    "숙박방문자 비율 추이.csv": rate_rows,
                    "평균 체류시간 추이.csv": stay_rows,
                    "숙박 목적지 검색건수.csv": search_rows,
                })
                spending_rows = "기준연월,업종대분류명,소비액(천원)\n" + "\n".join(f"{month},전체,1000" for month in months)
                comparison_rows = "기준연월,지역명,관광소비액(백만원)\n" + "\n".join(f"{month},테스트구,999999" for month in months)
                _write_archive(root / "관광소비" / f"{year}_01_12.zip", {
                    "관광소비 추이_외지인.csv": spending_rows,
                    "전국 대비 관광소비 추이_외지인.csv": comparison_rows,
                })
                navigation_rows = "기준연월,목적지 유형,목적지 검색량\n" + "\n".join(f"{month},전체,500" for month in months)
                _write_archive(root / "방문자" / f"{year}_01_12.zip", {"내비게이션 목적지 유형별 검색량.csv": navigation_rows})

            frame = load_standard_datalab_monthly_demand(
                StandardDatalabRegion("99999", "서울특별시 테스트구", "테스트구", root)
            )
            self.assertEqual(len(frame), 24)
            self.assertEqual(frame.year_month.iloc[0], "202401")
            self.assertEqual(frame.year_month.iloc[-1], "202512")
            self.assertEqual(float(frame.spending_krw.iloc[0]), 1_000_000)


if __name__ == "__main__":
    unittest.main()
