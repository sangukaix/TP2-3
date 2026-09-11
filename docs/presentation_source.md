# STAY-UP AI 발표자료 원본

> 작성 기준: 2026-09-08, `C:\Users\Admin\mbca\TP2-3`의 현재 작업 트리와 실행 중인 로컬 서비스. **최종 발표 PPT를 만들기 위한 자료이며, PPT 파일 자체는 생성하지 않았다.** 기존 소스·데이터·보고서·모델·승인 상태를 변경하지 않았다.

## 0. 읽는 법과 검증 범위

실제 코드 → 실행 응답·DB·모델 산출물 → 실측 기록 → 기존 설명 문서 순으로 판단했다. 필수 문서는 PROJECT_BRIEF, ARCHITECTURE, DATA_AND_AI_RULES, IMPLEMENTATION_PLAN, CONTEST_EVIDENCE, DECISIONS 순서로 확인했다. 저장소의 주요 폴더와 파일 목록을 조사하고, 페이지→API→처리 함수→데이터/모델 경로를 추적했다. 의존성·캐시 내부의 모든 파일을 개별 검토했다는 뜻은 아니다.

| 표시 | 의미 |
|---|---|
| ✅ 구현 완료 | 해당 범위의 구현과 이번 읽기 전용 확인 또는 명시한 기존 산출물로 확인 가능. 서비스 전체의 운영 승인과는 다르다. |
| 🟡 일부 구현 / 테스트 단계 | 흐름은 있으나 품질·범위·통합 검증이 남았다. |
| 🔴 미구현 / 기획 단계 | 사용자에게 제공하는 구현 또는 실사용 근거가 없다. |
| ⚪ 코드만 존재하지만 실제 동작 여부 확인 필요 | 코드 경로는 확인했으나 현재 환경에서 해당 동작을 실행·검증하지 않았다. |

이번 확인은 GET 요청, 코드·메타데이터 읽기, MySQL 읽기 전용 트랜잭션으로 수행했다. 신규 LLM 생성·유료 생성·모델 학습·DB 쓰기·문서 다운로드/재생성·관리자 설정 변경은 실행하지 않았다. 브라우저 화면의 시각적 검수, 전체 테스트 재실행, lint/build, 배포 검증도 이번 문서 작업에서는 수행하지 않았다. 아래의 HTTP 200은 화면 전체 및 AI 결과 품질 검증을 뜻하지 않는다.

### 발표자가 먼저 알아야 할 사실

- 현재 카탈로그는 **활성 89개 지역**이다. 지도에 보이는 전국 모든 지역이 예측·기획 생성 지원 지역이라는 뜻은 아니다.
- 일반 Backend는 주로 **지도 경계**를 제공한다. 관광 데이터·MySQL 조회·ML·LLM은 **AI Server**에 모여 있다. React가 `/api`와 `/ai`를 각각 호출한다.
- 현재 런타임 모드는 **`local_first`**다. 문서/기본 설정의 `student_budget`와 구분해야 한다.
- Qwen은 후보 비교·적용성·검토, Gemma는 기획 본문 작성·수정을 담당한다. OpenAI 공식 웹 조사와 최종 검토 경로도 남아 있다. **완전 무료·완전 오프라인 서비스가 아니다.**
- 월별 데이터는 다운로드한 원자료/파생 파일과 MySQL을 함께 사용한다. 모든 수치가 실시간 API 또는 MySQL에서만 오는 구조가 아니다.
- 직접 학습한 ML이 있으나 지역·지표별로 기준모델 대비 성능이 다르다. 원주 현재 선택 모델은 방문자·소비액 테스트에서 기준모델보다 나쁘다.
- 원주 저장 보고서 `0cb052838f0d4ab983891649fdf6a47b`는 **승인되지 않았다**. 저장·문서화 기능과 기획 품질 승인을 혼동하면 안 된다.
- Chroma 저장 파일은 있지만 확인 당시 임베딩은 0개다. 현재 활용 근거는 로컬 공식 문서 청크·요약·사례 카드 검색이다. 대규모 벡터 검색이 검증됐다고 발표하면 안 된다.
- DOCX/PPTX 생성 코드는 존재한다. PDF 출력 API는 확인되지 않았다. Nginx/AWS 운영 배포 완료 근거도 없다.

### 읽기 전용 실측 요약

| 대상 | 확인 결과 | 해석 범위 |
|---|---|---|
| Backend `8100/health` | 200 | 프로세스 응답 |
| AI Server `8111/ai/health` | 200 | 프로세스 응답 |
| React `5176/` | 200 | 개발 서버 HTML 제공 |
| Streamlit `8501/_stcore/health` | 200 | 구조 탐색 보조 서비스 실행 |
| 지역 카탈로그 | 200, 활성 89개, 모두 `model_ready=true` | 카탈로그/아티팩트 준비, 예측 우수성 보장 아님 |
| 저장 보고서 목록 | 200, 5개 | MySQL 저장·조회 연결 |
| 원주 보고서 상세 | 200, `approved=false`, score 81, 최종 감사 미완료 | 81점만 잘라 승인/성공으로 소개 금지 |
| 원주 대시보드 | 지역명 포함 요청 200 | 현재 대표 지역 조회·예측 경로 확인 |
| 원주 생성 준비도 | `can_generate=true`, 마지막 관측 2026-06 | 데이터 시점 조건 통과, 기획 품질 통과 아님 |
| 원주 ML planning evidence | 200 | ML 판단 근거 제공 |
| LLM 상태 | `local_first`, Qwen/Gemma active | 연결·모델 태그 확인, 신규 생성 성공 확인 아님 |
| 전 지역 준비도 감사 | 200, 2026-09-07 캐시 | 이번에 89지역 전체를 새로 실행한 결과 아님 |

---

## 1. 전체 프로젝트 구조

```text
TP2-3/
├─ frontend/                  React + Vite 업무 화면
│  └─ src/{pages,components,features,api,assets}
├─ backend/                   일반 FastAPI: VWorld 경계 제공
│  └─ app/{main.py,config.py,services/vworld.py}
├─ ai_server/
│  ├─ app/                    관광 조회·기획·문서·LLM 제어 API
│  │  ├─ agents/              조사→후보 비교→작성→검토
│  │  ├─ llm/                 Router, OpenAI/Ollama Provider, trace
│  │  ├─ scripts/             진단·감사·공식 PDF 처리 도구
│  │  └─ templates/           기획서 출력용 PPT 템플릿/이전 버전
│  └─ ml/                     지역 등록·전처리·학습·평가·예측
├─ data_pipeline/             원자료 인벤토리·압축 해제·정제·SQL 적재
│  ├─ tools/
│  └─ nationwide_ml/          별도 전국 패널/기준모델 실험
├─ database/mysql/            관광·출처·비교·측정 SQL 스키마
├─ data/
│  ├─ raw/                    공식 원본 보관
│  ├─ source_snapshots/       로컬 원본 스냅샷
│  ├─ catalog/                지역/출처 등록 CSV
│  ├─ interim/                중간 변환 산출물
│  ├─ processed/              전국·지역현황·ML 파생 데이터
│  ├─ rag/                    공식 문서 청크·요약·사례 카드
│  └─ chroma/                 Chroma 내부 영속 저장소
├─ artifacts/                 Joblib 모델·평가·메타데이터·진단 산출물
├─ storage/                   저장 보고서 파일·출력 검수물·LLM 설정
├─ project_tree_explorer/     별도 Streamlit/CLI 구조 탐색 도구
├─ tests/nationwide_pipeline/ 데이터 처리·ML·저장 검증
├─ docs/                      설계·결정·실측·이번 발표 원본
├─ references/               수업/참고 자료
├─ test-gangnam-dashboard/    별도 화면 실험 자료; 메인 앱과 구분
├─ setup-dev.ps1 / start-dev.ps1
├─ requirements.txt / README.md / AGENTS.md
└─ .env                      비밀 설정; 발표/문서에 값 공개 금지
```

```text
사용자 → React
          ├─ /api → 일반 Backend → VWorld → 지도 경계
          └─ /ai  → AI Server
                    ├─ 원자료/파생 JSON + MySQL → 관광 지표/비교
                    ├─ 저장 Joblib → ML 예측/평가
                    ├─ TourAPI + 공식 문서/사례 → 근거
                    ├─ Agent + LLM Router → 기획 초안/검토
                    └─ MySQL 보고서 + 로컬 DOCX/PPTX → 조회/출력
별도: React /project-tree → Streamlit 구조 탐색기
```

`artifacts`, `storage`, 템플릿의 이전 버전을 전부 현재 서비스 엔진으로 소개하지 않는다. 현재 import·호출 경로를 기준으로 구분한다.

## 2. 프로젝트 정의

### 한 문장

**STAY-UP AI는 지자체 관광 담당자와 관광 소상공인이 공식 관광지표와 방문·소비 예측, 공식 사례 근거를 함께 검토하여 지역 관광사업 기획 초안을 작성하도록 돕는 서비스다.**

### 3줄

1. 지역을 선택하면 방문·소비·체류 지표와 저장된 ML 모델의 예측을 확인한다.
2. 예산·기간·현장 여건을 입력하면 공식 자료와 사례를 바탕으로 LLM이 후보를 비교하고 기획 초안을 작성·검토한다.
3. 결과를 출처·검토 상태와 함께 조회하고 저장·문서화할 수 있으며, 현재 기획 품질 검증은 진행 중이다.

### 발표용 30초

“관광객이 많이 방문하는 것과 지역에서 오래 머물며 소비하는 것은 다른 문제입니다. STAY-UP AI는 지자체 담당자가 공식 관광데이터로 지역 상황을 확인하고, 직접 학습한 모델의 예측과 공식 정책 사례를 함께 검토하도록 돕습니다. 예산과 사업 여건을 입력하면 Qwen이 후보를 비교하고 Gemma가 기획 초안을 작성합니다. 출처와 검토 결과를 남기고 Word와 PowerPoint 문서로 연결하는 업무 흐름을 구현했으며, 생성 기획안의 실제 타당성은 계속 검증하고 있습니다.”

## 3. 개발 목적과 문제 정의

| 항목 | 확인 가능한 설명 |
|---|---|
| 해결하려는 문제 | 방문·관심 지표를 체류·소비와 연결해 해석하고 지역 여건에 맞는 관광사업 검토 자료를 만드는 과정 |
| 기존 방식의 문제 | 데이터 조회, 예측, 사례 조사, 문서 작성이 분리되는 업무를 통합하려는 설계. 실제 담당자의 평균 소요시간·불편 빈도는 **기획서 확인 필요** |
| 사용자 | 지자체 관광 담당자, 관광 소상공인. 일반 여행자의 일정 추천 서비스가 아님 |
| 얻는 결과 | 지역 지표, 예측과 평가 한계, 사업 조건, 사례·출처, 실행 단계가 있는 검토용 기획 초안 |
| 핵심 가치 | 관측·예측·목표를 구분하고, 숫자와 문서 근거를 함께 확인할 수 있는 업무 연결 |
| 최종 목표 | 근거 확인부터 기획·저장·후속 측정까지 연결. 현재 후속 성과 자료·운영 배포·기획 품질 검증 미완료 |
| 확인되지 않은 주장 | 실제 매출 상승, 정책 효과, 업무시간 절감률, 이용기관 수, 시장 점유율, 경쟁제품 대비 우위: **기획서 확인 필요** |

## 4. 주요 기능 전체 조사

이 절의 Backend는 일반 Backend와 AI Server를 구분한다. 각 상태의 구체적 검증 범위를 함께 읽어야 한다.

### 4.1 메인 화면과 업무 진입

- **사용자에게 보이는 기능:** 서비스 소개, 관광 데이터/기획 업무로 이동.
- **동작 방식:** `App.jsx`의 pathname 분기와 lazy import로 페이지 표시.
- **Frontend:** `TourismHomePage.jsx`, `WorkspaceShell.jsx`.
- **Backend:** 페이지 진입은 Vite; 관광 요청은 다음 페이지에서 API 호출.
- **AI / Data:** 메인 소개 문구 자체는 AI 추론 아님.
- **사용하는 API:** 진입 후 지역 카탈로그 등.
- **관련 파일:** `frontend/src/App.jsx`, `frontend/src/pages/TourismHomePage.jsx`.
- **현재 구현 상태:** ✅ 코드 및 루트 HTTP 200 확인. 시각적 QA는 미실시.
- **발표 가치:** 여행 추천 앱이 아닌 담당자 업무 도구라는 목적 소개.

### 4.2 지도·지역 선택

