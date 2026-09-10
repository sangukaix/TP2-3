# 시스템 아키텍처

### 전국 사례와 실행 근거 계약 (D-090 / D-091, 2026-09-07)

```text
지역 관측·SQL·ML → 전국 사례 선택(같은 시도 + 타시도 peer + 운영 원리)
  → Qwen 후보 비교 → 작성 누락 검사 → 필요 시 Qwen 보완 1회
  → Gemma 본문 → 코드 검사·Qwen 검수 → 필요 시 Gemma 수정 1회·재검수
  → 로컬 통과본만 기존 정책의 OpenAI 독립 최종 검수
  → 저장 기획안 + 전체 검증 항목 + 준비할 자료 안내
```

후보 보완은 `local_first`/`student_budget`의 로컬 경로에 적용합니다. 다른 모드의 라우팅·유료 상한은 변경하지 않습니다.
`planning_requirements.py`의 공통 작성 계약과 결정적 검사로 지역 근거 연결·비용 곱셈 산식·KPI 정의 및 일부 명백한 산식 오류를 확인합니다.
검사 통과는 인과효과·협약의 증명이 아닙니다. `needs_evidence`를 강제로 `ready`로 바꾸지 않습니다.
수정 입력은 실제 후보의 지역 사실/사례 ID와 보완 사례 원문을 함께 보존합니다. 오래된 RAG의 동일 사례 요약보다 최신 교정 사례 카드를 우선합니다.
로컬 전달 시 반복 JSON 행은 `context_tables.py`의 무손실 열/행 표로 바꾸고, 동일한 관측/선택 후보는 한 번만 보냅니다. 표 복원 결과는 원본과 동일하며 원본 도구 저장소·수치·출처·필수 조회·출력/문맥 상한은 유지합니다. 오프라인 사전검사와 실제 모델 품질 검증은 구분합니다.
[전국 범위·필터](NATIONWIDE_CASE_SELECTION.md), [원주 실제 기록·자료 요청](WONJU_PROPOSAL_QUALITY_AUDIT_20260907.md).

### 생성·출력 안정성 보완 (D-064)

`report_projection.py`가 최종 기획 기간의 저장 ML 행과 명시적 사용자 목표를 Word/PPT에 공통 공급한다. `report_review_status.py`는 표지의 검수 상태를 통일한다. 문서 렌더링은 스레드에서 실행하며 공유 렌더러는 잠금으로 보호한다. 본문 저장과 형식별 파일 생성 실패를 분리하고, 실제 렌더 입력 지문으로 캐시를 검증한다. 저장 모델 선택은 유지하며 `model_reliability`와 소비/방문 비율의 표본 미검증 정보를 Agent에 전달한다. 검증 결과와 추가 ML 우선순위는 [재검토 기록](GENERATION_REVIEW_20260902.md)을 참조한다.

### 현재 적용: 로컬 우선 품질 파이프라인 (D-063)

`로컬 연결 확인 → 수치/ML 사실표 + 공식 근거 재사용/필요 시 조사 → Qwen 후보 비교 → Gemma 작성 → 코드+Qwen 검수 → 필요 시 Gemma 수정+Qwen 재검수 → 통과 시 OpenAI 최종 검수 1회`.

기본 `student_budget`은 유료 자동 대체와 OpenAI Web Search 자동 실행을 차단하고, 생성 1건의 OpenAI 요청을 로컬 검수 통과본의 독립 최종 검수 **1회**로 제한한다. 선택적으로 Qwen이 최대 2개의 짧은 검색 질문을 JSON으로 설계하면, 서버의 `OfficialWebSearchClient`가 무료 API(Tavily, 선택적으로 Brave)로 허용된 공식 도메인의 제목·URL·요약 후보만 조회한다. Naver 검색 API는 결과 독립 노출 약관 때문에 LLM 내부 입력에 쓰지 않는다. Qwen·Gemma는 인터넷·DB·파일에 직접 접근하지 않으며, 검색 요약은 원문 검수 전 확정 근거·RAG 저장 대상이 아니다. 지역 사실은 MySQL·ML·공식 Open API, 문서 근거는 검수 JSONL/PDF RAG, 비교·초안·재검수는 Qwen·Gemma가 담당한다. 저장 근거가 부족한 결과는 승인하지 않는다. `local_first`는 최신 공식 웹 조사·사례 보강이 꼭 필요할 때만 최대 3회(OpenAI 지역 조사, 사례 조사/보강, 최종 검수)를 허용한다. 두 모드 모두 유료 자동 대체를 허용하지 않는다. RAG 조회는 유료 임베딩 없는 키워드 검색이며 의미 검색과 동등한 성능은 아직 검증하지 않았다. [계획 및 정확한 적용 범위](LOCAL_FIRST_QUALITY_PLAN.md).

