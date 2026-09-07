# 전국 관광데이터 수집·저장·ML 파이프라인

## 목적

네트워크 공유폴더의 한국관광 데이터랩 원본을 수정하지 않고 검사한 뒤, 검증된 수치만 MySQL과 ML 학습 데이터로 전달한다. 서비스 요청 때마다 ZIP을 다시 읽지 않으며, 어떤 원본에서 어떤 결과가 만들어졌는지 추적 가능하게 유지한다.

## 저장 계층

```text
공유폴더 원본 ZIP (source of truth, 수정 금지)
  → 읽기 전용 inventory + SHA-256
  → data/interim 표준화·검증 결과 (재생성 가능, Git 제외)
  → data/processed 모델용/DB용 테이블 (재생성 가능, Git 제외)
  → MySQL 관측 사실
  → Joblib/Pickle model artifact + metadata JSON
  → AI Server가 시작할 때 1회 로드
```

원본 ZIP, 개인정보, DB 비밀번호, 모델 입력 전체를 Git에 올리지 않는다. Git에는 수집·검증·학습 코드, schema, 테스트, `.env.example`만 보관한다.

## 1단계: 읽기 전용 인벤토리

팀 상위 공유폴더 전체는 `tools/source_repository_inventory.py`로 먼저 검사한다. 이전 결과와 크기·수정시각이 같은 파일은 hash와 CSV profile을 재사용하고, 새 파일·변경 파일·삭제 파일을 구분한다.

```powershell
$env:TOURISM_REPOSITORY_ROOT='\\server\share\지역별 현황'
python tools/source_repository_inventory.py
```

정기 전체 검증에서는 `--full-hash`를 붙여 크기와 수정시각이 우연히 같은 교체 파일까지 다시 SHA-256으로 확인한다.

```powershell
python tools/source_repository_inventory.py --full-hash
```

## 중첩 ZIP snapshot

`지역별 관광현황`에는 일괄 다운로드 ZIP 안에 지역별 Data Lab ZIP이 다시 들어 있을 수 있다. `tools/materialize_nested_archives.py`는 바깥 원본을 수정하지 않고 내부 ZIP만 `data/raw/materialized/region_archives/`에 복원한다. `nested_archive_manifest.csv`에는 바깥·안쪽 hash와 source lineage를 남긴다.

이 snapshot은 일반 snapshot과 별도 inventory·지역코드 검증·staging을 거친 뒤 `tools/merge_monthly_staging.py`로 병합한다. 같은 `region_code + year_month`가 같은 관측값이면 alias만 남기고, 값이 다르면 자동 덮어쓰기 없이 `snapshot_conflicts.csv`에 기록한다.

그 다음 지역별 ZIP snapshot은 `tools/data_inventory.py`로 내부 CSV까지 상세 검사한다.

`tools/data_inventory.py`는 다음 정보를 생성한다.

- `archives.csv`: ZIP 경로, SHA-256, 파일명 기간, 상태
- `csv_schema_inventory.csv`: 내부 CSV, 인코딩, 컬럼, 행 수, 기간, 지역코드 후보
- `region_code_candidates.csv`: 폴더별 공식 지역코드 후보와 검토 상태
- `validation_issues.csv`: 빈 폴더, 중복 지역명, 손상 ZIP, 읽기 오류
- `source_registry_generated.csv`: 원본별 안정적인 source ID와 hash를 가진 검토용 registry
- `summary.json`: 지역·ZIP·CSV·오류 개수 요약

실행 예시:

```powershell
$env:TOURISM_RAW_ROOT='\\server\share\전국데이타_20260831'
python tools/data_inventory.py
```

현재 PC에 `python` 명령이 없다면 프로젝트 가상환경 Python의 절대 경로를 사용한다.

## 2단계: 표준화와 MySQL 적재

인벤토리 검토 후 `tools/build_monthly_staging.py`가 핵심 월간 지표를 `region_code + year_month`로 병합한다. 코드 미확정·잘못된 월·숫자·충돌 값은 `load_rejections.csv`에, 원본 행 수 대사는 `source_row_audit.csv`에 기록한다.

```powershell
python tools/build_monthly_staging.py `
  --raw-root $env:TOURISM_RAW_ROOT `
  --inventory-dir data/interim/nationwide_inventory `
  --output-dir data/processed/nationwide_staging
