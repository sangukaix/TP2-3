# 시스템 아키텍처

## 1. 설계 원칙

### 현재 구현: 사업 여건 입력과 Agent 연결

```text
/dashboard 지역선택 (기존 지도 유지)
  └─ /planning 사업 여건
       ├─ 예산 / 일정 / 자원 / 필수 제약 (+ 선택 현장정보·선호·문서)
       ├─ 지역별 초안: 브라우저 localStorage
       └─ POST strategy-report/jobs + planning_brief
            ├─ Pydantic 검증 → 작업마다 조건 복사
            ├─ 기간 정책: 미정이면 3·6개월 비교, 입력 일정이면 종료월까지 범위 계산
            ├─ 저장 ML: 지역·데이터 hash 확인 → 동적 전망·검증 오차·조사 질문
            ├─ Evidence + Case Scout 병렬 조사 (조건을 캐시 키에 포함)
            ├─ Transferability: 지역 여건에서 가능한 대안 검토
            ├─ Planner: 문제·기회·목표·방법·실행 단계 제안
            └─ Reviewer: 근거·실행 가능성·조건 준수 검수 / 기존 재작성
                 └─ /strategy 상태 조회 → 결과 + 생성 당시 조건 저장
                      ├─ AI 챗봇: 해당 결과의 조건으로 설명·수정안
                      └─ Word/PPT: 예산·일정 요약 포함
```

`snapshot.observations`는 공식 관측값, `snapshot.ml_analysis`는 서버의 모델 전망,
`planning_brief`는 사용자 제공 여건으로 분리한다. 사용자 문서 안의 명령은 시스템 지시로 실행하지 않는다.
ML은 OpenAI 호출 전에 실행하며 방문·소비·체류·검색 전망 신호가 공식 근거·사례 조사의 질문을 좁힌다.
`horizon_policy.py`가 일정 미정에는 3개월·6개월 의사결정 창을 모두 만들고, 희망 일정에는 원자료 최신월 다음 달부터 사업 종료월까지 필요한 범위를 계산한다. 1~3개월만 재귀 백테스트 범위이며 4~12개월은 탐색 전망으로 구분한다. 모델·토큰 설정과 기존 품질 검수 절차는 유지한다.

1. 오프라인 학습과 온라인 예측을 분리한다.
2. 일반 업무 API와 AI 로직을 분리한다.
3. 정확한 정형 수치는 MySQL, 문서 의미 검색은 ChromaDB에 둔다.
4. ML은 숫자를 예측하고 LLM은 그 근거를 설명·추천한다.
5. LLM에는 검증된 지표, 예측 결과, 검색 문서만 전달한다.
6. 범위가 좁고 검증 가능한 MVP를 먼저 만든다.

### 내부 학습 페이지

```text
로고의 작은 점 → /ml-test
  → GET /ai/v1/ml/learning/catalog
  → region_registry의 등록 지역 순회
  → 모델 metadata.target별 학습 카드 자동 생성
  → 데이터·모델·Feature·함수·평가·3개월 차트 표시
```

`frontend/src/pages/MlTest/`는 팀 학습용 페이지와 전용 CSS만 관리한다. 데이터 설명은 React에
복사하지 않고 AI Server의 저장 모델 메타데이터에서 읽는다. 따라서 모델 Target이 늘어날 때
API 계약을 지키면 같은 페이지에 카드가 자동으로 추가된다.

오른쪽 `ML 챗봇`은 선택 지역의 같은 카탈로그와 서버의 구현 경로 설명을 Responses API에
전달한다. 현재는 짧고 구조화된 프로젝트 정보가 이미 준비되어 있어 RAG·웹 검색을 사용하지 않는다.
수업자료·논문·긴 기술문서가 늘어날 때만 별도 검수 문서 컬렉션을 RAG에 추가한다. OpenAI 키와
프롬프트는 AI Server에만 둔다.

관리자 학습 영역은 `/ml-test`, `/openai-test`, `/react-test` 세 페이지다. OpenAI 페이지는
Python AST로 Agent 클래스와 FastAPI route를 읽고, React 페이지는 `frontend/src`, App route,
fetch endpoint와 package.json 의존성을 읽는다. `project_learning_catalog.py`가 매 요청마다 현재
소스를 다시 스캔하므로 같은 규칙으로 파일·Agent·route를 추가하면 새로고침 후 구조표에 반영된다.
소스 전문·절대경로·`.env` 값은 반환하지 않는다.

`/react-test`는 강사 제공 시스템 구조 설계 자료를 기준으로 현재 로컬 구조와 AWS 예정 구조를
분리한다. 로컬 구조의 `5176 / 8100 / 8111` 포트는 `start-dev.ps1`에서 읽고, React·Backend·AI
Server와 MySQL·Joblib·ChromaDB·OpenAI 연결을 그림으로 표시한다. AWS EC2·Nginx는 아직 연결된
것처럼 표시하지 않고 `planned` 상태로 보여 준다. React 폴더 트리는 `frontend/src` 자동 스캔
결과를 Page·Component·API·Feature·Asset·Core로 묶고 대표 파일만 펼쳐 보게 한다.

