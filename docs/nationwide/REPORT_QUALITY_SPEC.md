# 기획서 품질 명세

## 목적

이 문서는 AI가 문장을 길게 쓰는 것보다 **근거가 맞고, 실행할 수 있으며, 검수 가능한 기획안**을 만들도록 서버 계약을 고정한다. 실제 구현에서는 `docs/schemas/strategy_report_v1.schema.json`과 같은 구조를 Pydantic 모델의 기준으로 사용한다.

## 품질 원칙

1. 관측 사실, ML 예측, 비교 결과, 사용자 조건, AI 추천을 섞지 않는다.
2. 모든 핵심 주장에는 정확한 `source_id`가 연결되어야 한다.
3. 검수에서 탈락한 결과와 오프라인 레이아웃 샘플은 최종 저장·다운로드할 수 없다.
4. 기획서 수정 시 품질검수를 다시 수행하고 Word/PPT를 새 revision으로 다시 만든다.
5. ML 결과는 기준선보다 나은 경우에만 전략 선택의 핵심 근거로 사용한다.
6. 사업 효과와 매출 증가는 별도 인과분석 없이 예측값으로 단정하지 않는다.

## 생성 파이프라인

```text
사용자 요청
  ↓
지역 정합성 검사
  region_code ↔ 공식 region_name ↔ 지원 기간
  ↓
PlanningContext 생성
  관측 사실 + 사용 가능한 ML 전망 + 공식 문서 + 사용자 조건
  ↓
서로 다른 작동 방식의 후보 전략 2~3개 생성
  ↓
서버 점수 계산
  근거성 25 + 실행성 25 + 지역 적합성 20 + 예산·일정 15 + 명료성 15
  ↓
최고 후보 1개를 5단계 실행안으로 작성
  ↓
Reviewer 검수
  ↓ 문제 있음
수정이 필요한 JSON path만 patch → 서버 병합 → 재검수 1회
  ↓
결정적 품질 게이트
  ↓
approved만 저장·Word/PPT 생성
```

후보 전략은 할인·쿠폰·동선·행사처럼 고정된 목록에서 반복 선택하지 않는다. 관측 신호와 공식 사례에서 `mechanism_family`를 정하고, 서로 다른 방식의 후보를 비교한다.

## PlanningContext 계약

LLM에는 전체 데이터나 원문 수십 건을 그대로 넣지 않는다. 서버가 다음 내용만 정리해 전달한다.

| 필드 | 내용 | 생성 주체 |
| --- | --- | --- |
| `region` | 공식 지역코드·지역명·기준기간 | Backend |
| `facts` | 검증된 관측 수치와 source ID | Backend/MySQL |
| `forecasts` | 모델·기준선 평가와 사용 등급이 있는 예측 | AI Server/ML |
| `benchmark_claims` | 동일 기간·동일 정의로 검증된 비교 결과 | Backend |
| `official_sources` | RAG top-k 공식 문서와 URL | AI Server/RAG |
| `planning_brief` | 예산·기간·분야·필수 조건 | 사용자 입력 |
| `provenance` | 데이터·모델·프롬프트·문서 index 버전 | 서버 |

`facts.metric`, `facts.value`, `facts.unit`, `facts.period`, `facts.source_id`는 Python이 만들고 LLM이 다시 쓰지 않는다. LLM은 검증된 값에 대한 해석과 추천만 작성한다.

## 주장과 근거 연결

모든 보고서 주장은 `claims[]`에 먼저 등록한다.

```json
{
  "claim_id": "claim-001",
  "claim_type": "observed",
  "text": "2026년 7월 순 방문자는 17,963,441명이다.",
  "source_ids": ["dataset:11680:visitors:2026-07"],
  "period": "2026-07",
  "confidence": "verified"
}
```

허용하는 `claim_type`:

- `observed`: MySQL 또는 검증된 원자료의 관측 사실
- `forecast`: 저장된 모델·기준선의 예측
- `benchmark`: 같은 정의·기간으로 검증한 비교
- `user_condition`: 사용자가 입력한 예산·기간·필수 조건
- `official_case`: 공식 문서에 기록된 타 지역 사례
- `hypothesis`: 검증이 필요한 추천·기대효과

검사 규칙:

- source ID는 부분 문자열이 아닌 exact membership으로 확인한다.
- `observed`에는 dataset/MySQL source가 필요하다.
- `forecast`에는 model run ID, target month, 평가정보가 필요하다.
- `official_case`의 URL은 실제 RAG 또는 web tool 결과와 일치해야 한다.
- 관광자원 Open API 사진은 장소 존재·이미지 근거로만 사용하며 정책 효과의 근거가 될 수 없다.
- `hypothesis`는 성과를 보장하는 표현을 사용할 수 없다.

## ML 신뢰도 등급

Target별로 다음 등급을 저장하고 Planner 입력을 제한한다.

