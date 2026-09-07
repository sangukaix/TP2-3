# 다음 달 방문자 예측 재평가 — 병합 전국 snapshot

## 평가 데이터

- 입력: 병합 전국 월별 staging 5,010행, 관측 지역 167개
- 최신 관측월: 2026-06
- feature 생성 뒤 평가 가능한 지역: 166개
- train: 2025-02~2025-06
- validation: 2025-07~2025-12
- test: 2026-01~2026-06
- random split: 사용하지 않음

## 결과와 운영 판단

| 구분 | Validation MAE | Test MAE | 운영 판단 |
| --- | ---: | ---: | --- |
| seasonal-naive | 335,006 | 209,214 | `baseline_only` |
| 최선 validation 후보: Random Forest seasonal residual | validation 우세 | test에서 기준선 미달 | 운영 제외 |

최선 후보는 validation에서는 seasonal-naive보다 좋았지만, 이미 보지 않은 test에서는 기준선보다 나빴다. 따라서 모델 파일은 후보 Random Forest가 아니라 사전에 정한 `seasonal-naive` 기준선을 `baseline_only` 상태로 저장한다.

이 규칙은 test 결과를 본 뒤 더 좋아 보이는 후보로 교체하는 data leakage를 막는다. 다음 새 월 데이터가 추가되면 별도 holdout을 두고 rolling-origin 평가를 다시 실행한 뒤에만 복잡한 모델을 승격한다.

## 기획서 사용 원칙

- baseline 전망은 계절 기준선임을 표시한다.
- 사업을 했을 때의 매출·방문 증가 효과로 해석하지 않는다.
- 기획 근거에는 관측 사실, 유사 지역 비교, 공식 RAG 문서를 함께 제공한다.
- `experimental` 또는 `rejected` model artifact는 AI Server가 로드하지 않는다.