- **사용자에게 보이는 기능:** 시도/시군구 지도 선택과 지역 선택 목록.
- **동작 방식:** VWorld GeoJSON을 Leaflet에 표시하고 지역 코드로 조회. 선택 지역 일부 상태는 localStorage에 보관.
- **Frontend:** `RegionWorkspacePicker.jsx`, `TourismDashboardPage.jsx`, `tourismWorkspace.js`.
- **Backend:** `backend/app/main.py`, `services/vworld.py`; 경계를 코드별 MultiPolygon으로 병합·단순화하고 24시간 캐시.
- **AI / Data:** 지역 카탈로그와 지도 경계는 별개. 활성 ML 지역 89개.
- **사용하는 API:** `/api/v1/boundaries/sido`, `/sigungu`, `/ai/v1/regions/catalog`.
- **관련 파일:** 위 파일 및 `ai_server/ml/region_catalog.py`, `region_registry.py`.
- **현재 구현 상태:** 🟡 카탈로그 조회 확인, 이번 지도 상호작용/외부 경계 재조회는 미검증.
- **발표 가치:** 지역명 자유 추측 대신 등록 코드로 데이터와 모델 연결.

### 4.3 관광 대시보드·차트·지역 비교

- **사용자에게 보이는 기능:** 예상 방문자·소비·숙박 카드, 월별 추이, 소비 구성, 지역 진단/비교.
- **동작 방식:** 원자료 시계열과 저장 모델 예측을 조합. 업종별 예상 소비는 전체 소비 예측에 최신 업종 비중을 적용한 가정.
- **Frontend:** Recharts ComposedChart/PieChart, 범례·툴팁·빈 데이터 안내.
- **Backend:** 일반 Backend는 지도만; AI Server가 dashboard/sido-comparison 제공.
- **AI / Data:** 지역 CSV/스냅샷, 모델, MySQL 비교 문맥. 조회 자체에 LLM 불필요.
- **사용하는 API:** `/ai/v1/demo/{code}/dashboard?region_name=...`, `/ai/v1/demo/sido-comparison`.
- **관련 파일:** `TourismDashboardPage.jsx`, `ai_server/app/main.py`, `ai_server/ml/gangnam_forecast.py`.
- **현재 구현 상태:** ✅ 원주 dashboard 200과 예측 응답 확인. 전 지역 화면 동작은 별도.
- **발표 가치:** 데이터와 예측을 즉시 볼 수 있는 가장 안정적인 핵심 데모.

### 4.4 지역 현황·관광자원·공식 근거 조회

- **사용자에게 보이는 기능:** 선택 지역의 관광 맥락, 관광자원과 출처를 기획 입력/결과에서 참고.
- **동작 방식:** 지역현황 JSON, 전국 비교 DB, TourAPI, 공식 문서 청크·사례를 결합.
- **Frontend:** 대시보드·기획·전략 화면의 지역 설명/출처.
- **Backend:** AI Server의 지역정보·tourism-status·Evidence 처리.
- **AI / Data:** 통계와 관광자원은 별도 자료. 관광자원 목록으로 매출/정책 효과를 증명하지 않음.
- **사용하는 API:** `/ai/v1/demo/{code}/region-info`, `/tourism-status`.
- **관련 파일:** `tourism_open_api.py`, `regional_tourism_status_store.py`, `agents/evidence_agent.py`, `rag_store.py`.
- **현재 구현 상태:** 🟡 코드·이전 보고서 trace에 수집 기록 있음. 이번 외부 API 전체 재검증 미실시.
- **발표 가치:** 지역 통계에 장소·정책 근거를 보완하는 방식.

### 4.5 사업 여건 입력과 참고자료 첨부

- **사용자에게 보이는 기능:** 예산 상태/범위/상한, 목표율, 일정, 자원, 제약, 선호, 현장 정보, 참고자료.
- **동작 방식:** Pydantic 계약 검증. 미정 값은 null/unknown으로 유지. 문서 텍스트를 요청 문맥으로 사용.
- **Frontend:** `TourismPlanningPage.jsx`, `features/planning/*`.
- **Backend:** `PlanningBrief`, 참고파일 텍스트 추출 endpoint.
- **AI / Data:** 사용자 진술과 공식 관측 사실을 분리. 첨부가 공용 RAG에 자동 학습되는 구조 아님.
- **사용하는 API:** POST `/ai/v1/planning/reference?filename=...`, 생성 job 요청.
- **관련 파일:** `ai_server/app/planning_brief.py`, `frontend/src/features/planning/planningBrief.js`.
- **현재 구현 상태:** ⚪ 폼·검증·추출 코드 확인, 이번 업로드/POST 미실행.
- **발표 가치:** 막연한 질문 대신 행정·사업 조건을 구조화한다. 화면 입력 시연은 제출 전까지만 권장.

### 4.6 지역 관광발전 기획 초안 생성

- **사용자에게 보이는 기능:** 생성 진행 단계, 후보/기획 내용, 실행 단계, 출처, 검토 결과.
- **동작 방식:** job 생성→근거/사례 수집→적용성 비교→후보 검사→본문 작성→검토/제한된 수정.
- **Frontend:** `TourismStrategyPage.jsx`, API polling.
- **Backend:** AI Server의 job·orchestrator·store.
- **AI / Data:** Qwen/Gemma/OpenAI, 지역 snapshot, ML planning evidence, 공식 근거, 사업 조건.
- **사용하는 API:** POST `/strategy-report/jobs`, GET `/strategy-report/jobs/{job_id}`; 동기 생성도 존재.
- **관련 파일:** `ai_server/app/agents/report_orchestrator.py`, `transferability_agent.py`, `planner_agent.py`, `reviewer_agent.py`.
- **현재 구현 상태:** 🟡 과거 실제 실행/저장 확인. 최신 검사 변경 이후 승인 가능한 기획 생성은 미확인.
- **발표 가치:** 역할 분담과 추적 가능한 생성 절차. “자동으로 타당한 사업 확정” 표현 금지.

### 4.7 기획 결과 검토·차트·목표 시나리오

- **사용자에게 보이는 기능:** 기획 본문, 검토 상태·지적사항, 월별 추이, 실행 목표/기준 추이 비교.
- **동작 방식:** 구조화된 report를 화면에 투영. 목표 시나리오는 입력/가정이며 관측 성과 아님.
- **Frontend:** `TourismStrategyPage.jsx`, `TourismDashboardPage.jsx`의 공용 보고서/차트 코드.
- **Backend:** `report_projection.py`, `report_review_status.py`, `report_projection` 관련 생성 결과 처리.
- **AI / Data:** 실제 수치/ML 자연 추이와 사업 목표 구분.
- **사용하는 API:** 보고서 상세 GET, job 결과 GET.
- **관련 파일:** 위 파일, `ai_server/app/report_projection.py`.
- **현재 구현 상태:** 🟡 원주 상세 조회 확인; 미승인 보고서이며 개선 효과 실증 없음.
- **발표 가치:** 결과를 예쁘게 표시하는 것과 검증 상태를 구분하는 설계.

### 4.8 AI 챗봇: 설명·조사·본문 보완

- **사용자에게 보이는 기능:** 지역 지표/현재 기획안 질문, 공식 추가 조사, 문장·실행 단계 수정안.
- **동작 방식:** 질문과 검색 허용 여부에 따라 explain/research/revise 작업 선택. revise는 제한된 `report_patch` 반환.
- **Frontend:** `TourismAssistant.jsx`, `WorkspaceAssistantPanel.jsx`, `applyReportPatch.js`, `chatHistory.js`.
- **Backend:** `TourismChatAssistantAgent`.
- **AI / Data:** 설명 Qwen, 수정 Gemma, 공식 웹 조사 OpenAI. 기존 보고서·snapshot·대화 문맥 전달.
- **사용하는 API:** POST `/ai/v1/demo/{code}/assistant-chat`.
- **관련 파일:** `agents/chat_assistant_agent.py`, `llm/chat_context.py`.
- **현재 구현 상태:** ⚪ 호출·patch 경로 확인, 이번 신규 대화 미실행.
- **발표 가치:** 결과 확인 후 보완하는 업무 연결. 챗봇이 ML/KPI/예산을 임의 확정·저장한다고 설명하지 않는다.

### 4.9 저장 기획안 게시판·수정 저장

- **사용자에게 보이는 기능:** 보고서 목록, 검색/연도 필터/페이지 이동, 상세 보기, 수정 내용 저장.
- **동작 방식:** 완료된 생성 결과를 MySQL에 자동 저장. 이후 본문 수정 저장은 PUT. 브라우저 메모리와 공용 저장을 구분.
- **Frontend:** `SavedStrategyPlansBoardPage.jsx`, `TourismStrategyPage.jsx`.
- **Backend:** `strategy_store.py`; JSON 및 문서 경로 관리.
- **AI / Data:** 저장된 결과 재조회에는 신규 LLM 불필요.
- **사용하는 API:** GET `/ai/v1/strategy-reports`, GET/PUT `/{report_id}`.
- **관련 파일:** 위 파일, `frontend/src/api/dashboardApi.js`.
- **현재 구현 상태:** ✅ 목록 5개/원주 상세 읽기 확인. PUT은 이번에 미실행.
- **발표 가치:** 일회성 채팅을 재사용 가능한 검토 기록으로 보관.

### 4.10 Word·PowerPoint 문서 출력

- **사용자에게 보이는 기능:** DOCX/PPTX 다운로드.
- **동작 방식:** report JSON을 python-docx/python-pptx/차트 처리 코드로 문서화하고 서버 파일 경로 저장. 캐시 버전이 다르면 재생성 가능.
- **Frontend:** 기획 결과·저장 목록의 출력 버튼.
- **Backend:** `proposal_document.py`, 현재 export가 가리키는 `proposal_presentation_v4.py` 및 레이아웃/내용 모듈.
- **AI / Data:** LLM 본문을 문서로 배치하는 Python 렌더링. 문서 파일을 생성했다는 이유로 내용이 승인되는 것은 아님.
- **사용하는 API:** POST `/strategy-proposal.docx`, `/strategy-proposal.pptx`; GET `/strategy-reports/{id}/documents/{file_format}`.
- **관련 파일:** `proposal_presentation.py` 마지막 재export, `proposal_slide_content.py`, `storage/strategy_documents/`.
- **현재 구현 상태:** 🟡 코드·기존 출력/검수 산출물 존재. 현재 목록의 Word/PPT ready=false 항목이 있어 재생성 필요 여부 확인해야 함. 이번 출력 미실행.
- **발표 가치:** 분석→기획→편집 가능한 업무 문서 연결. 미승인 초안도 출력 가능하므로 승인 필터가 출력을 모두 차단한다고 발표하지 않음.
- **없는 기능:** 🔴 사용자용 PDF 출력 endpoint는 확인되지 않음. PDF 입력/검수 파일과 구분.

### 4.11 LLM 관리자·모델 역할 설정·실행 추적

- **사용자에게 보이는 기능:** Provider 상태, 모드/작업별 모델, 설정 변경·초기화, 최근 trace·토큰.
- **동작 방식:** Router 정책이 저장 설정과 실제 적용 경로를 구분. 변경은 별도 관리자 토큰 필요.
- **Frontend:** `/llm-control`, `LlmControlPage.jsx`.
- **Backend:** `/llm/status`, `/config`, `/trace`; `storage/llm_runtime_config.json`.
- **AI / Data:** 모델 학습/다운로드 관리가 아니라 호출 설정 관리.
- **사용하는 API:** GET/PUT config, POST reset, GET status/trace.
- **관련 파일:** `llm/router.py`, `llm/trace_store.py`, `main.py`의 `_require_llm_admin_token`.
- **현재 구현 상태:** 🟡 상태 조회 확인; 이번 설정 변경 미실행. 일반 회원/권한 관리 시스템으로 소개 불가.
- **발표 가치:** 실제 모델 역할과 호출 비용 정책을 관찰 가능하게 함.

### 4.12 ML·OpenAI·React 학습 설명 화면

- **사용자에게 보이는 기능:** 등록 모델/평가와 프로젝트 구조 설명, 질문 기능.
- **동작 방식:** 실제 코드·모델 카탈로그를 구성하고 별도 학습 Assistant가 답변.
- **Frontend:** `/ml-test`, `/openai-test`, `/react-test`, `pages/MlTest/*`.
- **Backend:** ML learning catalog와 project learning catalog, 두 학습 Agent.
- **AI / Data:** 학습/발표 보조 설명이며 관광 기획 Agent 체인과 별개. 직접 OpenAI Responses 호출 경로.
- **사용하는 API:** `/ai/v1/ml/learning/catalog`, `/learning/{topic}`, 각 assistant POST.
- **관련 파일:** `ai_server/ml/learning_catalog.py`, `project_learning_catalog.py`, `agents/*learning_assistant_agent.py`.
- **현재 구현 상태:** ⚪ 코드/카탈로그 경로 확인, 이번 학습 채팅 미실행.
- **발표 가치:** 학습한 기술과 평가 과정을 설명하는 보조 화면.

