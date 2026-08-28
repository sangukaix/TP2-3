# 강남구 수요 예측 ML

이 폴더는 **오프라인 학습 코드**입니다. 웹 요청이 들어올 때 모델을 다시 학습하지 않습니다.

```text
data/raw 공식 ZIP (읽기 전용)
  → gangnam_data.py: 월별 방문자·외지인 관광소비·평균 숙박일 추출
  → data/processed/gangnam_monthly_demand.csv
  → gangnam_forecast.py: 피처 생성·시간순 평가·Joblib 저장
  → artifacts/ml/gangnam_demand_model.joblib
  → AI Server 대시보드 API: 저장 모델로 3개월 예측
```

## 폴더별 역할

- `region_registry.py`: 지원 시군구 코드와 전용 학습·예측 어댑터를 등록한다. 강남구를 다른 지역에 잘못 쓰지 않게 막는다.
- `region_service.py`: FastAPI와 CLI가 지역 코드만으로 같은 ML 파이프라인을 호출하게 하는 공통 진입점이다.
- `scripts/train_regions.py`: `--region-code` 또는 `--all`로 여러 지역을 순서대로 재학습하는 관리 CLI다.
- `gangnam_data.py`: 중첩 ZIP을 풀지 않고 읽어 월별 표를 만든다. `data/raw`는 수정하지 않는다.
- `gangnam_forecast.py`: `1·3·12개월 전 값`, 월 계절성(`sin`, `cos`)으로 방문자·소비액·평균 숙박일수를 예측한다.
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
- 테스트 기간: 가장 최근 4개월을 시간순으로 분리
- 기준선: 전년 같은 달 값(`seasonal-naive`)
- 방문자: `RandomForestRegressor`
- 관광소비액: `LinearRegression`
- 평균 숙박일수: `LinearRegression`, 검증 시 더 나쁘면 전년 동월 기준선 사용
- 저장 조건: 방문자·소비액 모델의 테스트 MAE가 계절 기준선보다 낮을 때만 저장

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

## 해석 주의

이 모델은 다음 달 자연 추세를 수치로 추정합니다. 정책을 실행했을 때의 증가분, 관광사업의 성과, 매출의 인과효과는 예측하지 않습니다. 업종별 예상 소비 패턴은 최신 월 관측 비중을 유지하는 가정입니다.
