"""공식 고정폭 행정구역 코드의 parsing과 보수적 mapping을 검증한다."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from data_pipeline.tools.build_region_code_reference import (
    FIELD_SLICES,
    parse_official_legal_dong_zip,
    resolve_region_mapping,
)


def fixed_width_line(**values: str) -> bytes:
    """행정안전부 TEXT layout과 같은 300-byte 테스트 행을 만든다."""

    output = bytearray(b" " * 300)
    for field, value in values.items():
        start, end = FIELD_SLICES[field]
        encoded = value.encode("cp949")
        output[start : start + min(len(encoded), end - start)] = encoded[: end - start]
    return bytes(output)


class RegionCodeReferenceTest(unittest.TestCase):
    def test_parse_and_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / "codes.zip"
            header = fixed_width_line(legal_dong_code="법정동코드")
            region = fixed_width_line(
                legal_dong_code="4111000000",
                province_name="경기도",
                municipality_name="수원시",
                created_date="19880101",
            )
            abolished = fixed_width_line(
                legal_dong_code="9999900000",
                province_name="경기도",
                municipality_name="폐지시",
                created_date="19880101",
                abolished_date="20200101",
            )
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("KIKcd_B.20260201", b"\n".join([header, region, abolished]))

            official = parse_official_legal_dong_zip(zip_path)
            self.assertEqual(len(official), 1)
            self.assertEqual(official[0]["region_code"], "41110")

            mapped = resolve_region_mapping(
                [
                    {
                        "region_folder": "경기도_수원시",
                        "province_name": "경기도",
                        "municipality_name": "수원시",
                        "local_hierarchy_name": "수원시",
                        "region_code_candidates_json": "[]",
                        "mapping_status": "unresolved",
                        "official_region_code": "",
                    }
                ],
                official,
            )
            self.assertEqual(mapped[0]["official_region_code"], "41110")
            self.assertEqual(mapped[0]["mapping_status"], "validated_from_mois")

    def test_existing_datalab_mapping_wins(self) -> None:
        rows = resolve_region_mapping(
            [
                {
                    "region_folder": "서울특별시_강남구",
                    "province_name": "서울특별시",
                    "municipality_name": "강남구",
                    "local_hierarchy_name": "강남구",
                    "region_code_candidates_json": '["11680"]',
                    "mapping_status": "resolved_from_data",
                    "official_region_code": "11680",
                }
            ],
            [],
        )
        self.assertEqual(rows[0]["mapping_status"], "validated_from_datalab")
        self.assertEqual(rows[0]["official_region_code"], "11680")
        self.assertEqual(rows[0]["canonical_province_name"], "서울특별시")


if __name__ == "__main__":
    unittest.main()