### 4.13 데이터 정제·등록·학습 운영 도구

- **사용자에게 보이는 기능:** 일반 이용자 버튼이 아니라 개발자의 CLI 작업.
- **동작 방식:** 원자료 인벤토리→스냅샷/압축 해제→월별 정제→지역 코드 결합→SQL bundle→MySQL 적재; 별도 학습 CLI로 Joblib 생성.
- **Frontend:** 등록 결과를 카탈로그·대시보드·ML 설명 화면에서 사용.
- **Backend:** batch 도구와 AI 조회 경로 연결; 요청마다 재학습하지 않음.
- **AI / Data:** Pandas/NumPy/scikit-learn/Joblib, 출처 계보·모델 fingerprint.
- **사용하는 API:** 원자료 수집 자동 API가 아닌 명시적 파일 처리 중심.
- **관련 파일:** `data_pipeline/tools/`, `ai_server/ml/`, `data/catalog/region_data_registry.csv`.
- **현재 구현 상태:** ✅ 변환 산출물·SQL 적재 데이터·89지역 모델 등록 확인. 이번 재적재/학습 미실행.
- **발표 가치:** 모델만 만든 것이 아니라 데이터에서 서비스까지 연결한 과정.

### 4.14 기준·후속 측정 저장

- **사용자에게 보이는 기능:** 보고서 기준과 후속 관측을 관리할 API. 완성된 별도 성과관리 화면은 확인되지 않음.
- **동작 방식:** 기준 관측과 후속 관측을 별도 테이블에 저장하고 출처를 보관.
- **Frontend:** 전용 입력/분석 흐름은 미완성으로 취급.
- **Backend:** `strategy_store.py`, measurements GET/POST.
- **AI / Data:** 목표를 실제 성과로 저장하지 않도록 분리. 인과효과 추정 모델 아님.
- **사용하는 API:** `/ai/v1/strategy-reports/{id}/measurements`.
- **관련 파일:** `tests/nationwide_pipeline/test_strategy_measurements.py`, SQL/strategy_store.
- **현재 구현 상태:** 🟡 기준 20행, 후속 0행. 실제 성과 검증 미완료.
- **발표 가치:** 향후 사업 평가를 위한 데이터 계약. 성과 수치 발표에는 사용 금지.

### 4.15 프로젝트 구조 탐색기

- **사용자에게 보이는 기능:** `/project-tree`에서 저장소 구조 탐색 보조 화면.
- **동작 방식:** React iframe이 별도 Streamlit 서비스에 연결. CLI 도구도 존재.
- **Frontend:** `ProjectTreePage.jsx`.
- **Backend:** 관광 FastAPI가 아닌 Streamlit 별도 프로세스.
- **AI / Data:** 파일 구조 탐색; 관광 의사결정 AI 아님.
- **사용하는 API:** Streamlit URL, 기본 localhost:8501.
- **관련 파일:** `project_tree_explorer/app.py`, `tree_core.py`, `tree_cli.py`.
- **현재 구현 상태:** 🟡 health 200. iframe/다른 PC 접근은 별도 확인 필요.
- **발표 가치:** 구조 설명 보조. 사용자 관광 서비스의 핵심 기능과 분리.

## 5. 실제 서비스 이용 흐름

### 사용자 관점 Flow

```text
메인 → 지원 지역 선택 → 대시보드에서 관측/예측 확인
 → 기획 여건 입력(예산·일정·목표·제약·참고자료)
 → 생성 요청 → 진행/오류 확인
 → 기획 초안 + 출처 + 검토 상태 확인
 → 필요 시 AI 설명/본문 수정 → 수정 저장
 → 저장 목록에서 다시 열기 → DOCX/PPTX 출력
```

생성 실패 시 보고서가 반드시 만들어지는 것은 아니다. 완료 결과는 자동 저장을 시도하며, 저장 실패가 생성 결과와 별도로 표시될 수 있다. 저장됐어도 승인된 기획안이라는 뜻은 아니다.

### 시스템 관점 Flow

```text
React → 카탈로그/지역 코드 확인 → AI Server snapshot
 → 원자료 + MySQL 문맥 + 저장 모델 예측
 → PlanningBrief 검증 + 데이터 최신성 + 로컬 모델 연결 확인
 → Evidence/CaseStudy 수집 → Qwen 후보 비교/보완
 → Python 후보 검사 [실패: 422, 본문 생성 이전 중단]
 → Gemma 초안 → Python 검사 + Qwen 검토
 → 필요 시 1회 수정·재검토 → 조건 충족 시 OpenAI 최종 감사
 → 결과 JSON / 검토상태 / 출처 / trace
 → MySQL 저장 + 출력 파일 생성 시도 → job 결과 → React
```

## 6. 데이터 분석

### 6.1 Local Dataset

| 데이터명·출처 | 형태·변수 | 사용 위치 / 화면 / AI | 실시간·현재 상태 |
|---|---|---|---|
| 한국관광 데이터랩 지역 월별 다운로드 | CSV/ZIP/스냅샷; 지역코드·월·방문자·소비액·숙박일·숙박률·체류시간·내비 검색·숙박 검색 | 지역 pipeline→대시보드·ML·snapshot·LLM 근거 | 실시간 아님. 지역별 관측 종료월 다름. 원주 조회 확인 |
| 지역 데이터 등록부 | `data/catalog/region_data_registry.csv`; 코드·경로·활성·출처 정보 | 지원 지역 선택/모델 연결 | 90행 중 활성 89개. exact download URL 보완 상태 |
| 전국 월별 정제 자료 | processed/nationwide + MySQL; 월별 지표·지역 간 비교·출처 ID | nationwide context→기획 근거/비교 | 다운로드 자료의 배치 적재. DB 행 확인 |
| 전국 빅데이터 문맥 | processed/nationwide_bigdata + MySQL; 기간형 시군구 지표/월별 문맥 | 지역 비교 보강·Evidence | 기간 집계와 월별 자료 구분. DB 행 확인 |
| 지역 관광현황 자료 | processed/regional_tourism_status JSON, 대응 SQL; 흐름·분류·장소·집중도 | tourism-status/지역 맥락/기획 | 런타임 store는 JSON 읽기. SQL도 적재돼 있으나 동일 경로로 쓰인다고 가정 금지 |
| 공식 문서 청크 | data/rag JSONL; 제목·URL·페이지·chunk ID·본문·지역 | 근거 검색/출처 표시/LLM 문맥 | 24청크(정책22·정의2), 고정 추출 자료 |
| 공식 참고 요약 | data/rag; 정책/정의 요약·URL | 로컬 검색/설명 | 3개(정책2·정의1), 전문 전체를 읽은 것으로 표현 금지 |
| 검토된 사례 카드 | data/rag; 적용 구조·비용/성과 구분·공식 URL | CaseStudy→Transferability | 6개(사례5·예산사례1). 성공 사업을 6건 실증했다는 뜻 아님 |
| 학습 모델/평가 | artifacts/ml의 Joblib·metadata JSON; 기간·선택 모델·MAE/MAPE·fingerprint | 예측 API/ML 화면/기획 evidence | 사전 학습. 새 데이터 자동 재학습 아님 |
| 생성 보고서 | MySQL JSON + storage 문서 | 결과/게시판/다운로드/챗봇 문맥 | 5개. 생성 당시 근거·검토 상태 보존 |
| 사용자 조건/첨부 | 요청 JSON·브라우저 초안·일시적 추출 텍스트 | 기획 입력/Agent | 공식 사실 아님. 첨부 원문을 공용 RAG로 자동 누적하지 않음 |
| 측정 기준/후속값 | MySQL baseline/followup | measurements API | 기준20행, 후속0행. 사업 효과 자료 없음 |
| 학습/구조 참고 자료 | references·project catalog·트리 정보 | 개발 설명 화면 | 관광 실측 데이터가 아닌 보조 자료 |

### 6.2 Open API

| API 데이터 | 저장/변수 | 화면·AI 사용 | 현재 상태 |
|---|---|---|---|
| VWorld 행정 경계 | GeoJSON, region_code/name, Polygon/MultiPolygon; 메모리/디스크 캐시 | 지도 표시. ML 학습 변수 아님 | 코드 경로·캐시 구현 확인, 이번 외부 요청 미실행 |
| 한국관광공사 TourAPI | areaCode2, areaBasedList2; 지역코드·관광정보 ID·제목·주소·대표 이미지 등 | 지역 관광자원·Evidence | 이전 trace에 open_api 완료. 이번 최신 응답 미확인 |
| OpenAI 공식 웹 검색 결과 | 응답의 공식 URL/제목/인용 | Evidence/CaseStudy/추가조사 | 유료 생성 경로. 원주 이전 official_web 실패 기록도 있음 |
| Tavily/Brave 검색 | 검색 결과 제목/URL/짧은 snippet | 로컬 웹 질의 계획과 검색 보완 | 코드 존재, 현재 configured provider 없음/available=false |

### 6.3 Hybrid Data

지역코드로 월별 통계를 조회하고, ML로 자연 추이를 예측한 다음, MySQL 비교 문맥과 공식 문서·관광자원을 함께 전달한다. LLM은 이를 설명·기획하는 역할이다. 월별 숫자를 벡터 DB에 넣어 LLM이 합계를 계산하는 설계가 아니다.

원주 예시의 마지막 관측은 **2026-06**이다. 2026-09 기준 마지막 완료월 2026-08보다 2개월 늦지만 허용 기준 3개월 안이라 생성 준비도는 통과했다. dashboard 응답의 `latest_month=2026-10`은 표시 중인 **예측월**이므로 최신 원자료 시점으로 인용하면 안 된다.

카탈로그 89개는 경기43·서울25·강원17·경남3·인천1개다. 전국 MySQL에 지역267행이 있다고 267개 예측 지원으로 바꾸어 말하지 않는다. 비활성 지역이나 원자료 부족 지역은 지원 준비와 구분한다.

## 7. 외부 API 조사

| API / 제공자 | 목적·요청 위치·사용 데이터 | 실제 사용 근거 / 실패 처리 | 발표 이유 |
|---|---|---|---|
| VWorld WFS / 공간정보 오픈플랫폼 | `backend/app/services/vworld.py`; 시도·시군구 경계 | HTTP 처리·범위 분할·병합·24시간 캐시. 실패는 API 오류/화면 오류 경로. 캐시로 매 클릭 외부 요청 방지 | 지도와 지역코드 연결 |
| TourAPI / 한국관광공사 | `tourism_open_api.py`; 지역코드 조회 후 관광자원 목록 | 키 미설정 시 빈 자료, HTTP 오류는 상위 수집 gaps 처리. 과거 수집 trace 존재 | 통계에 실제 지역 관광자원 보완 |
| OpenAI Responses / OpenAI | `openai_responses.py`, `llm/openai_provider.py`; 구조화 JSON·공식 웹 검색 | 실제 보고서 trace에 호출/실패 존재. Provider 오류·제한된 retry·비용 정책. 유료 부족 시 일반 무제한 대체 아님 | 조사/검토와 로컬 작성 역할 분담 |
| OpenAI Embeddings / OpenAI | `rag_store.py`; 공식 문서 embedding/query | Chroma 검색 코드 존재하나 현재 embeddings 0. 로컬 검색 경로 사용 가능 | 계획된 의미 검색과 실제 가동 범위 구분 |
| Ollama HTTP / 운영 중인 로컬 모델 서버 | `llm/ollama_provider.py`; `/api/tags`, 생성 요청 | Qwen/Gemma 연결 확인. local_first에서 장애를 유료 모델로 자동 전환하지 않음 | GPU 모델을 서비스 Provider로 연결 |
| Tavily / Brave Search | `local_web_search.py`; 검색 query/snippet/URL | 설정된 provider 없음. 현재 검색이 정상 동작한다고 소개 불가 | 추가 검색 보완 코드의 제한 |

데이터랩 월별 자료는 이 코드에서 허용된 파일 다운로드·로컬 처리 대상으로 사용한다. 데이터랩 웹 크롤링/실시간 수집이 구현됐다고 설명하지 않는다. 키·비밀번호·개인 LAN 주소는 발표자료에 넣지 않는다.

