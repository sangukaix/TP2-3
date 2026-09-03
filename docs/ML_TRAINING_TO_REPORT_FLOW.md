# ML 학습 결과가 AI 기획서가 되기까지

> 이 문서는 `training_result.txt`를 대체하지 않습니다.  
> 복잡한 `print` 로그 대신, **어떤 파일이 무엇을 하고 다음 어디로 가는지** 빠르게 확인하는 용도입니다.

## 한눈에 보는 전체 흐름

```text
[1] 공식 관광 원본 데이터
    data/raw/ , test-gangnam-dashboard/download/
        │
        ▼
[2] 원본 ZIP/CSV 읽기 및 월별 데이터 정리
    ai_server/ml/gangnam_data.py
    ai_server/ml/regional_datalab_data.py
        │
        ▼
[3] ML 학습용 월별 표 생성
    data/processed/ml/11680/monthly_demand.csv
        │
        ▼
[4] 시간순 모델 학습 및 성능 평가
    ai_server/ml/gangnam_forecast.py
        │
        ▼
[5] 학습 모델과 성능 정보 저장
    artifacts/ml/11680/demand_model.joblib
    artifacts/ml/11680/demand_model.metadata.json
        │
        ▼
[6] 저장 모델을 읽어 미래 값 예측
    ai_server/ml/region_service.py
    ai_server/ml/gangnam_forecast.py
        │
        ▼
[7] 예측값을 기획서용 근거로 변환
    ai_server/ml/planning_evidence.py
        │
        ▼
[8] AI가 근거 기반 전략기획서 작성 및 검수
    ai_server/app/agents/report_orchestrator.py
        │
        ▼
[9] 화면 표시 · MySQL 저장 · Word/PPT 출력
    ai_server/app/main.py
    ai_server/app/strategy_store.py
    storage/strategy_documents/
```

---

## [1] 원본 데이터: 어디에 두는가

```text
data/raw/
└─ 서울특별시/
   └─ 서울특별시_강남구-....zip

test-gangnam-dashboard/download/
├─ 강남구_방문자.zip
├─ 강남구_관광소비.zip
└─ 강남구_숙박체류시간.zip
```

- 한국관광 데이터랩에서 받은 ZIP/CSV 원본입니다.
- 원본은 **수정하지 않습니다.**
- 원본을 추가하거나 교체한 경우에만 재학습합니다.

## [2] 원본을 읽는 파일

```text
강남구 ZIP 원본
  → ai_server/ml/gangnam_data.py

일반 지역 CSV 원본
  → ai_server/ml/regional_datalab_data.py
```

이 단계에서 월별로 공통으로 존재하는 아래 7개 지표를 뽑습니다.

```text
visitors              외지인 순 방문자 수
spending_krw          관광소비액
lodging_nights        평균 숙박일수
lodging_rate_pct      숙박방문자 비율
stay_minutes          평균 체류시간
navigation_searches   내비게이션 검색량
lodging_searches      숙박 목적지 검색량
```

## [3] ML용 데이터 표

```text
data/processed/ml/11680/monthly_demand.csv
```

이 파일은 원본을 학습 가능한 월별 표로 정리한 결과입니다.

```text
region_code | year_month | visitors | spending_krw | ...
11680       | 202401     | ...      | ...          | ...
11680       | 202402     | ...      | ...          | ...
```

`validation.py`가 지역코드 혼입, 월 누락, 숫자 오류를 검사합니다. 모든 Target이 공통으로 존재하는 월이 최소 24개월이어야 학습할 수 있습니다.

## [4] 머신러닝: 어디에서 실행되는가

핵심 파일은 아래입니다.

```text
ai_server/ml/gangnam_forecast.py
```

이 파일은 다음 작업을 합니다.

```text
1. 과거 1개월·3개월·12개월 전 값(lag)을 피처로 생성
2. 월을 sin/cos 값으로 바꾸어 계절성 반영
3. 과거 → 검증 3개월 → 시험 4개월 순서로 시간 분리
4. LinearRegression / RandomForestRegressor / 전년 동월 기준선 비교
5. Validation MAE 기준으로 각 지표에 가장 적절한 방법 선택
```

`index`가 12부터 시작하는 이유는 작년 같은 달(`lag_12`) 값을 사용하기 위해 첫 12개월을 과거 이력으로 보관해야 하기 때문입니다.