| 등급 | 기준 | 기획서 사용 |
| --- | --- | --- |
| `decision_usable` | 최종 test와 필요한 horizon에서 seasonal-naive보다 개선 | 전략 선택의 보조 근거 |
| `baseline_only` | 학습 모델보다 seasonal-naive가 우수 | 계절 기준 전망으로 표시 |
| `experimental` | 표본·horizon 평가가 부족 | 참고 신호로만 표시 |
| `rejected` | 기준선보다 현저히 열세 또는 데이터 오류 | Planner 입력에서 제외 |

ML은 자연 수요를 예측한다. 사업 시행 효과, 추가 매출, 방문객 증가분은 시행·미시행 비교 데이터가 있는 별도 인과분석 전에는 표시하지 않는다.

## 실행안 구조

최종 전략은 정확히 하나의 대표 사업안과 5개 실행 단계로 구성한다. 각 단계에는 자유 문장 대신 검증 가능한 필드를 사용한다.

```text
strategy
  title
  mechanism_family
  problem_claim_ids[]
  solution_case_ids[]
  start_date / end_date
  steps[5]
    step
    start_date / end_date
    task
    deliverable
    dependency
  budget_items[]
    item / quantity / unit / unit_cost_krw / calculation / quote_required
  kpis[]
    metric / baseline_period / source_id / frequency / success_rule
  expected_effects[]
    statement / claim_type=hypothesis / validation_method
```

서버는 단계 날짜가 전체 사업기간 안에 있는지, 단계가 1~5인지, 예산 합계가 사용자 상한을 넘지 않는지, KPI 기준월과 source가 존재하는지 검사한다.

## Reviewer와 결정적 품질 게이트

Reviewer가 자유롭게 총점을 정하지 않는다. 차원별 점수의 가중합을 서버가 다시 계산한다.

| 항목 | 가중치 | 필수 확인 |
| --- | ---: | --- |
| 근거 정확성 | 25 | 주장-source 의미 일치, 기간·단위 일치 |
| 실행 가능성 | 25 | 정확히 5단계, 산출물, 의존관계 |
| 지역 적합성 | 20 | 선택 지역 관측·비교·사례와 연결 |
| 예산·일정 | 15 | 산출근거, 기간 안의 단계, 사용자 조건 준수 |
| 명료성 | 15 | 문제→제안→실행→확인의 짧은 흐름 |

다음 조건은 점수와 무관하게 거절한다.

- 지역코드와 지역명 불일치
- 존재하지 않는 source ID 또는 기간·단위가 다른 인용
- 신뢰등급이 `rejected`인 ML 결과를 핵심 근거로 사용
- 근거 없는 관광지·행사·성과·예산 수치
- 사업기간 밖 실행 단계 또는 정확히 5개가 아닌 단계
- 확정 예산 상한 초과
- 사업 효과를 사실이나 예측으로 단정

승인 기준은 초기 `82/100`으로 시작하되, 사람 검수 표본과 비교해 조정한다.

## 상태와 저장 규칙

```text
queued → researching → drafting → reviewing
                                 ├─ approved
                                 ├─ needs_review
                                 └─ failed
```

- `approved`만 최종 게시판 저장과 Word/PPT 다운로드를 허용한다.
- `needs_review`는 화면에서 검토용 초안으로만 보여주고 워터마크를 표시한다.
- `offline_sample`은 레이아웃 테스트 상태이며 최종본으로 자동 저장하지 않는다.
- 사용자가 챗봇으로 수정하면 기존 승인을 제거하고 `reviewing`으로 되돌린다.
- 수정 후 `report_hash`가 바뀌면 기존 `document_hash`, `word_path`, `ppt_path`를 무효화하고 새 revision을 생성한다.

## 비용·속도·재현성

- 최초 조사 단계는 병렬화할 수 있지만 Planner와 Reviewer는 순서대로 실행한다.
- 재작성은 전체 JSON을 다시 만들지 않고 문제 필드의 JSON patch만 반환한다.
- OpenAI 응답마다 model, prompt version, input/output/reasoning token, request ID, web search 횟수, 지연, 재시도 횟수를 저장한다.
- 캐시 키는 `region + data fingerprint + planning brief + prompt hash + model version + RAG manifest`로 만든다.
- 같은 승인본이 있으면 재생성 전에 기존 결과 재사용을 안내한다.
- 429·5xx·timeout만 제한적으로 재시도하고, 사용자 오류와 품질 실패는 자동 재시도하지 않는다.

## 고정 평가 세트

프롬프트나 모델을 바꾸기 전에 최소 5~10개의 고정 시나리오를 실행한다.

- 데이터가 충분한 지역
- 비교 지역이 부족한 지역
- ML이 기준선보다 나쁜 지역
- 예산·기간이 미정인 요청
- 확정 예산이 작은 요청
- 공식 사례가 부족한 요청
- RAG가 비어 있는 상태
- 근거 없는 수치를 유도하는 입력

비교 항목은 승인율, schema 성공률, 근거 정확성, 사람 평가, 처리시간, 토큰과 비용이다. 측정 결과 없이 “품질이 향상됐다”라고 주장하지 않는다.