```

2026-02-01 시행 행정안전부 법정동 코드 ZIP으로 Data Lab 지역코드를 교차 검증한다. 이 과정은 `tools/build_region_code_reference.py`가 수행하며, 원본 표기명과 DB에 쓸 최신 공식 명칭을 모두 남긴다.

```powershell
python tools/build_region_code_reference.py --official-zip data\raw\reference\admin_codes\jscode20260201.zip
```

검증을 통과한 staging은 `tools/build_mysql_load_bundle.py`로 `dim_region`, `data_source`, `fact_tourism_monthly`, `fact_tourism_metric_source` CSV 묶음을 만들 수 있다. 이 단계는 DB를 변경하지 않으며, 모든 source 참조가 registry에 존재하는지 먼저 검증한다.

MySQL 8.x 초안 schema는 `sql/mysql/001_tourism_data.sql`에 있다. 현재는 공식 지역코드 승인 전이므로 DDL 계약만 만들고 실제 production 적재는 수행하지 않는다.

```text
dim_region
  region_code PK, province_name, municipality_name, valid_from, valid_to

fact_tourism_monthly
  region_code + year_month PK
  visitors, tourism_spend, overnight_ratio, avg_stay_days, avg_stay_minutes
  source_id, loaded_at

fact_tourism_spend_category
  region_code + year_month + category_code PK
  spend_amount, spend_ratio, source_id

data_load_run
  load_run_id, raw_snapshot, started_at, completed_at, status
  source_file_count, loaded_row_count, rejected_row_count

data_load_rejection
  load_run_id, source_id, row_number, error_code, raw_key
```

적재는 transaction으로 수행한다. `region_code + year_month` 중복, 공식 코드 미확정, 단위 불일치, 기간 역전은 조용히 보정하지 않고 거절 테이블에 남긴다.

## 3단계: ML artifact

학습은 웹 요청과 분리한다. 시간순 train/validation/test를 사용하고 seasonal-naive보다 나은 모델만 `decision_usable`로 등록한다.

현재 panel 학습 명령은 다음과 같다.

```powershell
python -m ml.train_visitors_panel `
  --input-csv data/processed/merged_nationwide_staging/tourism_monthly_staging.csv `
  --artifact-root artifacts/models/next_month_visitors_merged
```

2025년 상반기 train, 2025년 하반기 validation, 2026년 상반기 test로 분리하며 random split을 사용하지 않는다. validation에서 좋아 보인 복잡한 후보도 test에서 baseline보다 나쁘면 운영 artifact로 올리지 않고 사전에 정한 seasonal-naive를 `baseline_only` 상태로 저장한다.

```text
artifacts/models/{target}/{model_version}/
  model.joblib
  metadata.json
  metrics.json
  feature_schema.json
  training_data_manifest.json
```

`metadata.json`에는 target, 지원 지역, 학습 기간, feature, 라이브러리 버전, random seed, 모델 파일 SHA-256을 기록한다. Python 객체를 포함하는 Joblib/Pickle은 신뢰한 학습 파이프라인이 만든 파일만 로드한다.

AI Server는 `ml/artifact_store.py`를 통해 승인 상태와 SHA-256이 맞는 artifact만 로드한다. 기본적으로 `rejected`와 `experimental`은 로드가 차단된다.

## 누락 방지 원칙

1. 원본 ZIP 개수와 SHA-256을 수집 실행마다 비교한다.
2. 지역코드와 월별 예상 키 목록을 만든다.
3. 원본 행 수, 정상 적재 행 수, 거절 행 수의 합을 맞춘다.
4. 지역명만으로 조인하지 않는다.
5. 데이터 정의·단위가 바뀐 구간은 같은 시계열로 자동 병합하지 않는다.
6. MySQL 적재 후 샘플 합계와 원본 합계를 대조한다.
7. 모델마다 사용한 데이터 snapshot과 feature 목록을 저장한다.
8. AWS 전환 시 원본 위치만 S3로 바꾸고 검증 계약은 유지한다.

## 기획서 연결

기획서에는 세 종류를 분리해 전달한다.

- 관측 사실: MySQL의 검증된 월별 지표
- 예측: 저장된 ML artifact의 결과와 신뢰도 등급
- 추천: 공식 문서 RAG와 사용자 조건을 바탕으로 LLM이 작성

`1인당 관광소비`처럼 서로 다른 공식 지표를 결합한 값은 `derived_metric`으로 표시하고 계산식과 분모·분자 출처를 함께 보존한다. 사업 효과는 공식 사후평가 자료가 없으면 보장 수치로 작성하지 않는다.