### 학습 실행 명령

프로젝트 루트에서 실행합니다.

```powershell
cd C:\Users\Admin\MBCA\TeamProject\TP2-3
& ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam
```

`train_gangnam_000-1.py`는 확인용 출력이 추가된 별도 진입점입니다.

```powershell
& ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_000-1
```

두 명령 모두 내부적으로 `gangnam_forecast.py`의 `train_gangnam_models()`를 호출합니다.

## [5] 학습 결과: joblib 파일이 만들어지는 곳

학습이 끝나면 `gangnam_forecast.py`의 `joblib.dump(...)`가 아래 파일을 만듭니다.

```text
artifacts/ml/11680/demand_model.joblib
  → 실제 학습된 모델 묶음

artifacts/ml/11680/demand_model.metadata.json
  → 학습 기간, 피처, 선택 모델, MAE/RMSE/MAPE, 한계
```

`joblib` 파일은 직접 편집하지 않습니다. 재학습 명령이 새 모델로 갱신합니다.

## [6] 저장된 모델을 실제 서비스에서 사용하는 함수

```text
demand_model.joblib
  → _load_region_artifact()      # joblib.load()로 파일 읽기
  → predict_region_future_months() # 다음 달 이후 값 계산
  → predict_region_demand()        # 지역 코드로 공통 호출
```

파일 기준 경로입니다.

```text
ai_server/ml/gangnam_forecast.py
  ├─ _load_region_artifact()
  └─ predict_region_future_months()

ai_server/ml/region_service.py
  └─ predict_region_demand(region_code, horizon)
```

예시:

```python
predict_region_demand("11680", 3)
```

강남구(`11680`)의 향후 3개월 예측을 반환합니다. 웹 요청마다 재학습하지 않고, 이미 저장된 `joblib` 모델만 읽습니다.

## [7] 예측값을 기획서 근거로 바꾸는 단계

```text
ai_server/ml/planning_evidence.py
```

이 파일은 예측값을 단순 숫자가 아니라 기획에 쓸 수 있는 근거로 바꿉니다.

```text
예측: 향후 3개월 방문객 전망
비교: 전년 동월 실제 방문객
결과: 증가/감소 추세, 오차 정보, 추가 조사 질문
```

중요: 이 예측은 과거 추세의 전망입니다. 정책을 실행했을 때의 증가분이나 사업의 인과 효과를 예측하는 것은 아닙니다.

## [8] AI 기획서 작성 단계

```text
ai_server/app/agents/report_orchestrator.py
```

ML 모델 자체를 OpenAI에 넣는 것이 아닙니다. Python ML 코드가 예측한 **숫자와 성능 정보**만 전달합니다.

```text
저장 모델(joblib)
  → Python이 미래 수치 계산
  → planning_evidence.py가 기획 근거 생성
  → Evidence / Case Scout / Transferability / Planner / Reviewer
  → 근거 기반 전략기획서 JSON
```

## [9] 최종 보고서 출력·저장

```text
ai_server/app/main.py
  → API 응답으로 화면에 기획서 표시

ai_server/app/strategy_store.py
  → MySQL에 기획서와 작업 상태 저장
  → Word/PPT 문서 경로 저장

storage/strategy_documents/
  → 생성된 Word/PPT 파일 보관
```

## 담당자용 확인 순서

```text
원본을 새로 받음
  → data/raw에 보관
  → 학습 명령 실행
  → data/processed/.../monthly_demand.csv 확인
  → artifacts/ml/.../demand_model.metadata.json에서 성능 확인
  → AI Server 대시보드/기획서에서 저장 모델 예측 사용
```

## 빠른 역할 구분

| 구분 | 담당 파일 | 하는 일 |
| --- | --- | --- |
| 원본 읽기 | `gangnam_data.py` | ZIP/CSV에서 월별 지표 추출 |
| 데이터 검사 | `validation.py` | 월 누락·오류 검증 |
| 학습·예측 | `gangnam_forecast.py` | 피처·모델·평가·Joblib |
| 모델 사용 | `region_service.py` | 저장 모델 예측 요청 |
| 기획 근거 | `planning_evidence.py` | 예측을 전략 근거로 변환 |
| AI 기획서 | `report_orchestrator.py` | 근거 수집·전략 작성·검수 |
| 저장·문서 | `strategy_store.py` | MySQL·Word·PPT 저장 |