로컬 최종 작성에는 원문 조회를 마친 공식 사례 ID만 허용 목록으로 전달한다. Qwen·Gemma가 요청 목록에만 있던 다른 사례를 최종안에 인용하면 AI Server가 해당 요청 범위의 원문을 읽고 같은 로컬 모델에 구조화 JSON 교정을 한 번만 요청한다. 두 번째 새 미조회 사례, 너무 큰 원문, Schema 위반이 남으면 채택하지 않는다. 이 복구 경로는 OpenAI 호출이나 LLM의 파일·DB·웹 권한을 늘리지 않는다.

도구 선택과 최종 보고서 출력 예산은 분리한다. 함수명·인자 선택은 512토큰으로 제한하며, 이 선택 단계가 장문 응답으로 미완료여도 서버가 필수 근거를 전부 사전조회한 상태라면 실패 사용량을 기록하고 최종 Schema 작성으로 넘어간다. 필수 조회가 남아 있으면 우회하지 않는다. 따라서 선택 단계의 불필요한 서술이 초안을 폐기하지 않으면서도, 근거가 빠진 결과나 잘린 최종 JSON을 허용하지 않는다.

최종 JSON이 역할별 출력 상한에서 끝나지 않으면 부분 문자열을 이어 붙이지 않는다. 같은 원문·Schema·출력 상한에 간결한 완전 응답 지시만 추가해 로컬 모델을 한 번 다시 실행하고, 두 번째 미완료는 실패로 남긴다. 이는 OpenAI 대체 호출이나 출력 상한 증가가 아니다.

아래 D-060~062의 자동 유료 폴백·반복 검수 설명은 기존 `hybrid` 동작이며 `local_first`에 적용하지 않는다.

### 2026-09-02 생성 품질 검토 반영

후속 토큰 보완: 5-Agent의 출력 상한을 조정하고 OpenAI의 토큰 부족 응답에만 같은 단계 1회 재시도를 적용한다.
Ollama 출력 예산·문맥 크기와 학습 챗봇 설정은 분리해 유지한다. 재시도 중에도 원문 근거·JSON Schema·공식 검색 검증을
완화하지 않으며 실패/재시도 사용량을 합산한다. 상세 수치·비용/시간 경계는 `GENERATION_TOKEN_BUDGETS.md` 참조.

`ZIP/저장 모델 + MySQL peer 비교 → 지역 근거·공식 사례 동시 조사 → Qwen 후보 2~3개 비교 → Gemma 통합 실행안 → 코드 검사 + OpenAI 독립 검수 → 최대 한 번 수정 → 검수 상태·선정 근거를 포함해 저장/미리보기`.

긴 입력·로컬 오류는 근거를 자르지 않고 OpenAI로 폴백할 수 있다. ML의 자연추세는 사업 인과효과가 아니며, 문맥 크기·출력 상한·사용량을 추적한다. 현재 Chroma 문서는 0건으로 의미 검색 지식베이스가 구축 완료된 상태는 아니지만, 검수한 공식 PDF 요약 3건은 `official_reference_documents.jsonl`에서 무료 키워드 RAG로 조회한다. 검수 카드와 공식 웹 조사 경로를 함께 사용한다. 상세 상태는 `GENERATION_READINESS_20260902.md` 참조.

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

### Hybrid Multi-LLM 실행 경로