`/openai-test`는 5-Agent를 `Evidence + Case Scout 병렬 → Transferability → Planner → Reviewer`로
시각화한다. `/ml-test`는 공식 데이터로 모델을 만드는 오프라인 학습과, 저장 Joblib을 불러오는
온라인 추론을 분리해 웹 요청마다 재학습하지 않는다는 원칙을 보여 준다.

## 2. 기술과 역할

| 영역 | MVP 기술 | 역할 |
|---|---|---|
| 화면 | React + Vite | 대시보드, 입력 폼, 보고서 UI |
| 일반 Backend | FastAPI + Uvicorn | REST API, 검증, CRUD, MySQL 접근 |
| AI Server | FastAPI + Uvicorn | 예측·RAG·LLM 오케스트레이션 |
| DB | MySQL + SQLAlchemy | 월별 지표와 보고서 저장 |
| 분석 | Pandas, NumPy, Matplotlib | 수집·EDA·전처리 |
| ML | scikit-learn + Joblib | 회귀, 평가, 모델 저장 |
| Vector DB | 영속형 ChromaDB | 문서·임베딩·메타데이터 검색 |
| Embedding | OpenAI Embedding (`text-embedding-3-small` 초기 후보) | 한국어 문서를 벡터로 변환 |
| LLM | OpenAI API | 근거 기반 전략을 구조화 JSON으로 생성 |
| 배포 | Nginx + AWS EC2 + systemd | 정적 파일·경로 분배·서비스 실행 |

OpenAI 모델명은 코드에 고정하지 말고 `.env`의 `OPENAI_MODEL`로 설정한다. 실제 평가한 모델·비용·품질은 문서에 기록한다.

## 3. 로컬 개발 구조

```text
[Browser]
    |
    +-- localhost:5176 ---------> [React / Vite]
    |                                  |
    |                                  +-- /api/*
    |                                  +-- /ai/*
    |
    +-- 127.0.0.1:8100/api/* --> [Backend FastAPI]
    |                                  |
    |                                  └--> [MySQL :3306]
    |
    └-- 127.0.0.1:8111/ai/* ---> [AI FastAPI]
                                       ├--> [model.joblib]
                                       ├--> [ChromaDB]
                                       └--> [OpenAI API]
```

개발 중에는 Vite proxy 또는 명시적 API 주소 중 하나를 일관되게 사용한다.

## 4. 배포 구조

```text
[사용자]
    |
[Nginx :80 / :443]
    ├─ /       → React dist/
    ├─ /api/*  → Backend :8000 → MySQL
    └─ /ai/*   → AI Server :8001 → Joblib / ChromaDB / OpenAI
```

MVP는 하나의 EC2에 배포할 수 있다. Backend와 AI Server는 별도 systemd 서비스로 실행하고, MySQL·8000·8001 포트는 외부에 공개하지 않는다.

## 5. 사용자 요청 흐름

```text
지역 선택
  → GET /api/regions/{region_code}/dashboard
  → Backend가 MySQL에서 관측 지표 조회
  → React가 대시보드 표시

업종·타깃·목표 입력 후 [AI 전략 생성]
  → POST /ai/generate-report
  → 검증된 Feature Snapshot 확보
  → 저장된 ML Pipeline으로 다음 달 방문객 예측
  → ChromaDB에서 지역 공식 문서와 검수된 성공사례 검색
  → 공식 웹에서 유사 사업의 실행 방식·예산·관측 성과 조사
  → 사례와 선택 지역의 문제·교통·숙박·상권 조건 적합성 평가
  → 수치 + 예측 + 지역 근거 + 사례 평가를 Prompt에 결합
  → OpenAI Structured JSON 생성
  → React가 보고서·출처 표시
  → 사용자가 저장 선택 시 POST /api/reports
```

AI Server가 Backend의 내부 Feature Snapshot API를 호출할지, Backend가 AI Server를 호출할지는 API 설계 단계에서 확정한다. 브라우저가 보낸 숫자를 LLM이 사실처럼 사용하게 하면 안 된다.

## 6. 오프라인 데이터·ML 파이프라인

```text
공식 CSV / Excel / 허용 API
  → data/raw (원본 보관)
  → 스키마·출처 검증
  → 날짜·지역코드·단위 정규화
  → region_code + year_month 기준 월별 결합
  → Feature Engineering
  → 시간 기준 Train / Validation / Test
  → 기준모델 / LinearRegression / RandomForestRegressor 비교
  → MAE / RMSE / MAPE 평가
  → artifacts/model.joblib + 모델 메타데이터 저장
```