## 8. AI가 실제로 담당하는 일

```text
지역 + 사업 조건
 → Python: 데이터 검증, snapshot, 숫자·예측·사업조건 분리
 → sklearn: 저장 모델로 방문·소비 등 자연 추이 예측
 → 근거 수집: SQL/파일/TourAPI/공식문서/조건부 공식 웹
 → Qwen: 후보 설계·사례 적용성 비교·본문 검토
 → Gemma: 선택 후보를 사업 기획 본문으로 작성·수정
 → Python: JSON/출처/조건/후보 검사
 → 조건부 OpenAI: 최종 검토
 → 기획 초안 + 출처 + 검토 결과 + trace
```

**숫자 사실:** 데이터 저장소와 Python. **미래 자연 추이:** 직접 학습한 ML 또는 선택된 기준모델. **문서 근거:** 공식 자료 검색. **설명·전략 문장:** LLM. **DOCX/PPTX 배치:** Python 문서 라이브러리.

현재 `/llm/status`의 실제 적용 경로는 Evidence=`gpt-5.6-terra`, CaseStudy/최종 검토/조사 채팅=`gpt-5.6-sol`, 후보/검토/설명=`qwen3:14b`, 작성/수정=`gemma4:26b`다. 이는 프로젝트가 반환한 설정/trace이며 모델의 일반적인 성능이나 모든 경로의 현재 호출 성공을 보증하지 않는다. OpenAI health가 기본 모델 `gpt-5-mini`를 확인한 것을 다른 모델 전부의 성공으로 해석하지 않는다.

모든 Agent가 매번 LLM을 호출하는 것은 아니다. Evidence/CaseStudy는 로컬 자료·캐시만으로 처리하거나 조건에 따라 웹 조사를 생략한다. 공식 도메인 제한과 출처 ID 검사는 오류를 줄이기 위한 장치이며, 사례의 이용 절차/효과 해석까지 자동으로 정확해졌다는 증거는 아니다.

## 9. Agent 구조

### 9.1 EvidenceAgent

- **역할:** 선택 지역의 관측/예측·전국 비교·지역현황·관광자원·공식 문서 근거 묶음 구성.
- **입력:** snapshot, 환경/Router, 지역/사업 여건.
- **처리:** 데이터 출처 정리, SQL/로컬 문서/TourAPI/허용 도메인 조사, 부족 근거 gaps 표시.
- **출력:** evidence pack, source 목록, gaps, 단계 trace.
- **모델:** 자료 조회는 Python; 필요 시 evidence route의 OpenAI.
- **관계:** CaseStudy와 함께 수집된 뒤 Transferability/Planner에 전달.
- **실제 호출:** 원주 저장 trace의 dataset 등 완료, official_web 실패가 함께 존재.
- **코드:** `ai_server/app/agents/evidence_agent.py`.

### 9.2 CaseStudyAgent

- **역할:** 공식 관광사업 사례를 고르고 적용 구조를 정리.
- **입력:** 지역 조건, 사례 카드·RAG·조사 설정.
- **처리:** 지역/유사 조건을 고려한 카드 선택, 부족 시 조건부 공식 웹 조사.
- **출력:** 사례 및 출처/해석·부족사항.
- **모델:** 로컬 선택은 Python, 조사 시 case_study route OpenAI.
- **관계:** Evidence와 병렬 수집 후 Transferability 입력.
- **실제 호출:** 원주 저장 trace에서 사례 선택/수집 완료 기록.
- **코드:** `agents/case_study_agent.py`, `case_registry.py`, `case_scope.py`, `case_mechanism.py`.

### 9.3 TransferabilityAgent

- **역할:** 다른 지역 사례를 그대로 복사하지 않고 현재 지역 사업 후보를 비교.
- **입력:** 지역 evidence, 사례, 사업 조건, ML 판단 근거.
- **처리:** 후보 유형·지역 적합성·비용/측정/출처 연결 생성. 필요 시 제한된 로컬 보완.
- **출력:** 후보 비교·선택/유보 사유 및 후보 구조.
- **모델:** 현재 Qwen3:14b. 허용된 읽기 도구 문맥 사용.
- **관계:** Planner 이전 품질 관문. 검사를 통과하지 못하면 본문 단계 차단.
- **실제 호출:** 저장 trace와 별도 candidate replay 실측 존재, 품질 미달 지속.
- **코드:** `agents/transferability_agent.py`, `llm/local_agent.py`, `llm/evidence_tools.py`.

### 9.4 PlannerAgent

- **역할:** 선택 후보를 지역 관광사업 기획 본문으로 구성.
- **입력:** snapshot, evidence/cases, 후보 비교, 사업 조건, ML evidence; 수정 시 검토 지적.
- **처리:** 구조화 JSON 초안 작성, 필요 시 1회 수정.
- **출력:** 제목·문제·비교·해결방안·효과 가정·실행 단계 등.
- **모델:** 현재 Gemma4:26b, planner/planner_revision.
- **관계:** Transferability 다음, Reviewer 이전/피드백 이후.
- **실제 호출:** 원주 저장 trace에 초안/수정 완료 기록.
- **코드:** `agents/planner_agent.py`, `agents/prompts.py`.

### 9.5 ReviewerAgent

- **역할:** 보고서의 사실/출처/조건/기획 논리를 검토.
- **입력:** 보고서 및 동일 근거·사업 조건·검사 결과.
- **처리:** 코드 기반 precheck와 LLM 검토를 통합, 승인/미승인 및 지적 생성.
- **출력:** quality_review, validation findings, 개선 지시.
- **모델:** 현재 로컬 검토 Qwen3:14b. 조건부 final_reviewer는 OpenAI.
- **관계:** Planner 수정 여부 결정. 최종 검토는 별도 task이며 항상 실행되지 않음.
- **실제 호출:** 원주 첫 검토/재검토 완료, 최종 cloud 감사 skipped.
- **코드:** `agents/reviewer_agent.py`, `plan_quality_gate.py`, `planning_requirements.py`.

### 9.6 TourismChatAssistantAgent

- **역할:** 현재 지역/보고서 설명, 추가 조사, 제한된 본문 보완.
- **입력:** 질문·대화 이력·snapshot·current_report·검색 허용·사업조건.
- **처리:** explain/research/revise 분기, 허용 출처만 응답, 수정은 report_patch.
- **출력:** answer, mode, key_points, sources, report_patch.
- **모델:** Qwen 설명/Gemma 수정/OpenAI 조사.
- **관계:** 생성 체인 밖의 사용자 후속 상호작용.
- **실제 호출:** API/Frontend 연결 확인, 이번 신규 호출 미실행.
- **코드:** `agents/chat_assistant_agent.py`, `llm/chat_context.py`.

### 9.7 MlLearningAssistantAgent

- **역할:** 등록 모델과 평가를 학습자가 이해하도록 설명.
- **입력:** learning_region 카탈로그·질문·이력.
- **처리/출력:** 카탈로그 근거로 구조화 설명 생성.
- **모델:** `OPENAI_ML_CHAT_MODEL → OPENAI_CHAT_MODEL → OPENAI_MODEL` 우선순위. 확인된 두 앞 설정은 없고 기본 `gpt-5-mini` 사용 경로.
- **관계:** 관광 기획 체인과 별도이며 공통 Router를 경유하지 않는 직접 Responses 경로.
- **실제 호출:** 코드 확인, 이번 호출 미실행.
- **코드:** `agents/ml_learning_assistant_agent.py`.

### 9.8 ProjectLearningAssistantAgent

- **역할:** 프로젝트의 OpenAI/React 구조 학습 설명.
- **입력:** topic, 프로젝트 카탈로그, 질문/이력.
- **처리/출력:** 주제별 실제 구조를 근거로 답변.
- **모델:** `OPENAI_LEARNING_CHAT_MODEL → OPENAI_ML_CHAT_MODEL → OPENAI_CHAT_MODEL → OPENAI_MODEL` 순서. 전용 설정/실행 응답 재확인 전 단일 모델로 단정하지 않음.
- **관계:** 관광 기획 체인과 별도 직접 Responses 호출.
- **실제 호출:** 코드 확인, 이번 호출 미실행.
- **코드:** `agents/project_learning_assistant_agent.py`, `project_learning_catalog.py`.

### 9.9 Report Orchestrator와 비LLM 검사

- **역할:** Agent 순서·동시 수집·캐시·진행·재시도·중단 조건 조정.
- **입력:** snapshot, PlanningBrief, Router, progress callback.
- **처리:** ML evidence/decision facts 준비→수집→후보→검사→작성→검토→조건부 감사.
- **출력:** 완성 또는 미승인 report/오류 및 trace.
- **모델:** 자체 모델 없음; 작업을 각 Agent/Router에 위임.
- **관계:** 전체 호출을 관리하되 저장/job API는 main/store와 협력.
- **실제 호출:** 저장 보고서 trace와 진단 기록 확인.
- **코드:** `agents/report_orchestrator.py`, `decision_facts.py`, `plan_quality_gate.py`.

```text
Report Orchestrator (Python)
 ├─ snapshot + ML evidence + decision facts
 ├─ [동시] EvidenceAgent ─┐
 └─ [동시] CaseStudyAgent ┴─ 근거 pack
             ↓
     TransferabilityAgent (Qwen)
             ↓ 후보 검사/제한된 보완
     실패 → 구조화 오류로 중단
     통과 ↓
     PlannerAgent (Gemma)
             ↓
     Python 검사 + ReviewerAgent (Qwen)
             ├─ 필요 시 Gemma 수정 → 재검토 (제한)
             └─ 조건 충족 시 final_reviewer (OpenAI)
             ↓
     보고서 + 출처 + 검토 상태 + trace

별도: TourismChatAssistant / ML Learning / Project Learning
```

여기서 Agent는 **정해진 역할의 코드 모듈과 호출 절차**다. 독립 에이전트가 무제한 도구 사용·자율 협상을 하거나 자체 학습하는 시스템으로 설명하지 않는다. AGENTS의 초기 MVP 제외 문구보다 이후 결정 로그와 현재 실제 구현을 함께 참고한다.

## 10. LLM Router·모델 관리

| 기능 | 실제 구현/현재 적용 | 상태 |
|---|---|---|
| Provider 추상화 | OpenAIProvider/OllamaProvider, LLMRequest/Result | ✅ 코드/trace 존재 |
| 모드 | openai_only, hybrid, local_only, local_first, student_budget | 🟡 모드 구현; 전 모드 통합 실행 검증 아님 |
| 현재 모드 | `/llm/status`: local_first | ✅ 조회 확인 |
| 역할 라우팅 | 아래 표; 관리자 저장 설정과 effective_routes 구분 | ✅ 조회 확인 |
| 설정 수정/초기화 | PUT config/POST reset, X-LLM-Admin-Token 검사 | ⚪ 이번 쓰기 미실행 |
| fallback | hybrid 등 코드 경로는 존재; 현재 effective fallback은 none | ✅ 현재 정책 확인 |
| 비용 제어 | 현재 automatic_paid_fallback=false, cloud call budget 3, 자동 웹 조사 true | 🟡 정책 구현, 비용 절감률 실측 아님 |
| 사용량 | 프로세스 최근 최대120 trace, 응답에 보고된 토큰 합산 | ✅ 코드. 계정 전체 청구/잔여 한도 아님 |
| 무료 검색 | enabled이나 configured provider 없음 | ⚪ 현재 이용 불가 |
| 모델 학습·다운로드 UI | 없음 | 🔴 |

| 작업 | 현재 effective Provider / 모델 |
|---|---|
| evidence | OpenAI / gpt-5.6-terra |
| case_study | OpenAI / gpt-5.6-sol |
| local_web_query_planner | Qwen / qwen3:14b |
| transferability | Qwen / qwen3:14b |
| planner, planner_revision | Gemma / gemma4:26b |
| reviewer | Qwen / qwen3:14b |
| final_reviewer | OpenAI / gpt-5.6-sol |
| chat_explain | Qwen / qwen3:14b |
| chat_revise | Gemma / gemma4:26b |
| chat_research | OpenAI / gpt-5.6-sol |

local_first 실패 시 OpenAI로 자동 전환되지 않는다. 로컬 우선 정책은 유료 조사를 없애는 것이 아니며 학습 Assistant의 직접 호출 경로까지 통합한 계정 단위 예산 제한도 아니다. trace의 duration/token은 응답이 보고한 범위이며 누락/실패/재시작에 따라 전체 청구와 다를 수 있다.

