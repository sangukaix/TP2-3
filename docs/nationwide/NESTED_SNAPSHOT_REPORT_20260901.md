# 서울·강원 중첩 snapshot 통합 보고서

## 발견과 처리

팀 공유폴더의 `지역별 관광현황`에는 단순 비교 CSV 외에 두 개의 바깥 ZIP이 있었다.

- `서울특별시(완)-20260828T055120Z-1-001.zip`
- `강원특별자치도-20260828T055058Z-1-001.zip`

각 바깥 ZIP은 다시 지역별 Data Lab ZIP을 포함하는 일괄 다운로드 형식이었다. `tools/materialize_nested_archives.py`가 바깥 원본을 수정하지 않고 내부 ZIP의 SHA-256·부모 source를 manifest에 남겨 `data/raw/materialized/region_archives/`에 재현 가능한 local snapshot을 만들었다.

## 검증 결과

| 항목 | 결과 |
| --- | ---: |
| 바깥 ZIP | 2 |
| 내부 지역별 ZIP | 639 |
| 복원 지역 | 27 |
| 내부 ZIP 오류 | 0 |
| 서울·강원 staging 월별 행 | 810 |
| complete 행 | 810 |
| 강남구 핵심 월별 기간 | 2024-01~2026-06 |

27개 지역은 Data Lab 내부 지역코드와 2026-02-01 행정안전부 법정동 코드를 교차 검증했다.

## 전국 병합 결과

기존 전국 snapshot과 중첩 snapshot 사이에서 강릉시·고성군 60개 `region_code + year_month` 중복이 발견됐다. 핵심 관측값 9개가 모두 동일해 canonical 행 하나만 유지하고 alias audit에 기록했다. 값 충돌은 0건이다.

| 항목 | 결과 |
| --- | ---: |
| 기존 월별 행 | 4,260 |
| 중첩 snapshot 월별 행 | 810 |
| 동값 중복 행 | 60 |
| 새로 추가된 행 | 750 |
| 병합 월별 행 | 5,010 |
| 병합 관측 지역 | 167 |
| MySQL dimension 후보 지역 | 171 |

`dim_region` 후보가 171개인 이유는 코드 mapping은 통과했지만 현재 핵심 월별 fact가 없는 지역도 4개 포함하기 때문이다. 서비스의 월별 대시보드 지원 여부는 167개 fact 보유 지역으로 판단한다.

## 강남구 기획서에 쓸 수 있는 관측 context

기간은 최신 관측월 2026-06을 끝점으로 한 2025-07~2026-06과 직전 동기간이다. 아래 값은 정책 성과 예측이 아니라 원자료에서 계산한 관측·비교 값이다.

- 최근 12개월 방문자: 230,815,768명
- 전년 동기 대비 방문자 변화: +4.24%
- 최근 12개월 내국인 관광소비: 6,167,186,982천 원
- 1인당 내국인 관광소비 proxy: 26,719원
- 평균 숙박자 비율: 3.12%
- 평균 숙박일수: 2.87일
- 산출 유사 지역: 서초구, 송파구, 영등포구, 성남시, 용인시

`tools/build_planning_context.py`가 이와 같은 값을 계산하고 출처 source ID도 함께 보존한다. LLM은 이 결과를 바탕으로 설명·전략 후보를 작성할 수 있지만, 이 값만으로 사업 효과 또는 매출 상승을 단정해서는 안 된다.

## 추가 파일 감지

마지막 전체 SHA-256 감사에서는 공유폴더가 3,221개 파일로 늘었고, 기존 검사 뒤 강원 일부 지역의 `유사 지역`·`유입/유출 지역` ZIP 20개가 추가된 것을 확인했다. 이 파일들은 현재 핵심 월별 fact와 충돌하지 않으며, 다음 보조 진단 전처리 대상으로 inventory에 남겼다.

## 재실행 순서

```powershell
.\.venv\Scripts\python.exe tools\materialize_nested_archives.py --repository-root $env:TOURISM_REPOSITORY_ROOT
.\.venv\Scripts\python.exe tools\data_inventory.py --raw-root data\raw\materialized\region_archives --output-dir data\interim\materialized_inventory
.\.venv\Scripts\python.exe tools\build_region_code_reference.py --official-zip data\raw\reference\admin_codes\jscode20260201.zip --candidates data\interim\materialized_inventory\region_code_candidates.csv --output-dir data\processed\materialized_region_reference
.\.venv\Scripts\python.exe tools\build_monthly_staging.py --raw-root data\raw\materialized\region_archives --inventory-dir data\interim\materialized_inventory --region-mapping data\processed\materialized_region_reference\region_mapping_validated.csv --output-dir data\processed\materialized_staging
.\.venv\Scripts\python.exe tools\merge_monthly_staging.py
```