학습은 일반 웹 요청에서 실행하지 않는다. 서비스에서는 저장된 모델을 불러와 예측만 한다.

### 강남구 1차 구현

```text
data/raw/서울특별시/서울특별시_강남구-*.zip (2024~2026, 읽기 전용)
  + test-gangnam-dashboard/download/강남구_* (최신 2026-07 공식 다운로드)
→ ai_server/ml/gangnam_data.py
→ data/processed/gangnam_monthly_demand.csv
→ ai_server/ml/train_gangnam.py (수동 재학습 CLI)
→ 시간순 마지막 4개월 테스트 + seasonal-naive 기준선 비교
→ artifacts/ml/gangnam_demand_model.joblib / metadata.json
→ GET /ai/v1/demo/11680/dashboard
→ 최근 3개월 관측 + 향후 3개월 예측 차트
```

강남구 저장 모델은 방문자·소비액·평균 숙박일·숙박방문 비율·평균 체류시간·내비게이션 검색·숙박검색 7개 Target을 같은 시간 분리 규칙으로 평가한다. Target별 후보모델이 Validation에서 전년 동월 기준선보다 나쁠 때는 기준선을 선택한다. 업종별 소비 패턴은 아직 별도 모델이 아니며 최신 관측 비중을 적용한 표시용 가정이다.

초기 Feature 후보: 전월 방문객, 최근 3개월 평균, 전년 동월 방문객, 전월 관광지출액, 1인당 소비액, 내비게이션 검색량·증가율, 연령대 비율, 월·계절, 공휴일 수, 축제 여부. 실제 데이터로 사용 가능성과 예측 시점 누수를 먼저 확인한다.

## 7. RAG 파이프라인

```text
공식 데이터 정의 / 지역 관광 페이지 / 정책 / 축제 설명
  → 출처 목록 작성 및 문서 정제
  → 제목·문단 기준 Chunk (초기 700~1,000자, overlap 100~150자)
  → Embedding
  → Chroma collection: tourism_official_docs
  → 지역 코드 + 공통 문서 메타데이터 필터, Top 5 검색
  → source_id·제목·URL·날짜를 포함하여 LLM에 전달
```

초기 메타데이터 예시:

```json
{
  "region_code": "string 또는 ALL",
  "region_name": "string",
  "document_type": "data_definition|tourism_page|policy|event|case_study|case_study_budget",
  "title": "문서 제목",
  "source_url": "공식 출처 URL",
  "published_or_updated_at": "알 수 있는 경우 날짜",
  "source_id": "안정적인 내부 ID"
}
```

월별 숫자 테이블은 RAG에 넣지 않는다. 계산과 정확한 수치 조회는 MySQL 또는 Pandas가 맡는다.

공식 성공사례는 `data/rag/official_case_studies.jsonl`에 검수된 사례 카드로 보관한다. 라이브 웹 검색은
최근 사례를 보강하고, RAG는 이미 검수한 사례의 운영 방식·성과·적용 조건을 재사용한다.

## 7-1. 전략 Agent 고정 흐름

```text
Evidence Agent       → 선택 지역 원자료·Open API·지역 정책 근거
Case Scout Agent     → 전국 공식 사업의 운영 방식·예산·관측 결과
Transferability Agent → 지역 적합성 점수와 적용·제외 조건, 시범사업 구조
Planner Agent        → 하나의 구체적인 3~6개월 실행 기획안
Reviewer Agent       → 출처·사례 오용·일반론·실행 가능성 검수
```

Case Scout와 Evidence 수집은 병렬로 실행하고, Planner는 두 결과와 지역 적합성 평가를 모두 받은 뒤에만 작성한다.

## 8. LLM 출력 규약

Prompt는 다음 순서로 구성한다.

```text
역할·환각 방지 규칙
+ MySQL 관측 지표 Snapshot
+ ML 예측값과 모델 버전
+ RAG 문서 Chunk와 source_id
+ 사용자의 업종·타깃·목표
+ 엄격한 JSON Schema
```

주요 응답 필드: `summary`, `observed_findings`, `forecast`, `target_segment`, `problems`, `strategies`, `expected_effects`, `risks_and_limits`, `sources`.

전략에는 행동 항목, 이유, `evidence_source_ids`를 포함한다. 실제 관측값·모델 예측·기대효과를 서로 구분한다.

## 9. Function Calling 범위

핵심 보고서 생성은 정해진 순서의 파이프라인으로 실행한다. 선택 기능인 AI 질의응답에만 읽기 전용 Tool을 둔다.

- `get_region_metrics(region_code, start_month, end_month)`
- `predict_tourism_demand(region_code, target_month)`
- `search_official_context(region_code, query)`

LLM은 DB를 직접 저장·삭제하지 못한다. 보고서 저장은 사용자가 명시적으로 선택한 Backend REST API가 처리한다.