## 11. Frontend 구조와 캡처 추천

React 19, Vite 8, JavaScript/JSX, CSS, Recharts, Leaflet/react-leaflet, lucide-react를 실제 import/렌더링 코드에서 확인했다. React Router 패키지 대신 `window.location.pathname` 분기, React.lazy/Suspense를 사용한다. UI는 자체 CSS 중심이며 shadcn 같은 표현이 주석에 있다고 해당 UI 라이브러리를 사용 기술로 넣지 않는다. fetch 기반 API 모듈을 사용한다.

| 경로 | 페이지 | 역할 |
|---|---|---|
| `/` | TourismHomePage | 서비스 소개 |
| `/dashboard`, `/diagnosis` | TourismDashboardPage | 지도·지표·차트·예측 |
| `/planning` | TourismPlanningPage | 사업 여건 입력 |
| `/strategy`, `/proposal` | TourismStrategyPage | 생성·결과·수정·출력 |
| `/saved-plans` | SavedStrategyPlansBoardPage | 저장 목록·상세 |
| `/ml-test` | MlTestPage | ML 카탈로그·평가 설명 |
| `/openai-test`, `/react-test` | LearningArchitecturePage | 기술 학습 화면 |
| `/llm-control` | LlmControlPage | 모델 연결·설정·trace |
| `/project-tree` | ProjectTreePage | Streamlit iframe |

`WorkspaceShell`, `RegionWorkspacePicker`, `WorkspaceAssistantPanel`, `TourismAssistant`가 공통 흐름을 구성한다. CSS media query로 단일 열/메뉴/차트 너비 등을 조정한다. 모바일 전 기종 검증 완료라는 의미는 아니다. Vite proxy는 `/api→8100`, `/ai→8111`; 브라우저에 외부 API 키를 전달하는 구조가 아니다.

### 발표 스크린샷 추천

| 화면 | 왜 필요한가 | 강조/촬영 조건 |
|---|---|---|
| 1. 지원 지역 대시보드 | 서비스 핵심이 한 장에 보임 | 지역명·예측 표시·관측 종료월 함께 설명. 지도 오류 없는 사전 캡처 |
| 2. 기획 여건 입력 | 지역 맞춤의 입력 근거 | 예산 미정/확정, 일정·자원·제약 구분. 실제 제출 불필요 |
| 3. 저장 보고서 상세 | 데이터→문서 연결 | 출처와 **미승인 상태를 가리지 말 것**. 부적절한 제목은 우수사례로 홍보하지 않음 |
| 4. ML 평가 화면 | 직접 학습과 정직한 검증 | 강남 방문자 기준모델 비교와 한계, 원주 반례 준비 |
| 5. LLM 제어/trace | Qwen/Gemma/OpenAI 실제 역할 | effective route·연결 상태. 토큰/키·호스트 정보는 공개 범위 점검 |

문서 출력은 발표 전 별도 실행·레이아웃 검수를 마친 파일만 캡처한다. 이번 작업에서는 캡처 파일이나 새 출력 파일을 만들지 않았다.

## 12. Backend와 API

일반 Backend와 AI Server 모두 FastAPI/Uvicorn이다. 일반 Backend는 VWorld 호출·경계 정규화·캐시를 담당한다. AI Server가 관광 데이터를 처리하고 PyMySQL로 DB에 접근하며 ML/LLM·저장·문서화를 수행한다. 일반 Backend를 반드시 거쳐 AI Server에 전달되는 구조는 아니다.

아래 `{code}`는 지역 코드, `{id}`는 report ID다. ✅는 이번 해당 조회 또는 대표 상세 경로 확인, ⚪는 호출 경로만 확인, 🟡는 기존 실행 기록과 현재 제한이 공존함을 뜻한다.

| Endpoint | Method | 역할 | 호출 주체 | 상태 |
|---|---|---|---|---|
| `/health` | GET | 일반 서버 health | 운영 확인 | ✅ |
| `/api/v1/boundaries/sido` | GET | 시도 경계 | 지도 | ⚪ |
| `/api/v1/boundaries/sigungu?sido_code=...` | GET | 시군구 경계 | 지도 | ⚪ |
| `/ai/health` | GET | AI 서버 health | 운영 확인 | ✅ |
| `/ai/v1/regions/catalog` | GET | 지원 지역 | 지역 선택 | ✅ |
| `/ai/v1/regions/readiness-audit` | GET | 준비도 감사 캐시 | 운영/개발 확인 | ✅ |
| `/ai/v1/demo/{code}/dashboard?region_name=...` | GET | 관광 대시보드 | 대시보드 | ✅ 원주 |
| `/ai/v1/demo/sido-comparison` | GET | 시도 내부 지역 비교 | 대시보드 | ⚪ |
| `/ai/v1/demo/{code}/generation-readiness?region_name=...` | GET | 데이터 최신성/생성 준비 | 기획 화면 | ✅ 원주 |
| `/ai/v1/demo/{code}/tourism-status` | GET | 지역 관광현황 | 지역정보/기획 | ⚪ |
| `/ai/v1/demo/{code}/region-info?region_name=...` | GET | 지역정보·자원 | 기획 화면 | ⚪ |
| `/ai/v1/planning/reference?filename=...` | POST | 참고파일 텍스트 추출 | 기획 입력 | ⚪ |
| `/ai/v1/demo/{code}/strategy-report/jobs` | POST | 비동기 생성 시작 | 전략 화면 | 🟡 |
| `/ai/v1/demo/{code}/strategy-report/jobs/{job_id}` | GET | 생성 상태/결과 | polling | 🟡 |
| `/ai/v1/demo/{code}/strategy-report` | POST | 동기 생성 | API/호환 경로 | 🟡 |
| `/ai/v1/demo/{code}/strategy-report/sample` | POST | 개발용 예시 | 개발/제한된 fallback | 🟡 예시 명시 |
| `/ai/v1/demo/{code}/assistant-chat` | POST | 설명/조사/보완 | 챗봇 | ⚪ |
| `/ai/v1/strategy-reports` | GET | 저장 목록 | 게시판 | ✅ |
| `/ai/v1/strategy-reports/{id}` | GET / PUT | 조회 / 본문 저장 | 상세·전략 | ✅ GET / ⚪ PUT |
| `/ai/v1/strategy-reports/{id}/measurements` | GET / POST | 기준·후속 관측 | 개발/API | 🟡 |
| `/ai/v1/strategy-reports/{id}/documents/{file_format}` | GET | 저장 출력/필요 시 재렌더 | 다운로드 | 🟡 |
| `/ai/v1/demo/{code}/strategy-proposal.docx` | POST | Word 생성 | 다운로드 | 🟡 |
| `/ai/v1/demo/{code}/strategy-proposal.pptx` | POST | PPT 생성 | 다운로드 | 🟡 |
| `/ai/v1/ml/{code}/planning-evidence?region_name=...` | GET | ML 판단 근거 | 기획/개발 | ✅ 원주 |
| `/ai/v1/ml/learning/catalog` | GET | 학습 카탈로그 | ML 화면 | ⚪ |
| `/ai/v1/ml/learning/{code}/assistant` | POST | ML 질문 | ML 화면 | ⚪ |
| `/ai/v1/learning/assistant-status` | GET | 학습 Assistant 상태 | 학습 화면 | ⚪ |
| `/ai/v1/learning/{topic}` | GET | OpenAI/React 학습 자료 | 학습 화면 | ⚪ |
| `/ai/v1/learning/{topic}/assistant` | POST | 학습 질문 | 학습 화면 | ⚪ |
| `/ai/v1/llm/status` | GET | Provider·실제 정책 | 제어 화면 | ✅ |
| `/ai/v1/llm/config` | GET / PUT | 설정 조회/변경 | 관리자 화면 | ⚪ 변경 미실행 |
| `/ai/v1/llm/config/reset` | POST | 설정 초기화 | 관리자 화면 | ⚪ |
| `/ai/v1/llm/trace` | GET | 최근 호출/토큰 | 제어 화면 | ⚪ |

지역명 필수 요청에서 이를 생략하면 오류가 발생한다. 발표용 URL/스크립트는 정상 파라미터를 사전 점검한다. Pydantic 요청 검증·구조화 오류 응답은 있으나 모든 오류 흐름을 이번에 다시 실행한 것은 아니다.

## 13. 실제 DB 스키마와 데이터

앱 DB는 **MySQL**, 직접 연결은 **PyMySQL**이다. 2026-09-08 읽기 전용 `SHOW TABLES`/`COUNT(*)`로 다음 28개 테이블을 확인했다. 행 수는 확인 당시 값이며 지역 수/월 수/성과 수로 임의 변환하지 않는다.

| 테이블 | 행 수 | 저장 내용·사용 |
|---|---:|---|
| dim_region | 267 | 지역 차원; 전체 차원 수와 ML 지원 수 구분 |
| data_source | 2,806 | 원자료 출처 |
| data_load_run | 5 | 적재 실행 기록 |
| data_load_rejection | 0 | 적재 거부 기록; 전체 품질 무결점 의미 아님 |
| fact_tourism_monthly | 5,040 | 지역+월 관광지표 |
| fact_tourism_metric_source | 45,270 | 지표별 출처 연결 |
| regional_planning_context | 167 | 기획용 지역 문맥 |
| regional_peer_comparison | 835 | 비교 지역 문맥 |
| nationwide_municipal_period_metric | 4,332 | 시군구 기간형 지표 |
| nationwide_monthly_tourism_context | 2,511 | 전국 월별 보강 문맥 |
| regional_tourism_status_flow | 20,320 | 지역 관광 흐름 |
| regional_tourism_status_flow_category | 38,107 | 흐름 분류 |
| regional_tourism_status_place | 538,157 | 장소별 현황 |
| regional_tourism_status_concentration | 7,500 | 집중도 |
| strategy_reports | 5 | report JSON·지역·제목·출력 경로 |
| strategy_report_jobs | 15 | job 상태/요청 조건/오류 |
| strategy_measurement_baseline | 20 | 생성 당시 기준 관측·출처 |
| strategy_measurement_followup | 0 | 후속 관측; 실제 성과 아직 없음 |
| data_source_lineage | 1,266 | 원자료 계보 |
| data_source_alias | 0 | 출처 별칭 |
| ml_model_registry | 0 | DB 모델 등록 스키마; 현재 모델은 파일 카탈로그/Joblib 사용 |
| ml_prediction | 0 | 예측 저장 스키마; 현재 예측 조회와 구분 |
| dim_attraction | 0 | 관광지 차원 확장 스키마 |
| fact_attraction_monthly_visitors | 0 | 관광지 월별 방문 확장 |
| attraction_edge | 0 | 관광지 연결 확장 |
| fact_attraction_popularity | 0 | 관광지 인기 확장 |
| fact_foreign_tourism_metric | 0 | 외국인 지표 확장 |
| fact_tourism_benchmark_metric | 0 | 벤치마크 지표 확장 |

핵심 결합은 `region_code + year_month`, 보고서는 `report_id`, 측정 기준은 `report_id + metric_name`으로 관리한다. 실제 Frontend 관계는 React→AI Server→store→MySQL이다. React에서 DB에 직접 접속하지 않는다. Word/PPT 바이너리는 MySQL에 모두 넣는 것이 아니라 로컬 서버 파일과 DB 경로로 연결한다.

`data/chroma/chroma.sqlite3`는 Chroma 내부 저장 구현이다. 앱 DB를 SQLite로 대체한 것이 아니다. 이번 조회에서 collection 1개/embedding 0개를 확인했으므로 “영속 벡터 검색 운영 완료”라고 쓰면 안 된다.

근거: `database/mysql/001_nationwide_tourism_data.sql`, `002_regional_tourism_status.sql`, `003_nationwide_bigdata_context.sql`, `ai_server/app/strategy_store.py`, `nationwide_context_store.py`, `nationwide_bigdata_store.py`.

## 14. 실제 기술 Stack