```text
5-Agent / 지역 챗봇
  → LLMRouter (mode + 작업별 capability 확인)
      ├─ Evidence·Case Study → OpenAI Responses + 공식 Web Search
      ├─ Reviewer → OpenAI Responses (독립 검수)
      ├─ Transferability → Qwen + 요청 내 읽기 전용 근거 도구
      ├─ Planner·보완 → Gemma + 요청 내 읽기 전용 근거 도구
      ├─ 설명·수정 챗봇 → 기존 Qwen·Gemma JSON 경로
      └─ 로컬 연결·JSON 실패 → OpenAI 폴백 (Web Search 작업은 제외)
  → 구조화 JSON → Pydantic/품질 게이트 → agent_trace
```

Provider 설정은 `.env` 이름과 별도 `storage/llm_runtime_config.json`의 안전한 라우팅 값으로 분리한다.
Ollama IP·OpenAI 키는 React에 전달하지 않는다. `GET /ai/v1/llm/status`는 상태·모델 태그·capability를,
`/llm-control`은 성공·실패·폴백·근거 도구 조회 기록을 보여 준다. ACTIVE는 연결 상태이지 추론 성공이 아니다.

오른쪽 `ML 챗봇`은 선택 지역의 같은 카탈로그와 서버의 구현 경로 설명을 Responses API에
전달한다. 현재는 짧고 구조화된 프로젝트 정보가 이미 준비되어 있어 RAG·웹 검색을 사용하지 않는다.
수업자료·논문·긴 기술문서가 늘어날 때만 별도 검수 문서 컬렉션을 RAG에 추가한다. OpenAI 키와
프롬프트는 AI Server에만 둔다.

학습 챗봇의 답변은 보고서 생성과 분리해 `reasoning=low`, `text.verbosity=low`,
`max_output_tokens=800`으로 호출한다. 답변은 4문장·핵심 포인트 3개·관련 파일 3개 이내다.
`GET /ai/v1/learning/assistant-status`는 AI Server와 OpenAI 모델 연결을 Models API로 확인하며,
토큰을 생성하지 않는다. 프런트엔드는 30초마다 상태를 갱신하고, 실제 답변 실패도 즉시 `Inactive`로 표시한다.

관리자 학습 영역은 `/ml-test`, `/openai-test`, `/react-test` 세 페이지다. OpenAI 페이지는
Python AST로 Agent 클래스와 FastAPI route를 읽고, React 페이지는 `frontend/src`, App route,
fetch endpoint와 package.json 의존성을 읽는다. `project_learning_catalog.py`가 매 요청마다 현재
소스를 다시 스캔하므로 같은 규칙으로 파일·Agent·route를 추가하면 새로고침 후 구조표에 반영된다.
소스 전문·절대경로·`.env` 값은 반환하지 않는다.

