# 공식 원본 Snapshot 보관소

이 폴더는 팀 공유폴더와 기존 수동 보관소의 공식 관광데이터랩 ZIP·CSV를 로컬에서
안정적으로 사용하기 위한 **hash 검증 불변 복제본**이다. snapshot 생성 과정은
`data/raw/`의 수동 보관 원본을 수정·이동·삭제하지 않는다. 활성 ML 카탈로그는 이 폴더만 읽는다.

- `data_pipeline.tools.materialize_regional_archives`,
  `data_pipeline.tools.materialize_local_source_snapshot` 또는
  `data_pipeline.tools.materialize_regional_tourism_status`만 파일을 추가한다.
- 파일명·내부 ZIP·CSV는 수정하지 않으며, 같은 경로에서 SHA-256이 다르면 중단한다.
- 부모 묶음 ZIP과 내부 지역 ZIP의 hash 관계는 `data/interim/regional_archive_materialization/` manifest에 기록한다.
- 이 폴더의 실제 데이터는 Git에 올리지 않는다.

## 기존 수동 원본 전환 (2026-09-04)

- `인천광역시/`: 기존 `data/raw/인천광역시`의 계양구·서구·옹진군 CSV 631개를 상대경로와
  SHA-256이 동일하게 복제했다. 사용자 승인에 따라 원래 raw 복제본은 검증 뒤 Windows 휴지통으로
  이동했으며, 기록은 `data/interim/local_source_snapshot/20260904_incheon/`에 둔다.
- `서울특별시/서울특별시_강남구/supplemental_202607/`: 기존 최신 2026년 7월 공식 ZIP 9개를
  복제했다. 기본 서울 category ZIP은 2026년 6월까지이므로, 강남 전용 로더가 이 보완 snapshot만
  마지막에 명시적으로 적용한다. 기록은
  `data/interim/local_source_snapshot/20260904_gangnam_supplement/`에 둔다.

## 지역별 관광 현황 ZIP (2026-09-03)

`지역별 관광 현황_데이터_202401-202606_202609030.zip`은 유입·유출 권역,
인기 관광지·음식점, 향후 30일 집중 운영 신호를 담은 불변 원본이다. 복제본의
SHA-256과 내부 ZIP 계보는 `data/interim/regional_tourism_status_snapshot/`에 기록한다.

- 정규화 결과: `data/processed/regional_tourism_status/`
- MySQL 적재: `data_pipeline.tools.import_regional_tourism_status --apply`
- 사용 범위: 기획 후보의 권역·장소·분산 운영 근거. 월별 ML 학습값·정책 효과·확정 수요로 사용하지 않는다.