| 영역 | 발표에 넣을 기술 | 사용 근거 / 제외할 과장 |
|---|---|---|
| Frontend | React, Vite, JSX, CSS, Recharts, Leaflet/react-leaflet, lucide-react | 실제 페이지/import. React Router·별도 UI 프레임워크 사용 주장 금지 |
| Backend | Python, FastAPI, Uvicorn, Pydantic, httpx, asyncio | 경계/AI API·검증·외부 요청·job/수집 |
| AI / LLM | OpenAI Responses, Ollama, Qwen3:14b, Gemma4:26b, 자체 Router/Agent 모듈 | 학습 모델을 직접 개발한 것이 아닌 사전학습 LLM 활용 |
| Data / ML | Pandas, NumPy, scikit-learn, Joblib, CSV/JSON/ZIP 처리 | 정제·학습·시계열 평가·저장 추론 |
| Database | MySQL, PyMySQL | 실데이터/보고서 조회. SQLAlchemy를 핵심 사용으로 넣지 않음 |
| 근거 검색 | 로컬 공식 JSONL/사례 카드, ChromaDB 연동 코드 | 현재 embedding 비어 있음, 대규모 의미검색 성능 주장은 제외 |
| 문서 처리 | python-docx, python-pptx, Matplotlib, pypdf, openpyxl | 기획서/차트 출력 및 입력자료 추출 |
| External API | VWorld, TourAPI, OpenAI | Tavily/Brave는 현재 미설정으로 별도 표기 |
| Infrastructure | Windows PowerShell 개발 실행, LAN Ollama, Vite proxy, 별도 Streamlit | Nginx/AWS EC2는 목표; 운영 배포 설정/URL 확인되지 않음 |
| Collaboration | Git 저장소, Markdown 결정/검증 로그 | 실제 PR/CI·협업 플랫폼 성과는 별도 근거 필요 |

## 15. 기술적 핵심 8개

| 기술 | 왜 사용했는가 / 역할 | 발표 가치 |
|---|---|---|
| 지역 등록·출처 계보 | 이름 혼동을 줄이고 파일/지표/모델을 코드로 연결 | 높음: 데이터 신뢰성의 구체적 구현 |
| 시간순 ML 평가 | 미래 자료 누출을 피하고 기준모델과 비교 | 높음: 좋은 수치만 제시하지 않는 평가 |
| 저장 모델 추론 | 화면 요청과 학습을 분리 | 높음: ML의 서비스 연결 |
| 사실·예측·목표 계약 | 목표율과 예측/성과 혼동 방지 | 높음: 기획 결과 해석의 핵심 |
| 공식 근거 pack | DB·관광자원·문서·사례를 출처와 함께 전달 | 높음: 일반 자유질문과 다른 입력 구성 |
| Qwen/Gemma 역할 분리 | 후보 검토와 본문 작성을 분리 | 높음: 현재 실험 중인 구조, 품질 향상 확정 주장은 제외 |
| Router/검사/trace | 모드별 비용 정책·오류·수정 한도·실행 기록 | 높음: 관찰 가능한 AI 호출 절차 |
| JSON→저장/업무문서 | 동일 결과를 화면·게시판·DOCX/PPTX로 연결 | 높음: 업무 산출물로 이어지는 구현 |

## 16. 구현으로 설명할 수 있는 차별점

1. **관광 담당자의 사업 조건을 입력받는다.** 예산·일정·자원·제약을 별도 계약으로 전달한다.
2. **지역 지표·ML·공식 사례를 하나의 검토 흐름에 연결한다.** LLM에게 숫자 예측을 맡기지 않는다.
3. **후보 비교를 본문 작성 전에 수행한다.** 유형·지역 근거·비용·측정을 검사하고 실패를 드러낸다.
4. **모델별 역할과 실제 경로를 확인할 수 있다.** 저장 설정과 effective route를 구분한다.
5. **기획 결과를 저장하고 문서화한다.** 수정·조회·출력으로 이어진다.
6. **한계를 표시할 구조가 있다.** gaps·검토 상태·기준모델·출처를 결과와 함께 남긴다.

이는 구현 특징이지 경쟁서비스 대비 성능 우위 실험 결과가 아니다. “국내 최초”, “환각 제거”, “정책 성공률 향상”, “비용 몇 % 절감”은 근거가 없어 제외한다.

## 17. 머신러닝 사용 여부와 발표 판단

**직접 ML을 학습했고, 서비스에서는 그 저장 모델을 사용하며, 별도로 사전학습 LLM을 호출한다.** 따라서 사용자 요청의 분류 1·2·4가 함께 해당한다. LLM만 사용하는 프로젝트가 아니다. Qwen/Gemma 파인튜닝을 수행한 근거는 없다.

### 실제 학습 구조

- 대상: visitors, spending_krw, lodging_nights, lodging_rate_pct, stay_minutes, navigation_searches, lodging_searches의 7지표.
- 후보: RandomForestRegressor, LinearRegression, 전년 동월 계절 기준모델.
- 방문/소비 일부는 다변량 lag, 다른 지표는 lag1/3/12와 월 계절성 sin/cos 등 사용.
- RandomForest 설정은 300 trees, max_depth=3, min_samples_leaf=2, random_state=42 경로 확인.
- 시간순 분리: validation 3개월, test 4개월. 모델 선택은 validation MAE로 수행하고 test는 별도 평가.
- 검증에서 학습모델이 기준보다 낫지 않으면 기준모델을 선택할 수 있다. 선택된 학습모델이 test에서도 반드시 우수한 것은 아니다.
- 운영 추론은 Joblib/metadata를 읽으며, 원자료 fingerprint 불일치 검사로 학습 시점과 다른 데이터 사용을 탐지한다.
- 별도 `data_pipeline/nationwide_ml`의 전국 패널 실험은 현재 지역별 운영 registry와 구분한다.

### 현재 사용 아티팩트의 실제 평가 예시

| 지역/지표 | 관측 기간·test | 현재 선택 | 선택 MAE | 기준 MAE | 해석 |
|---|---|---|---:|---:|---|
| 원주 방문자 | 2024-01~2026-06, test 2026-03~06 | RandomForest | 103,646.64명 | 92,238.25명 | 기준보다 나쁨 |
| 원주 소비액 | 동일 | LinearRegression | 8,003,403,761.33원 | 4,727,706,750원 | 기준보다 나쁨 |
| 강남 방문자 | 2024-01~2026-07, test 2026-04~07 | RandomForest | 537,513.50명 | 673,789명 | 해당 test에서 기준보다 좋음 |
| 강남 소비액 | 동일 | 계절 기준모델 | 24,906,220,750원 | 동일 | 학습모델 개선으로 발표하면 안 됨 |

원주 30개월 관측에 lag12를 적용하면 학습 표본이 작다. 원주 target 학습월은 2025-01~11, 검증 2025-12~2026-02, test 2026-03~06이다. 강남은 31개월 관측, target 학습 2025-01~12, 검증 2026-01~03, test 2026-04~07이다. 서로 규모가 다른 지역의 MAE 절대값만 비교하지 않는다.

강남 방문자 MAPE는 선택 모델 3.05%, 기준 3.78%다. 원주 방문자는 4.37%, 기준 3.99%다. “정확도 97%”로 변환해 전체 서비스 성능으로 쓰지 않는다. 원주 spending MAPE 12.87%도 정책 효과 예측 정확도가 아니다.

현재 planning evidence는 원주에 2026-07~2027-02 예측을 만들고 사업 검토 3/6개월 창을 제시한다. 검증한 recursive horizon은 3개월이며 더 긴 창은 탐색적이다. 자연 추이가 사업 시행 시 증가분을 예측한 것은 아니다.

**발표해야 한다.** 본문 1~2장으로 “직접 학습→기준모델 비교→저장 추론→한계”를 보여주는 것이 적절하다. `artifacts/ml/11680/demand_model.metadata.json`, `51130/demand_model.metadata.json`을 사용한다. `artifacts/ml`에 남은 이전 강남 metadata를 현재 결과와 섞지 않는다. 총 metadata 90개와 활성 지역89개의 차이는 legacy 파일 존재 때문이며 지원 지역 증가로 해석하지 않는다.

## 18. 구현 완료와 미완성 분리

| 기능 | 상태 | 실제 동작 근거 | 발표 포함 추천 | 비고 |
|---|---|---|---|---|
| 메인/페이지 분기 | ✅ | 코드·루트200 | 포함 | 시각적 QA 별도 |
| 지역 카탈로그 | ✅ | 89개 응답 | 핵심 | 전국 전체 지원 아님 |
| 지도 | 🟡 | 코드/캐시 경로 | 사전 확인 후 | 외부 경계·UI 의존 |
| 원주 관광 조회·예측 | ✅ | dashboard200 | 핵심 | 관측/예측 시점 구분 |
| 등록 지역 전체 품질 | 🟡 | 모델 준비·감사 캐시 | 범위 설명 | 전 지역 신규 실행 미실시 |
| 직접 ML 학습/아티팩트 | ✅ | 현재 metadata/Joblib | 핵심 | 우수성은 지역별 다름 |
| 사업조건/첨부 | ⚪ | 폼/계약/추출 코드 | 입력 화면 | 이번 업로드 미실행 |
| Agent 생성 체인 | 🟡 | 저장 trace/실측 | 구조 설명 | 품질 미달, 최신 end-to-end 미승인 |
| 챗봇 | ⚪ | API/patch 코드 | 녹화/사전 검증 후 | 신규 질문 미실행 |
| 보고서 저장 조회 | ✅ | 5개/상세200 | 핵심 | 저장≠승인 |
| DOCX/PPTX | 🟡 | 코드·기존 산출물 | 검수된 파일만 | ready=false와 재생성 확인 필요 |
| PDF 출력 | 🔴 | endpoint 없음 | 제외 | PDF 입력과 혼동 금지 |
| Router 상태 | ✅ | 상태/effective route | 핵심 | 설정 변경 시연 불필요 |
| 관리자 설정 변경 | ⚪ | 토큰 검사/쓰기 코드 | 설명만 | 일반 사용자 인증 아님 |
| RAG 로컬 자료 검색 | 🟡 | 청크/카드/과거 trace | 범위 명시 | 의미검색 품질 미검증 |
| Chroma 의미 검색 운영 | ⚪ | 코드, embedding0 | 향후/현재 제한 | 활성 벡터 검색 주장 금지 |
| 무료 웹 검색 | ⚪ | 코드, provider없음 | 현재 제한 | 무료 조사 완료 아님 |
| 후속 성과 측정 | 🟡 | 스키마/API, 후속0 | 개선 계획 | 실제 효과 없음 |
| 학습 설명 화면 | ⚪ | 코드/카탈로그 | 보조 | 별도 유료 채팅 가능 |
| Streamlit 구조 탐색 | 🟡 | health200 | 보조 | 별도 실행 필요 |
| 회원/로그인/개인별 권한 | 🔴 | 완성 흐름 확인 못 함 | 완료 주장 금지 | LLM 관리 토큰과 다름 |
| 일반 사용자 피드백 제품 흐름 | 🔴 | 완성 UI/API 확인 못 함 | 향후 | 검토결과/측정 API와 구분 |
| 실시간 혼잡·인과효과 예측 | 🔴 | 구현 없음 | 제외 | 월별 예측과 다름 |
| 파인튜닝 | 🔴 | 실행 근거 없음 | 제안만 | 별도 승인 범위 |
| Nginx/AWS 운영 배포 | 🔴 | 설정/운영URL 확인 못 함 | 향후 | 로컬/LAN 실행 확인 |

### 자신 있게 보여줄 범위

지원 지역 조회, 대표 대시보드의 관측/예측, 직접 ML 평가 자료, 저장 보고서 조회, Router 현재 상태. 단, 각 화면은 발표 전 브라우저에서 점검한다.

### 설명은 가능하지만 즉석 Demo를 피할 범위

새 AI 기획 생성, 공식 웹 조사, 무료검색, 긴 챗봇 보완, 관리자 설정 변경, DOCX/PPT 재생성, 대량 지역 감사/재학습. 시간·외부 연결·비용·내용 품질 변수가 있다.

### 구현 완료라고 표현하면 안 되는 범위

검증된 고품질 관광기획 자동 생성, 전 지역 기준모델 초과, 정책의 실제 효과·성공률, 대규모 Chroma 의미검색, 실제 후속 측정, 파인튜닝, PDF 출력, AWS 운영 배포, 회원별 권한.

### 남은 기획 품질 이슈

`LOCAL_CANDIDATE_REPLAY_20260908.md`, `CANDIDATE_FLOW_EXPERIMENT_20260908.md`, DECISIONS D-102~D-108의 기록을 참고한다. 후보 유형·출처·분모 검사, 프롬프트/추론 모드/짧은 예시 비교를 보강했지만 실제 관광객 이용 절차와 사례 해석 문제 등이 남았다. 오류 개수 감소나 unittest 통과를 실제 기획 승인으로 바꾸지 않는다. 이번 작업은 이 품질 수정을 재개하지 않았다.

