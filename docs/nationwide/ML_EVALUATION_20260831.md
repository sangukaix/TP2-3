# 다음 달 방문자 예측 1차 평가

## 목적

전국 데이터 snapshot의 132개 지역 staging을 이용해 다음 달 방문자 수를 예측하고, 복잡한 모델이 전년동월 방문자 수를 그대로 사용하는 seasonal-naive보다 실제로 나은지 확인했다.

## 데이터와 분리

- 원본 월 범위: 2024-01~2026-06
- staging 지역: 132
- feature 생성 후 평가 지역: 131 (양양군 방문자 원본 누락으로 제외)
- train: 2025-02~2025-06
- validation: 2025-07~2025-12
- test: 2026-01~2026-06
- random split: 사용하지 않음

## 사용 feature

- 방문자 lag 1·2·3·12·13개월
- 직전 3개월 방문자 평균
- 직전 월 내국인·외지인 관광소비
- 직전 월 숙박자 비율, 평균 숙박일, 평균 체류시간
- 직전 월 전년동월 방문자 비율
- 예측 월의 계절 sin/cos
- 지역코드 one-hot encoding

모든 feature는 target 월보다 앞선 시점의 값만 사용한다.

## 주요 평가 결과

| 모델 | Validation MAE | Validation MAPE | Test MAE | Test MAPE | 판단 |
| --- | ---: | ---: | ---: | ---: | --- |
| seasonal-naive | 223,509 | 8.96% | 144,983 | 7.27% | 현재 기준선 |
| Random Forest 직접 예측 | 178,010 | 8.86% | 171,393 | 8.48% | test 악화, rejected |
| 전년동월·최근월 혼합 | 191,755 | 8.44% | 137,875 | 6.91% | 후속 검증 후보 |
| 전년 증가율 유지 | 186,742 | 9.46% | 192,574 | 10.89% | rejected |
| Linear Regression | 346,603 | 22.01% | 249,930 | 16.26% | rejected |

## 판단

Validation MAE가 가장 낮은 Random Forest를 선택했지만 완전한 test에서 seasonal-naive보다 나빴다. 따라서 저장 모델의 상태는 `rejected`이며 기획서의 확정 전망에 사용하지 않는다.

전년동월·최근월 혼합은 두 구간에서 기준선보다 낮은 오류를 보였지만, test 결과를 본 뒤 선택을 바꾸면 test를 사실상 tuning에 사용하게 된다. 이번 snapshot에서는 연구 후보로만 기록하고 새 월 데이터가 추가된 별도 holdout에서 다시 평가한다.

## 기획서 적용 원칙

- 현재 숫자 전망은 `seasonal-naive baseline`과 한계를 표시한다.
- `rejected`와 `experimental` artifact는 Planner 입력에서 제외한다.
- ML이 통과하지 않아도 MySQL 관측 사실과 지역 비교 진단은 사용할 수 있다.
- 사업 효과나 매출 증가를 이 예측으로 주장하지 않는다.

## 다음 개선

1. 서울·인천 등 남은 지역과 새 월 데이터를 추가한다.
2. 공식 지역코드와 상위 시/하위 구 분석 단위를 확정한다.
3. rolling-origin validation으로 계절별 안정성을 비교한다.
4. 지역 규모를 정규화한 전년동월 대비 변화 모델을 재검증한다.
5. 최종 holdout을 새로 확보하기 전에는 후보를 production으로 승격하지 않는다.
