# 전국 관광 데이터 파이프라인

이 폴더는 TP2-3 서비스 코드와 분리된 **오프라인 전국 데이터 처리 영역**입니다.
웹 요청마다 원본 ZIP을 다시 읽거나 모델을 재학습하지 않습니다.

```text
공식 원본 ZIP/CSV (팀 공유폴더, 읽기 전용)
→ tools/ : inventory·정규화·중첩 ZIP 병합·MySQL 적재 후보 생성
→ data/processed/nationwide/ : 검증된 파생 CSV·비교 요약
→ nationwide_ml/ : 시간순 평가·저장 모델 생성
→ artifacts/nationwide/ : Joblib·metadata
→ database/mysql/ : MySQL 스키마
```

## 현재 포함된 결과

- `merged_nationwide_staging/`: 지역 코드와 기준월로 검증한 월별 관광 지표
- `merged_planning_context/`: 비교 지역·기간 변화·백분위 기반 기획 근거
- `mysql_load_bundle/`: MySQL 적재 전 검증용 CSV 묶음
- `artifacts/nationwide/models/`: baseline과 후보 모델 평가가 기록된 Joblib 산출물

원본 ZIP은 이 폴더로 복사하지 않는다. 팀 공유폴더의 원본을 보관하고, 새 자료 반영 시 `tools/`를 다시 실행한다.
전국 결과는 MySQL 적재와 지역별 검증을 마친 데이터만 AI Server 입력으로 연결한다. DB가 아직 준비되지 않은 경우에도 기존 지역 원자료 대시보드는 계속 작동하며, 전국 비교만 표시하지 않는다.

## 지역별 ML 확장 순서

1. `tools/assess_region_ml_readiness.py`로 24개월 이상·월 연속·핵심 target 조건을 확인합니다.
2. `nationwide_ml/evaluate_region_baselines.py`로 지역별 seasonal-naive 기준선을 시간순 validation/test에 평가합니다.
3. 후보 모델은 같은 지역·target에서 기준선을 validation과 test 모두 이긴 경우에만 `decision_usable`로 등록합니다.

현재 평가표는 모델 등록이 아닙니다. 데이터가 짧은 지역에 강남 모델을 복사하거나, 평가하지 않은 예측을 기획 근거로 쓰지 않기 위한 품질 게이트입니다.

## 검증

프로젝트 루트에서 다음 명령으로 전국 파이프라인 테스트를 실행한다.

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests\nationwide_pipeline -p "test_*.py"
```

상세 데이터 범위·병합 규칙·ML 평가 결과는 `docs/nationwide/`를 확인한다.