작은 이용 흐름 실험에서는 예시 없는 요청이 31.413초, 예시 포함 요청이 53.163초였다. 예시 없는 실제 답변은 “야간관광 특화도시 예산 편성”을 제안하고 원주 관측 사실 자리에 전주 사례 목적을 복사했다. 짧은 실행 단계에도 신청·지출 증빙·확인 행동이 부족했다. 예시 포함 후에도 품질 승인을 받지 못했다. 이 실험은 상세 예산·측정·Gemma 본문을 제외했으므로 전체 생성 실험과 시간/오류 수를 동등하게 비교할 수 없다. 작성 예시 사용 동의 역시 전문가의 사업 타당성 승인과는 다르다.

## 19. 3~5분 Demo 시나리오

권장 4분, **새 LLM 생성 대신 저장 결과와 호출 기록을 설명**한다.

| 시간 | 화면/행동 | 말할 내용 |
|---|---|---|
| 0:00~0:25 | 메인 | 대상은 관광 담당자, 데이터→검토용 기획 업무 지원 |
| 0:25~1:20 | 지원 지역 선택→대시보드 | 관측과 예측, 소비/체류, 선택 지역 연결. 원주 마지막 관측6월과 예측10월 구분 |
| 1:20~1:55 | 기획 여건 | 예산·기간·제약을 구조화하고 미정은 미정으로 유지. 생성 제출은 생략 |
| 1:55~2:55 | 저장 목록→상세 | 출처·본문·실행 단계·검토 상태. 미승인 초안임을 명확히 설명 |
| 2:55~3:30 | LLM 제어/trace | Qwen 후보·검토, Gemma 작성, 조건부 OpenAI 조사 |
| 3:30~4:00 | ML 평가/준비된 비교 그림 | 기준모델과 비교, 원주 반례, 이후 품질검증 과제 |

원주 저장 제목 “야간관광 특화도시 운영 예산 체계 구축”은 좋은 관광사업 후보로 승인된 사례가 아니다. 이를 대표 성공 결과로 내세우지 말고, 검토 상태를 남기는 기능의 사례로 사용한다. 결과의 품질을 홍보해야 하는 발표라면 사람이 검토한 별도 결과를 준비한 뒤 사용할 필요가 있다. 이번에 그 결과를 새로 만들지는 않았다.

리스크: LAN GPU/Ollama 연결, OpenAI quota/모델 접근/웹 검색 실패, 후보 gate422, 긴 생성시간, 지원하지 않는 지역, stale 데이터, 외부 경계 캐시 만료, 문서 재렌더 시간, Streamlit localhost가 다른 PC에서 가리키는 대상 차이. 발표 전 화면을 열어 확인하고 캡처/검수된 파일을 준비한다. 샘플 fallback을 쓸 경우 **개발용 예시**라는 표시를 유지한다.

## 20. 발표용 아키텍처

### 한 장용 간단 아키텍처

```text
 [관광 담당자]
       │ 지역 · 사업 여건
 [React / Vite]
       ├── /api ─ [지도 Backend] ─ [VWorld]
       └── /ai ── [AI Server]
                       ├─ [공식 파일 + MySQL]
                       ├─ [저장 ML 모델]
                       ├─ [공식 문서/사례 + TourAPI]
                       └─ [Qwen · Gemma · OpenAI]
                                  │
                  [기획 초안 · 출처 · 검토 상태]
                                  │
                    [저장 조회 · DOCX/PPTX]
```

### 기술 설명용 상세 아키텍처

```text
공식 다운로드 → raw/source_snapshots → data_pipeline
                                      ├─ catalog/processed
                                      └─ MySQL (월별·출처·비교·현황)
지역 pipeline → 시간순 학습/평가 → Joblib + metadata

React :5176 (Vite proxy)
 ├─ /api → FastAPI Backend :8100
 │           └─ VWorld WFS → 경계 정규화/단순화/24h cache
 └─ /ai  → FastAPI AI Server :8111
             ├─ raw_data_repository / registered region pipeline
             ├─ MySQL context stores / regional status JSON
             ├─ Joblib 추론 / planning ML evidence
             ├─ PlanningBrief 검증 / readiness
             └─ report job → Orchestrator
                  ├─ Evidence / CaseStudy
                  │    ├─ TourAPI / local RAG / case cards
                  │    └─ 조건부 OpenAI 공식 웹 조사
                  ├─ Transferability (Qwen) → Python gate
                  ├─ Planner (Gemma) ↔ Reviewer (Qwen)
                  └─ 조건부 final audit (OpenAI)
                        │ Router → Provider → usage/trace
                        ├─ LAN Ollama (Qwen/Gemma)
                        └─ OpenAI Responses
             결과 → MySQL strategy_reports/jobs/baseline
                  → Python DOCX/PPTX → storage/strategy_documents

별도: /project-tree → Streamlit :8501
현재 미가동 의미검색: Chroma 영속 collection, embedding 0
목표/미확인: Nginx → EC2 운영 배포
```

초기 문서의 8000/8001과 현재 실행 스크립트의 8100/8111을 혼용하지 않는다. 포트는 발표에서 반드시 외울 핵심은 아니지만 데모 환경표에는 실제 값을 쓴다.

## 21. 발표 PPT 구성 추천 — 18장

### Slide 01 — STAY-UP AI

- **핵심 메시지:** 공식 데이터에서 관광사업 검토 초안까지.
- **내용:** 프로젝트명, 한 줄 정의, 대상 사용자.
- **시각자료:** 대시보드 대표 화면 한 장.
- **발표:** 여행 일정 추천과 다른 담당자 업무 목적을 설명.

### Slide 02 — 해결하려는 문제

- **핵심 메시지:** 방문 규모만으로 체류·소비 전략을 결정하기 어렵다.
- **내용:** 지표 확인→예측→사례 조사→기획 작성의 연결 필요.
- **시각자료:** 현재 업무 단계 도식.
- **발표:** 정량 시간절감/시장 규모는 입증 자료 없이 넣지 않음.

### Slide 03 — 사용자와 서비스 목표

- **핵심 메시지:** 지자체 담당자의 검토를 돕는다.
- **내용:** 지자체·소상공인, 얻는 정보와 기획 산출물.
- **시각자료:** 사용자→지역/조건→결과 3칸.
- **발표:** 의사결정 지원이며 정책 효과 자동 보증은 아님.

### Slide 04 — 실제 서비스 흐름

- **핵심 메시지:** 지역 선택부터 저장 문서까지 이어진다.
- **내용:** 대시보드→사업조건→초안→검토→저장/출력.
- **시각자료:** 사용자 Flow와 페이지 작은 캡처.
- **발표:** 현재 품질검증 진행 상태를 한 줄 표시.

### Slide 05 — 공식 데이터와 지원 범위

- **핵심 메시지:** 등록된 지역·시점·출처를 기준으로 처리한다.
- **내용:** 데이터랩 파일, MySQL, TourAPI, VWorld, 공식 문서; 활성89지역.
- **시각자료:** 자료별 역할 표/지도.
- **발표:** 지도 전국 표시와 예측89지역 구분, 실시간 아님.

### Slide 06 — 데이터 신뢰성의 구현

- **핵심 메시지:** 지역·월·출처 계보를 보존한다.
- **내용:** region_code+year_month, source 연결, 최신성 검사, 미정값.
- **시각자료:** raw→정제→MySQL/ML 도식.
- **발표:** exact download URL 보완 과제를 함께 표시.

### Slide 07 — 대시보드

- **핵심 메시지:** 관광 현황과 예측을 한 화면에서 검토한다.
- **내용:** 월별 추이·예상 지표·소비/체류.
- **시각자료:** 실제 화면 확대.
- **발표:** 업종 예상 분포는 전체 소비 예측×관측 비중 가정.

### Slide 08 — 직접 학습한 ML

- **핵심 메시지:** LLM이 숫자를 예측하지 않는다.
- **내용:** 7지표, RF/LR/계절 기준, 시간순 분리, 저장 추론.
- **시각자료:** train/validation/test 타임라인.
- **발표:** 작은 표본, 모델 선택과 test 평가 분리.

### Slide 09 — ML 결과와 한계

- **핵심 메시지:** 지역별로 기준모델과 비교해 해석한다.
- **내용:** 강남 방문자 개선, 강남 소비 기준 채택, 원주 반례.
- **시각자료:** 선택/기준 MAE 비교표, 각 단위 표시.
- **발표:** 모든 지역 우수성·사업 효과 예측 주장 금지.

### Slide 10 — 전체 시스템 구조

- **핵심 메시지:** 지도 서버와 관광/AI 서버를 분리했다.
- **내용:** React의 /api·/ai 분기, MySQL/ML/근거/LLM.
- **시각자료:** 20절 간단 아키텍처.
- **발표:** 일반 Backend를 통해 모든 AI 요청이 흐른다고 그리지 않음.

### Slide 11 — 사업조건을 구조화하는 기획 입력

- **핵심 메시지:** 같은 통계라도 사업 여건이 다르면 기획이 달라져야 한다.
- **내용:** 예산·기간·자원·제약·첨부, 미정 상태.
- **시각자료:** 기획 입력 폼.
- **발표:** 사용자 진술과 공식 사실을 구분.

### Slide 12 — Agent Pipeline

- **핵심 메시지:** 조사·후보 비교·작성·검토를 분리한다.
- **내용:** Evidence/CaseStudy→Transferability→Planner→Reviewer.
- **시각자료:** 9절 pipeline.
- **발표:** 검사 실패 시 중단, 무제한 자율 Agent가 아님.

### Slide 13 — Qwen·Gemma·OpenAI의 역할

- **핵심 메시지:** 역할별 모델과 실제 호출 정책을 관리한다.
- **내용:** 현재 local_first, Qwen 후보/검토, Gemma 본문, OpenAI 조건부 조사/감사.
- **시각자료:** 역할표와 effective route 캡처.
- **발표:** 완전 무료 아님, 자동 유료 fallback은 꺼져 있음.

### Slide 14 — 근거와 검토 상태가 있는 초안

- **핵심 메시지:** 결과와 함께 출처·미해결 문제를 보여준다.
- **내용:** report·sources·gaps·quality_review·trace.
- **시각자료:** 저장 상세의 출처/미승인 표시.
- **발표:** 원주 미승인 결과를 성공 기획으로 소개하지 않음.

### Slide 15 — 저장·보완·업무 문서

- **핵심 메시지:** 생성 결과가 업무 산출물로 이어진다.
- **내용:** 저장 게시판, 제한된 챗봇 patch, DOCX/PPTX.
- **시각자료:** 목록→상세→검수된 출력물.
- **발표:** PDF 출력 미구현, 출력 가능과 승인 구분.

### Slide 16 — 실제 Demo

- **핵심 메시지:** 현재 확인된 흐름을 보여준다.
- **내용:** 19절 4분 흐름; 실시간 생성은 생략.
- **시각자료:** 라이브 화면/준비된 캡처.
- **발표:** 데이터 조회→조건→저장결과→모델 역할 연결.

### Slide 17 — 구현 결과와 차별점

- **핵심 메시지:** 데이터·모델·기획·문서를 연결한 것이 구현 성과다.
- **내용:** 활성89지역, 실DB/저장 조회, 직접ML, Agent/Router, 출력 경로.
- **시각자료:** 완료/검증중 두 영역 표.
- **발표:** DB행 수·저장5개를 사업 성공/이용자 수로 해석하지 않음.

### Slide 18 — 남은 과제와 다음 검증

- **핵심 메시지:** 실제 응답 품질과 일반화 검증이 다음 과제다.
- **내용:** 이용 절차/사례 해석, 예산·측정 타당성, 별도 지역 평가, 문서 QA, 후속 관측, 운영 배포.
- **시각자료:** 우선순위 3단계: 기획 품질→지역/통합 검증→운영.
- **발표:** 새 라이브러리·파인튜닝·유료 확대는 구현 완료가 아닌 별도 검토 방향.

## 22. 발표에서 강조할 TOP 10

1. **담당자 업무 목적:** 서비스 정체성을 바로 이해하게 한다.
2. **공식 관광 데이터와 출처 연결:** 근거가 무엇인지 확인할 수 있다.
3. **관측·예측·목표 구분:** 결과를 잘못 해석하지 않게 한다.
4. **실제 지역 대시보드:** 구현을 가장 빠르게 보여준다.
5. **직접 ML 학습과 기준 비교:** 분석이 단순 LLM 설명에 그치지 않는다.
6. **사업조건 구조화:** 지역/예산/현장 여건이 입력에 포함된다.
7. **후보 비교→본문 작성 분리:** 현재 AI 설계의 핵심이다.
8. **모델 Router와 trace:** 어떤 모델이 무엇을 했는지 설명 가능하다.
9. **저장·DOCX/PPTX 연결:** 업무 결과물로 이어진다.
10. **한계를 드러내는 검증:** 품질 미달과 기준모델 반례를 숨기지 않아 발표 신뢰성을 높인다.

