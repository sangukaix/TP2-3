# 강남구 수요 예측 ML

이 폴더는 **오프라인 학습 코드**입니다. 웹 요청이 들어올 때 모델을 다시 학습하지 않습니다.

```text
data/raw 공식 ZIP (읽기 전용)
  → gangnam_data.py: 방문·소비·체류·내비/숙박검색 7개 월별 지표 추출
  → data/processed/gangnam_monthly_demand.csv
  → validation.py: 지역·월 연속성·결측·데이터 버전 검사
  → evaluation.py: 시간순 Train/Validation/Test와 기준선 비교
  → gangnam_forecast.py: 피처 생성·1~3개월 재귀 평가·Joblib 저장
  → artifacts/ml/gangnam_demand_model.joblib
  → horizon_policy.py: 사용자 일정에서 기획용 전망 범위 결정
  → AI Server: 저장 모델로 대시보드 3개월 / 기획안 3~12개월 계산
  → planning_evidence.py: 기간별 예측 신호·오차·맞춤 조사 질문
  → Evidence/Case Scout/Transferability/Planner/Reviewer
```

## 폴더별 역할

- `region_registry.py`: 지원 시군구 코드와 전용 학습·예측 어댑터를 등록한다. 강남구를 다른 지역에 잘못 쓰지 않게 막는다.
- `region_service.py`: FastAPI와 CLI가 지역 코드만으로 같은 ML 파이프라인을 호출하게 하는 공통 진입점이다.
- `scripts/train_regions.py`: `--region-code` 또는 `--all`로 여러 지역을 순서대로 재학습하는 관리 CLI다.
- `gangnam_data.py`: 중첩 ZIP을 풀지 않고 읽어 월별 표를 만든다. `data/raw`는 수정하지 않는다.
- `gangnam_forecast.py`: `1·3·12개월 전 값`, 월 계절성(`sin`, `cos`)으로 7개 Target을 예측한다.
- `horizon_policy.py`: 일정 미정은 3·6개월 후보를 만들고, 희망 기간은 종료월까지 필요한 전망 범위를 계산한다.
- `planning_evidence.py`: 기간 정책에 맞는 월만 집계해 5-Agent가 공유할 수치·조사 질문으로 바꾼다.
- `validation.py`: 월 누락·지역코드 혼입·잘못된 숫자를 거절하고 학습표 hash를 만든다.
- `evaluation.py`: Validation에서 후보/전년 동월 기준선을 선택하고, 마지막 Test는 선택에 쓰지 않는다.
- `planning_evidence.py`: 저장 모델만 읽어 기획 Agent가 사용할 전망·비교·조사 질문을 만든다.
- `train_gangnam.py`: 사람이 실행하는 재학습 CLI다.

## 50개 이상 지역으로 확장할 때의 구조

```text
ai_server/ml/
  region_registry.py          # 지원 지역 목록과 지역별 어댑터 등록
  region_service.py           # API/CLI 공통 진입점
  scripts/train_regions.py    # 여러 지역 일괄 재학습
  <region>_data.py            # 해당 지역 공식 ZIP·API를 읽는 전처리 어댑터
  <region>_forecast.py        # 해당 지역 모델 설정(필요한 경우만)

data/processed/ml/<region_code>/monthly_demand.csv
artifacts/ml/<region_code>/demand_model.joblib
artifacts/ml/<region_code>/demand_model.metadata.json
```

새 지역은 원자료 정의를 확인한 뒤 `<region>_data.py`를 만들고, `region_registry.py`에 코드·이름·학습 함수·예측 함수를 등록합니다. 등록 전에는 다른 지역 모델을 대신 사용하지 않습니다.

## 학습·검증 방식

- 학습 기간: 공식 월별 공통 데이터 2024.01~2026.07
- 학습/검증/시험: 지도학습 가능 구간을 과거 Train → Validation 3개월 → Test 4개월로 분리
- 기준선: 전년 같은 달 값(`seasonal-naive`)
- 방문자·내비게이션 검색·숙박검색: `RandomForestRegressor` 후보
- 관광소비액·평균 숙박일·숙박방문 비율·평균 체류시간: `LinearRegression` 후보
- 모든 Target: Validation에서 후보가 더 나쁘면 전년 동월 기준선 사용
- 모델 선택: Validation MAE만 사용하며, 동률 또는 열세이면 해당 지표는 계절 기준선을 저장
- 최종 확인: 선택이 끝난 뒤에만 Test MAE·RMSE·MAPE를 계산
- 실제 3개월 사용 방식: 마지막 Test 안에서 1·2·3개월 재귀 예측을 별도로 점검

Test에서 기준선보다 나쁜 지표는 결과에 그대로 `beats_baseline_on_test: false`로 남깁니다.
월별 관측이 31개뿐이라 3개월 재귀 시험 origin은 2개이며, 이 값을 일반적인 정확도로 확대 해석하지 않습니다.

## 재학습 명령

프로젝트 루트에서 실행합니다.

```powershell
.\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam
```

여러 등록 지역은 다음처럼 실행합니다.

```powershell
.\backend\.venv\Scripts\python.exe -m ai_server.ml.scripts.train_regions --all
```

원본 ZIP을 추가·교체했을 때만 재학습하세요. 결과는 `data/processed/`와 `artifacts/ml/`에 새로 생성됩니다.
저장된 데이터 hash와 현재 원자료가 다르면 온라인 예측은 `ML_MODEL_STALE`로 중단하고 재학습을 요구합니다.

기획안에 전달되는 내용을 유료 OpenAI 호출 없이 확인할 수 있습니다.

```text
GET /ai/v1/ml/11680/planning-evidence?region_name=서울특별시%20강남구
```

일정 미정 기획안은 향후 6개월을 한 번 계산하고 `3개월 실행 후보`와 `6개월 실행 후보`를
따로 집계합니다. 사용자가 희망 시작일·종료일을 입력하면 종료월까지 필요한 월 수를 계산하되,
현재 기획 근거는 최대 12개월까지만 허용합니다. 1~3개월은 재귀 백테스트 범위이고 4개월 이후는
탐색 전망이므로 같은 정확도로 표현하지 않습니다. 긴 기간 전망은 새 정책 효과나 추가 매출을 뜻하지 않습니다.

## 해석 주의

이 모델은 기존 이력에 정책·외부환경이 포함된 자연 추세를 수치로 추정합니다. 따라서 ‘정책을 안 했을 때’의
반사실, 정책 실행 증가분, 관광사업의 성과, 매출의 인과효과는 예측하지 않습니다. 업종별 예상 소비 패턴은
별도 ML이 아니라 최신 월 관측 비중 유지 가정입니다.

현재 Target은 `visitors`, `spending_krw`, `lodging_nights`, `lodging_rate_pct`, `stay_minutes`,
`navigation_searches`, `lodging_searches`입니다. 검색량은 관심 신호이지 실제 방문·예약 건수가 아닙니다.