`/react-test`는 강사 제공 시스템 구조 설계 자료를 기준으로 현재 로컬 구조와 AWS 예정 구조를
분리한다. 로컬 구조의 `5176 / 8100 / 8112` 포트는 `start-dev.ps1`에서 읽고, React·Backend·AI
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
    └-- 127.0.0.1:8112/ai/* ---> [AI FastAPI]
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

### 등록 지역 ML 구현

```text
data/source_snapshots/서울특별시/서울특별시_강남구/ (2024~2026, hash 검증·읽기 전용)
  + supplemental_202607/강남구_* (최신 2026-07 공식 다운로드의 hash 검증 복제본)
→ ai_server/ml/gangnam_data.py
→ data/processed/gangnam_monthly_demand.csv
→ ai_server/ml/train_gangnam.py (수동 재학습 CLI)
→ 시간순 마지막 4개월 테스트 + seasonal-naive 기준선 비교
→ artifacts/ml/gangnam_demand_model.joblib / metadata.json
→ GET /ai/v1/demo/11680/dashboard
→ 최근 3개월 관측 + 향후 3개월 예측 차트
```

직접 내려받은 CSV 구조가 같은 지역은 `ai_server/ml/regional_datalab_data.py`가 공통 열 정의를 검증하고,
`<region>_data.py`는 지역 코드·원본 위치만 선언한다. `RegionForecastSettings`는 지역별 Joblib·메타데이터
경로를 분리한다. 현재 계양구(`28245`, 2024.01~2026.06)도 이 경로로 등록되어 있다. 새 시군구는 24개월 이상
공통 Target, 월 연속성, 지역 코드, 시간순 기준선 비교를 통과한 뒤에만 `region_registry.py`에 등록한다.
`_build_registered_ml_dashboard()`는 등록 지역에 같은 카드·그래프·소비 패턴 UI를 적용하고, 등록되지 않은
지역은 예측을 만들지 않은 관측 원자료 대시보드를 그대로 사용한다.

### 지역 확장 카탈로그와 사전점검

```text
공식 원본을 data/raw/<시도>/<시군구> 또는 data/source_snapshots/<시도>/<시군구>에 불변 보관
  → data/catalog/region_data_registry.csv에 코드·경로·출처 상태 등록
  → check_regions.py: 경로·7개 Target·월 연속성·관측 기간 점검 (읽기 전용)
  → standard_region_pipeline.py: 표준 CSV·category ZIP을 공통 학습 함수로 연결
  → train_regions.py: 지역 코드별 Joblib·메타데이터 저장
  → region_registry.py: 해당 지역만 대시보드·기획 근거에 등록
  → GET /ai/v1/regions/catalog: 원본·모델이 모두 준비된 지역만 React 선택기에 전달
```

`data/raw/`와 기존 `data/raw/SOURCE_REGISTRY.csv`는 수정하지 않는다. 활성 ML은 `data/source_snapshots/`를 읽으며, 원본마다 정확한 공식 다운로드 URL,
다운로드 날짜, 이용 조건을 팀이 카탈로그에 기록하고 `provenance_status=verified`로 확인하기 전에는
`ready_with_provenance_warnings`를 유지한다. 코드가 출처를 추정하거나 검증 완료로 바꾸지 않는다.

2026-09-04 기준 서울 25개 자치구(강남구 포함), 강원 17개 시군구, 경기도 43개, 경상남도 3개,
인천 계양구까지 총 89개 지역이 이 경로로 원본·시간순 ML·대시보드까지 준비돼 있다. 양양군은
2025년 방문자 archive가 빠져 있어 비활성 상태이며, 누락 원본을 보완하고 같은 사전점검·학습을
마치기 전에는 선택 목록에 넣지 않는다.

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
현재 검수 카드는 강진 반값여행, 디지털 관광주민증, 야간관광 특화도시 성과,
전주시 야간관광 예산서 4건이다. 전국 월별 수치가 늘어도 사례 문서는 자동으로 늘지 않으므로
`check_case_registry` 검증을 통과한 공식 성과·예산·운영 문서를 별도로 추가한다.

공식 PDF의 정책·운영·지표 해석은 `data/rag/official_reference_documents.jsonl`에 원문 SHA-256·공식 URL·쪽수와 함께
짧은 검수 요약으로 보관한다. `OfficialTourismRagStore`는 ChromaDB가 비어 있거나 `local_first`일 때도 이 레지스트리를
키워드로 검색한다. 월별 수치표, 향후 공개 예정 화면, 가상 예시는 이 경로에 넣지 않는다.

전국 확장 시 원본·전처리 수치·지역 모델·정책 문서를 한 저장소에 섞지 않는다. 자세한 현재/운영 구조는
`docs/NATIONAL_DATA_AND_CASE_STORAGE.md`를 따른다.

## 7-1. 전략 Agent 고정 흐름

```text
Evidence Agent       → 선택 지역 원자료·Open API·지역 정책 근거
Case Scout Agent     → 전국 공식 사업의 운영 방식·예산·관측 결과
Transferability Agent → 지역 적합성 점수와 적용·제외 조건, 시범사업 구조
Planner Agent        → 하나의 구체적인 3~6개월 실행 기획안
Reviewer Agent       → 출처·사례 오용·일반론·실행 가능성 검수
```

Case Scout와 Evidence 수집은 병렬로 실행하고, Planner는 두 결과와 지역 적합성 평가를 모두 받은 뒤에만 작성한다.

### 전략기획 작업 영속화

`strategy_report_jobs`는 queued/running/completed/failed 상태와 첨부 본문을 제거한 요청 조건을 MySQL에
저장한다. AI Server 재시작 시 첨부가 없던 작업은 다시 예약하고, 첨부가 있던 작업은 본문 비저장 원칙상
자동 복구하지 않고 재요청을 안내한다. 완료 결과는 `strategy_reports`, Word/PPT는 서버 문서 저장소에 보관한다.

PowerPoint는 사용자가 승인한 최신 디자인을 확장한
`ai_server/app/templates/tourism_strategy_12_slide_template.pptx`의 편집 가능한 도형·텍스트·표·차트를 공개 출력에 사용한다.
`proposal_presentation.py`가 호환 진입점을 제공하고, `proposal_presentation_v4.py`가 보고서 JSON을 각 슬라이드에
매핑한다. 글꼴 크기·정렬·마지막 장의 위치는 템플릿에 확정하여 생성 때 다시 변경하지 않는다.
구형 `proposal_presentation_v3.py`를 직접 호출하는 재현 경로는 `tourism_strategy_12_slide_template_legacy_v1.pptx`를 사용해 새 템플릿과 shape 계약이 섞이지 않게 한다.
4장은 선정 후보의 작동 방식·대상·시범 범위·필요 자원·최종 산출물을 설명한다. 6장은 실제 `comparison_analysis`, 선정 후보·공식 사례의 적용 판단을 사용한다. 전년동월 방문 증감률이 있는 경우에만
같은 지역의 `전년동월=100` 상대 지수를 그리며, 이를 타 지역 비교나 정책 효과로 표시하지 않는다.
9장은 견적 산식과 편집 가능한 표를 유지하고, 10장은 시범 종료 후 정례 운영·월별 개선·단계적 확장을 제시한다.
4장은 기획의 구성요소를 병렬 설명하고, 7장은 같은 4열 구성을 반복하지 않는다. 7장은 `implementation_steps`의 앞 4단계를 우상향 실행 여정으로 배치하고 다섯 번째 단계를 왼쪽 최종 산출물 레일에 연결한다. 도형 이름은 `step-0~3-label/title/body`, `value-panel`, `value-title`, `value-body` 계약을 유지한다. 11장은 관측 데이터·저장 ML·공식 사례/웹 근거·AI 공급자를 `evidence_sources`, 모델 metadata, `agent_trace`에서 읽어 구분하고, 12장은 인사 장으로 마무리한다.
3장 지역 사진 프레임에는 해당 지역의 한국관광공사 관광 Open API 결과 중
관광지·문화시설·축제·레포츠를 우선 배치하며, 이미지가 없으면 다른 지역 사진을 재사용하지 않고 중립 템플릿 이미지를 쓴다.
ML 비교 차트는 저장 모델의 자연추세와 사용자가 직접 입력한 목표만 네이티브 차트로 표시한다. 자연추세와 목표의
차이는 정책 미실행 반사실·사업 인과효과·보장 성과로 해석하지 않는다. 등록 ML이 없는 지역은 수치를 만들지 않고
미지원 상태를 표시한다.

Word/PPT 캐시는 보고서 내용 지문과 문서 렌더 버전을 함께 저장한다. 보고서가 수정되거나 템플릿·생성기 버전이
바뀌면 기존 파일 경로를 무효화하고 다시 생성하여, 이전 슬라이드 구성이나 오래된 보고서가 다운로드되는 것을 막는다.

Word의 비교 그래프는 저장 ML의 자연추세만 예측으로 표시한다. 사용자가 목표율을 직접 입력한 경우에만
별도 목표선을 산술 계산하며, 정책 미실행 반사실·사업효과·추가 매출 예측으로 부르지 않는다.

등록 ML 지역의 AI snapshot은 `region_registry`의 `load_history()`를 관측 기준으로 재사용한다.
따라서 최신월 보완 ZIP이 있는 강남구도 화면·기획안 관측값·ML 전망이 같은 마지막 확정월을 사용한다.
SNS처럼 별도 원본의 공개가 늦은 지표는 값을 최신월로 당기지 않고 해당 지표의 실제 기준월을 함께 표시한다.

Planner 자동 재작성에는 검수받은 기존 초안을 반드시 전달한다. 최초 작성처럼 40여 개 근거 전체를 다시
전송하지 않고, 관측값·ML·사용자 조건과 기존 초안이 인용했거나 Transferability가 추천한 사례를 중심으로
최대 16개 출처를 전달한다. 재작성은 `medium` 추론으로 지적 필드만 고쳐 출력 중단과 비용을 줄인다.

### 기획안 결정적 품질 게이트

```text
Planner 구조화 JSON
  → plan_quality_gate.py
      ├─ 실제 source_id 인용 여부
      ├─ 정확히 5개 집행 단계와 일정·행동·산출물
      ├─ 대상·참여/혜택/운영 방식의 구체성
      ├─ 비용 항목×수량×단가 또는 비교견적 산식
      └─ 기준월·주기·원자료가 있는 KPI
  → Reviewer Agent
  → 미달 시 Planner 1회 보완 → 최종 Reviewer
```

이 게이트는 기획 내용을 새로 만들지 않는다. 코드로 판정 가능한 누락만 Reviewer와 Planner에게 전달해,
그럴듯하지만 출처·집행 방식이 비어 있는 결과가 승인되는 것을 막는다.

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

핵심 보고서 생성은 정해진 순서의 파이프라인으로 실행한다. D-062부터 Qwen 적용성 검토와 Gemma 기획·보완에도 요청 범위 읽기 전용 Tool을 둔다. Agent 순서를 스스로 바꾸는 무제한 자율 실행은 아니다.

- `get_region_metrics(region_code, start_month, end_month)`
- `predict_tourism_demand(region_code, target_month)`
- `search_official_context(region_code, query)`

LLM은 DB를 직접 저장·삭제하지 못한다. 보고서 저장은 사용자가 명시적으로 선택한 Backend REST API가 처리한다.

위 질의응답용 인터페이스와 별개로, 구현된 로컬 기획 Tool은 `llm/evidence_tools.py`의 9개 허용 함수다. 서버가 이미 계산·수집한 snapshot·ML·공식 사례·선정 판단·초안을 요청 메모리에서 조회한다. 웹 크롤링·SQL 실행·파일 열기·재학습 권한은 없다. 자세한 명칭과 계약은 [로컬 Agent 도구](LOCAL_AGENT_TOOLS.md)를 따른다.

### 지역별 관광 현황 보조 근거 흐름 (2026-09-03)

```text
공유 원본 ZIP(불변 snapshot)
  → 전수 검증·정규화(data/processed/regional_tourism_status)
  → MySQL 지역 현황 사실 테이블
  → AI Server의 작은 region context 캐시
  → Evidence Agent / Qwen·Gemma 읽기 전용 근거 Tool
  → 후보의 권역·장소·혼잡 분산 운영 조건
```

이 흐름은 기존 월별 ML 파이프라인과 병렬이다. 유입·유출과 인기 순위는 후보의 운영 범위를
구체화하는 관측 근거이고, 향후 30일 집중률은 현장 운영 참고 신호다. 어느 값도 예측 target,
정책효과, 보장 수요로 승격하지 않으며 LLM은 DB·원본 파일·외부 URL을 직접 읽지 못한다.

### 전국 빅데이터 기간집계 보조 근거 흐름 (2026-09-04)

```text
공유 원본 ZIP 20개(불변 hash snapshot)
  → 시군구 기간합계/비중 + 전국 월별 추이 분리 정규화
  → MySQL nationwide_*_context 보조 테이블
  → AI Server의 작은 선택지역 context
  → Qwen·Gemma get_nationwide_bigdata_context 읽기 전용 Tool
  → 외국인·내국인·검색 관심도의 범위 확인 보조 신호
```

시군구 연간/반기 집계는 지역 월별 사실이나 ML target/feature가 아니며, 전국 월별 추이도
선택 지역의 실적·예측·전국 평균이 아니다. 두 자료는 RAG에 넣지 않고, 기간·단위·출처 상태를
보존한 보조 진단에만 사용한다. 모델은 DB·원본 ZIP에 직접 접근하지 못한다.