## 23. 예상 기술 질문 15개와 답변

1. **왜 데이터랩 자료인가?** 프로젝트 목적에 맞는 공식 방문·소비·체류 지표이기 때문이다. 지역·월·출처를 유지하지만 표본/집계 정의의 한계는 남는다.
2. **실시간 데이터인가?** 월별 통계는 다운로드·정제·적재한 자료다. TourAPI/경계 요청과 월별 통계 갱신은 별개다.
3. **전국 모든 지역이 되나?** 현재 활성 모델 카탈로그는 89개다. 지도 범위·DB 지역 차원·예측 지원 수는 다르다.
4. **머신러닝을 직접 학습했나?** RF/LR와 계절 기준을 시간순으로 비교해 Joblib로 저장했다. 화면에서는 저장 모델을 읽는다.
5. **성능은 좋은가?** 강남 방문자는 해당 test에서 기준보다 좋지만 원주 방문·소비는 나쁘다. 전체 우수성을 주장하지 않는다.
6. **사업을 하면 얼마나 늘어나는지 예측하나?** 현재 ML은 자연 추이 예측이다. 사업 목표 시나리오나 입력 목표는 인과효과 예측이 아니다.
7. **OpenAI는 어디에 사용하나?** 현재 정책에서 공식 웹 조사·사례 보완·조건부 최종 검토·조사 채팅, 별도 학습 Assistant 등에 사용한다.
8. **Qwen과 Gemma는 왜 나눴나?** 후보 판단/검토와 본문 작성을 분리하기 위한 구현이다. 분리만으로 품질 개선이 검증됐다고 말하지 않는다.
9. **Agent는 자율적으로 학습하나?** 아니다. 정해진 역할·입력·출력·도구 제한·호출 순서를 가진 코드 모듈이다.
10. **일반 ChatGPT와 무엇이 다른가?** 지역별 실제 데이터·저장ML·사업조건·출처·검토·저장/문서 흐름을 애플리케이션에 연결했다. 모델 자체 우월성 주장은 아니다.
11. **RAG가 가동 중인가?** 로컬 공식 청크/요약/사례 검색 경로가 있다. Chroma 연동 코드도 있지만 현재 embedding 0이라 대규모 의미검색 검증 완료라고 할 수 없다.
12. **잘못된 기획은 차단되나?** 후보/출처/조건 검사와 검토가 있고 일부 실패를 중단한다. 그러나 의미적 오류가 남아 있으며 저장·출력이 모두 승인 전용은 아니다.
13. **로컬 모델이 실패하면 유료 호출하나?** 현재 local_first의 자동 유료 fallback은 꺼져 있다. 다른 모드의 fallback 코드 및 원래 유료 조사 경로와 구분한다.
14. **DB와 문서는 어떻게 저장하나?** MySQL에 관광/출처/보고서 JSON·파일 경로를 저장하고 DOCX/PPTX는 서버 storage에 둔다. 조회는 AI Server를 거친다.
15. **실제 효과와 배포는 검증했나?** 후속 측정은 0행이고 Nginx/AWS 운영 배포 근거는 없다. 현재는 로컬 서비스 구현과 기획 품질 검증 단계다.

## 24. PPT 제작용 Executive Summary

**프로젝트명:** STAY-UP AI (저장소 TP2-3).

**한 줄 설명:** 공식 관광지표·ML 예측·공식 사례를 연결해 지자체 관광 담당자의 지역사업 기획 초안 작성을 돕는 서비스.

**핵심 문제:** 방문 규모를 확인하는 것만으로 체류·소비 개선 사업을 설계하기 어렵고, 지표·예측·사례·문서 작업을 연결할 필요가 있다. 업무시간/경제효과 수치 근거는 별도 확인 필요.

**해결 방법:** 지역 선택→관측/예측 조회→사업 여건 입력→근거 수집→후보 비교→본문 작성/검토→저장/문서화.

**사용자:** 지자체 관광 담당자와 관광 소상공인. 여행 일정 추천 이용자가 아님.

**핵심 데이터:** 데이터랩 월별 파일, MySQL의 관광지표/비교/출처, TourAPI 관광자원, VWorld 경계, 공식 정책 청크/사례 카드. 현재 활성89지역, 지역별 갱신월 다름.

**핵심 기술:** React/Vite·Recharts·Leaflet, FastAPI 2개, MySQL/PyMySQL, Pandas/scikit-learn/Joblib, OpenAI/Ollama Router, python-docx/python-pptx. 현재 로컬/LAN 개발 실행이며 AWS 운영 배포는 미확인.

**AI 역할:** sklearn 모델이 자연 추이를 예측. Qwen3:14b가 후보 비교/적용성/검토/설명, Gemma4:26b가 본문 작성/수정, OpenAI가 조건부 공식 조사·최종 검토 등을 담당. LLM 자체를 학습/파인튜닝한 것은 아님.

**주요 기능:** 지역 대시보드, 사업조건 입력, Agent 기획 초안, 출처·검토 상태, AI 보완, 저장 게시판, DOCX/PPTX, 모델 제어·평가 설명 화면.

**차별점:** 데이터·예측·조건·근거·모델 역할·검토·문서를 연결한 업무 흐름. 경쟁서비스 대비 품질 우위나 비용 절감률은 검증하지 않음.

**최종 결과:** 대표 지역 조회/예측, 89지역 모델 등록, MySQL 실제 데이터, 보고서5개 조회, Agent/Router·출력 코드와 기존 산출물이 있다. 원주 현재 보고서는 미승인이고, 일부 ML은 기준보다 낮으며, 후속 사업 성과·운영 배포는 미완료다. 이를 **검증된 정책 자동화 완성품**으로 소개하지 않는다.

**가장 보여줄 화면 5개:** 지역 대시보드 / 사업조건 입력 / 저장 보고서 상세와 출처·미승인 표시 / ML 기준모델 비교 / LLM effective route·trace.

**발표 핵심 메시지 5개:**

1. 관광 담당자의 의사결정을 지원한다.
2. 공식 관측·ML 예측·사업 목표를 구분한다.
3. 후보 비교와 본문 작성을 나누고 출처를 남긴다.
4. 결과를 저장·보완·업무 문서로 연결한다.
5. 구현 성과와 아직 검증되지 않은 품질·효과를 정확히 구분한다.

**권장 구성:** 본문18장. 문제→업무흐름→데이터→ML와 한계→구조→Agent/Router→저장/문서→실제 데모→구현 결과/다음 검증. DB 상세·전체 API·기존 실측은 발표자 참고/부록 후보.

**제작 금지 표현:** 완벽한 기획, 환각 제거, 전 지역 정확도97%, 실제 관광매출 증가, 완전 무료, 모든 자료 실시간, 벡터 검색 운영 완료, 파인튜닝 완료, PDF 출력/EC2 배포 완료. 미승인 표시를 잘라내지 않는다.

## 25. 근거 파일과 재확인 위치

경로는 저장소 루트 기준이다. 최종 발표 제작자는 실제 화면/현재 응답을 다시 확인하고 날짜를 붙인다. 비밀값을 담은 `.env`를 캡처하지 않는다.

| 주제 | 핵심 근거 |
|---|---|
| 목적/결정/제한 | `AGENTS.md`, `docs/PROJECT_BRIEF.md`, `ARCHITECTURE.md`, `DATA_AND_AI_RULES.md`, `IMPLEMENTATION_PLAN.md`, `CONTEST_EVIDENCE.md`, `DECISIONS.md` |
| 최근 기획 품질 | `docs/LOCAL_CANDIDATE_REPLAY_20260908.md`, `docs/CANDIDATE_FLOW_EXPERIMENT_20260908.md`, DECISIONS D-102~D-108 |
| 실행 환경 | `start-dev.ps1`, `setup-dev.ps1`, `frontend/vite.config.js`, `project_tree_explorer/start-streamlit.ps1` |
| 화면/라우팅 | `frontend/src/App.jsx`, `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/App.css` |
| Frontend API | `frontend/src/api/dashboardApi.js`, `llmControlApi.js`, `mlLearningApi.js`, `projectLearningApi.js` |
| 지도 | `backend/app/main.py`, `backend/app/services/vworld.py`, `backend/app/config.py` |
| 관광/기획 API | `ai_server/app/main.py` |
| 데이터 조회 | `ai_server/app/raw_data_repository.py`, `nationwide_context_store.py`, `nationwide_bigdata_store.py`, `regional_tourism_status_store.py` |
| 지역 등록 | `data/catalog/region_data_registry.csv`, `ai_server/ml/region_catalog.py`, `region_registry.py`, `regional_datalab_data.py` |
| ML | `ai_server/ml/gangnam_forecast.py`, `evaluation.py`, `planning_evidence.py`, `learning_catalog.py`; `artifacts/ml/11680/demand_model.metadata.json`, `artifacts/ml/51130/demand_model.metadata.json` |
| 정제/학습 batch | `data_pipeline/tools/`, `data_pipeline/nationwide_ml/` |
| 외부/공식 근거 | `ai_server/app/tourism_open_api.py`, `rag_store.py`, `local_web_search.py`, `case_registry.py`, `evidence_sources.py`, `data/rag/` |
| 사업조건 | `ai_server/app/planning_brief.py`, `frontend/src/features/planning/` |
| Agent | `ai_server/app/agents/report_orchestrator.py`, `evidence_agent.py`, `case_study_agent.py`, `transferability_agent.py`, `planner_agent.py`, `reviewer_agent.py`, `chat_assistant_agent.py` |
| 품질 검사 | `ai_server/app/agents/plan_quality_gate.py`, `planning_requirements.py`, `decision_facts.py`, `ai_server/app/report_review_status.py` |
| Router/Provider | `ai_server/app/llm/router.py`, `models.py`, `openai_provider.py`, `ollama_provider.py`, `trace_store.py`, `local_agent.py`, `evidence_tools.py` |
| DB/저장 | `database/mysql/*.sql`, `ai_server/app/strategy_store.py` |
| 문서 출력 | `ai_server/app/proposal_document.py`, `proposal_presentation.py`, `proposal_presentation_v4.py`, `proposal_slide_content.py`, `proposal_layout_v9.py`, `storage/strategy_documents/` |
| 보조 학습 | `ai_server/app/project_learning_catalog.py`, `agents/ml_learning_assistant_agent.py`, `agents/project_learning_assistant_agent.py`, `frontend/src/pages/MlTest/` |
| 구조 탐색 | `project_tree_explorer/`, `frontend/src/pages/ProjectTreePage.jsx` |
| 테스트 위치 | `tests/nationwide_pipeline/`, `ai_server` 내부 테스트, `frontend/src/features/planning/*.test.*` — 존재/기록과 이번 실행을 구분 |

### 기존 문서와 현재 구현을 구분해야 하는 항목

| 혼동 가능 설명 | 이번 조사에서 확인한 현재 상태 |
|---|---|
| Backend→AI Server 단일 직렬 구조 | React가 두 서버에 각각 요청 |
| Backend가 관광 MySQL을 담당 | 현재 주요 관광/보고서 DB 접근은 AI Server |
| 모든 숫자는 MySQL 조회 | 지역 대시보드/학습용 파일과 JSON도 런타임 사용 |
| 43지역 또는 3지표 | 현재 활성89지역/7예측 지표 |
| student_budget가 현재 모드 | 실제 응답은 local_first |
| 설정된 fallback이 항상 실행 | effective route가 정책에 따라 none으로 제한 |
| 생성 성공=승인=저장=출력 가능 | 별개 상태; 미승인 저장·출력 가능 경로 있음 |
| Chroma 파일 존재=의미검색 준비 | embedding0, 로컬 문서 검색과 구분 |
| 모델DB 테이블 존재=운영 등록 | ml_model_registry/ml_prediction은0행, 파일 모델 사용 |
| PDF 파일 존재=PDF 출력 서비스 | 입력/검수 자료와 다름, PDF 출력 endpoint 없음 |
| 포트8000/8001 | 현재 개발8100/8111, React5176 |
| AWS/Nginx 배포 목표 | 실행 설정/운영URL 근거 미확인 |

이 문서는 구현 현황을 설명하는 발표 원본이다. 승인되지 않은 기획을 승인하거나, 계획된 개선을 구현된 성과로 바꾸는 자료가 아니다.
