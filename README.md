# STAY-UP AI

후보 이용 흐름의 짧은 요청과 사용자 승인 작성 예시를 비교했습니다. 예시 포함 시 원주 출처 연결·단계 구조는 달라졌지만 구체적 이용 절차와 사례 해석 문제가 남아 미승인입니다([기록](docs/CANDIDATE_FLOW_EXPERIMENT_20260908.md)).

동일 최종 입력의 Qwen `think=false/true` 비교 진단을 실행했습니다. 각각 252.5초/194.3초에 응답했지만 실제 내용에 예산·측정·근거 오류가 남아 둘 다 미승인입니다. 운영 모드는 유지합니다. 재현 명령과 응답별 검토는 [실측 기록](docs/LOCAL_CANDIDATE_REPLAY_20260908.md)의 D-107을 참고하세요.

최초 설계 비교 진단(`--fresh`)에서도 후보 품질 미달을 확인했습니다. 후보 유형·우회 제목·근거 없는 성공률 검사를 보강했고 관련 테스트 102개를 통과했습니다. 전체 기획안 생성 성공과는 구분합니다([실측](docs/LOCAL_CANDIDATE_REPLAY_20260908.md)).

후보 재비교는 오류가 있는 이전 선정 사례를 우선하지 않고, 지역 관측 도구에 등록 데이터 출처 ID를 함께 전달합니다(D-104). 기존 보고서를 수정하거나 자동 승인하지 않습니다.

로컬 후보 보완 후속: 예산·측정·지역 적합성·출처의 필드별 작성 지시와 전체 피드백 전달을 보강했습니다. 코드 회귀와 실제 모델 품질 결과는 [실측 기록](docs/LOCAL_CANDIDATE_REPLAY_20260908.md)에서 구분합니다.

기획안·챗봇 최신 점검: [실제 로컬 응답·수정 범위·남은 품질 조건](docs/QUALITY_INTEGRATION_AUDIT_20260907.md). 연결 성공과 기획안 최종 승인은 구분합니다.

관광 빅데이터를 활용하여 인구감소지역의 관광수요를 예측하고 체류·소비 활성화 전략을 생성하는 공모전 프로젝트입니다.

## 시작하기 전

지역 선택창의 초록색은 최근 점검에서 데이터·저장 기획안 목표/검수·문서 출력이 통과한 지역입니다. 미래 생성 성공 보장이 아닙니다. `python -m ai_server.app.scripts.audit_all_regions`로 읽기 전용 재점검하며 24시간 뒤 표시를 만료합니다. 실행에는 로컬 AI 서버 8112가 필요합니다.

2026-09-07: [원주 기획안 정밀 점검·필요 자료 목록](docs/WONJU_PROPOSAL_QUALITY_AUDIT_20260907.md),
[전국 사례 선택 정책](docs/NATIONWIDE_CASE_SELECTION.md), [전체 기획안 생성 준비도 점검](docs/PROPOSAL_READINESS_AUDIT_20260907.md)을 추가했습니다.
후보 비교의 보완은 Qwen, 본문 보완은 Gemma로 분리하며 비용·KPI·실행 조건을 공통 검사합니다.
검토 페이지는 전체 코드 점검과 준비할 자료 목록을 표시합니다. 기존 저장 보고서는 자동 수정하지 않습니다.

PowerPoint 출력은 승인 디자인의 v6 원본 위에 v9 출력 레이아웃을 적용합니다. 6장 실행 개요 다음에 7장 세부 실행내역을 추가하며, 단계·기간 열과 표 제목 가운데 정렬을 적용합니다.
사업 설명과 3개월 ML예측치·목표 KPI 비교 차트, 4개 사례, 4단계 실행표를 제공합니다.
중복 예측·지속 운영 장을 제거하여 출처는 10장부터 1~2장, 감사 장을 포함해 총 11~12장입니다. 방문·소비 표는 분리하고, 목표 증가율과 월별 합계를 표시합니다. 사례는 선정 자료를 유지한 채 서로 다른 운영방식을 우선 배치합니다. 저장된 기획서의
PowerPoint를 다시 다운로드하면 재생성하며, 이 과정에 OpenAI·Ollama 생성 호출은 없습니다.
수치 예측과 사업 효과·가정 목표의 경계는 `docs/DECISIONS.md`의 D-089를 참고합니다.

현재 로컬 우선 기획의 구현 범위·비용 제한·남은 GPU/PPT 검증은
[`docs/LOCAL_FIRST_QUALITY_PLAN.md`](docs/LOCAL_FIRST_QUALITY_PLAN.md)를 먼저 확인합니다.
기본 `student_budget` 모드에서는 Qwen·Gemma가 비교·작성·재검수를 맡습니다. `TAVILY_API_KEY` 등 무료 검색 API 키를 설정하면 Qwen이 만든 최대 2개 검색 질문으로 허용된 공식 도메인의 제목·URL·요약 후보를 제한 조회할 수 있습니다. 이 후보는 원문 검수 전 확정 근거나 RAG 문서가 아니며, MySQL·ML·공식 Open API·검수 RAG가 계속 사실 근거를 담당합니다. OpenAI는 로컬 검수를 통과한 결과의 독립 최종 검수 1회에만 사용하고, OpenAI Web Search는 자동 실행하지 않습니다. 저장 근거가 부족하면 승인되지 않은 검토용 초안으로 남습니다. 최신 지역 정책·사례를 자동 조사해야 할 때만 `local_first`를 선택합니다.

기획안의 단계별 출력 상한·토큰 부족 시 1회 재시도 정책은
[`docs/GENERATION_TOKEN_BUDGETS.md`](docs/GENERATION_TOKEN_BUDGETS.md)에 정리했습니다.
이는 완료 가능성을 높이는 설정이며 연결·결제 오류까지 방지하거나 생성 품질을 보장하지 않습니다.

Codex 또는 팀원은 먼저 루트의 `AGENTS.md`와 아래 문서를 순서대로 읽습니다.

- `docs/PROJECT_BRIEF.md`: 프로젝트 기획
- `docs/ARCHITECTURE.md`: 시스템·데이터·AI 구조
- `docs/DATA_AND_AI_RULES.md`: 데이터와 AI 사용 원칙
- `docs/IMPLEMENTATION_PLAN.md`: 단계별 개발 계획
- `docs/CONTEST_EVIDENCE.md`: 공모전 성과 증빙 기준
- `docs/DECISIONS.md`: 확정·미확정 결정 사항
- `docs/DATA_SOURCE_USAGE.md`: ZIP·Open API별 사용 위치와 연결 상태
- `docs/NATIONAL_DATA_AND_CASE_STORAGE.md`: 전국 시군구 수치·ML·공식사례 저장 구조
- `docs/REPORT_QUALITY_AND_COST_EVOLUTION.md`: 기획안 품질과 비용 개선 이력

## 현재 상태

### 전국 데이터 확장 파이프라인 (2026-09-01)

- 전국 공식 관광 원본을 서비스 코드와 분리해 검증·정규화하는 자산은 `data_pipeline/`에 둡니다. 결과는 `data/processed/nationwide/`, 모델 산출물은 `artifacts/nationwide/`, MySQL 적재 스키마는 `database/mysql/`에 있습니다.
- 원본 ZIP/CSV는 Git에 올리지 않습니다. 수동 보관 원본은 `data/raw/`에 그대로 남기고, **활성 ML 카탈로그는 hash 검증 불변 복제본 `data/source_snapshots/`만 읽습니다.** 공유폴더의 서울·강원·경기·경남 자료와 기존 인천 CSV를 이 경로에 보관해 네트워크 연결이 없어도 재현합니다. 강남구의 2026년 7월 보완 ZIP도 같은 snapshot 아래에 명시적으로 보관합니다. 2026-09-03 원본에서 같은 경로·다른 hash로 갱신된 강원 30일 집중률은 `versioned_conflicts/20260903/`에 별도 보관하며 기존 원본을 덮어쓰지 않습니다.
- 지역별 관광 현황 ZIP은 별도 `data/source_snapshots/regional_tourism_status/`에 불변 복제하고, 254개 매핑 지역의 유입·유출 권역·인기장소·30일 집중 운영 신호를 MySQL과 Agent 읽기 전용 사실표에 연결했습니다. Agent에는 반복 식별 열을 뺀 상위 3건·비율·출처의 명시적 요약만 전달하며, 원본 snapshot은 요청 범위에 그대로 보존합니다. 이 자료는 ML 학습값·정책효과가 아니라 기획 후보의 권역·장소·분산 운영 근거입니다.
- 전국 수치를 화면과 기획서 근거로 사용하기 전에는 MySQL 적재, 지역별 시간순 ML 평가, AI Server 입력 연결을 별도로 검증해야 합니다. 자세한 내용은 `data_pipeline/README.md`와 `docs/nationwide/`를 확인합니다.

### 공식 PDF 참고문서 RAG (2026-09-02)

- 한국관광공사 「요즘, 한국관광 2호」와 제2회 데이터 세미나 자료집의 원문 사본은 `data/rag/source_documents/`에 로컬 보관하고, 검수한 정책·운영·지표 해석은 `data/rag/official_reference_documents.jsonl`에 등록합니다.
- 이 레지스트리는 ChromaDB 임베딩을 새로 만들지 않아도 무료 키워드 검색으로 Evidence/Case Scout Agent에 전달됩니다. 월별 수치·가상 화면·향후 공개 예정 정보는 정확한 관측값이나 예측 근거로 사용하지 않습니다.

### 전략기획 입력 페이지 (2026-08-28)

- 메뉴: 지역선택 → **전략기획** (`/planning`) → AI 전략기획 (`/strategy`) → 저장된 기획서.
- 공무원은 예산·추진 시기·확보/협의 중인 자원·필수 제약을 제공합니다. 분야·목표·사업 방식은 정답으로 요구하지 않으며 AI가 원자료와 공식 사례로 제안합니다. 현장 정보·선호·참고자료는 선택 입력입니다.
- 미정은 0원·확정으로 바꾸지 않습니다. 필수 제약과 선호를 구분하고, 사용자 문서를 공식 근거로 취급하지 않습니다.
- **데이터 최신성 보호:** 새 기획안을 요청할 때 마지막 확정 관측월 다음 달부터 직전 완료월까지의 공백을 계산합니다. 공백이 3개월 이상이면 생성만 중단하고, 필요한 시작·종료월과 `원자료 적재 → 기간·지역코드·단위 검증 → ML 재학습 → 계절 기준모델 비교` 절차를 표시합니다. 진행 중인 이번 달은 누락으로 계산하지 않으며, 대시보드·저장 기획안·기존 Word/PPT 열람은 계속 가능합니다.
- 초안은 지역별 브라우저 localStorage에 임시 저장합니다. 단, 첨부 문서의 본문은 브라우저·결과·저장된 보고서에 남기지 않고 생성 작업 중에만 사용합니다. 생성 당시 조건은 작업·결과·저장된 보고서에 복사되고 Word/PPT에 예산·일정 요약을 표시합니다. 작업 상태와 완료 결과는 MySQL에 저장합니다. 첨부가 없는 중단 작업은 AI Server 재시작 뒤 재개하며, 첨부가 있던 작업은 본문 비저장 원칙 때문에 재요청을 안내합니다.
- 참고자료: 한글(HWPX)·Word(DOCX)·텍스트(TXT/MD)·PDF·Excel(XLSX)을 파일당 2MB·6,000자, 최대 3개까지 받습니다. 텍스트만 메모리에서 추출하고 원본·공용 RAG·서버 DB에는 저장하지 않습니다. 생성 요청 시 모델 입력에 포함되므로 개인정보·민감정보는 제외합니다. 기존 HWP는 HWPX 또는 PDF로 저장해 첨부합니다.
- PDF·Excel 참고문서 추출에는 `pypdf`, `openpyxl`을 사용하며 `requirements.txt`에 기록합니다.
- 개발 위치: `frontend/src/features/planning/`, `frontend/src/pages/TourismPlanningPage.jsx`, `ai_server/app/planning_brief.py`. 조건별 지시문은 `ai_server/app/agents/prompts.py`의 `PLANNING_CONTEXT_RULES`에서 관리합니다.
- 검증 명령: `python -m unittest ai_server.test_planning_brief ai_server.test_report_orchestrator`, frontend에서 `npm test`, `npm run lint`, `npm run build`.

### 강남구 3개월 수요 예측 (2026-08-28)

- 개발 위치: `ai_server/ml/`. 원본 ZIP을 읽는 `gangnam_data.py`, 학습·평가·예측을 담당하는 `gangnam_forecast.py`, 수동 재학습 CLI `train_gangnam.py`로 나뉜다.
- 화면: 강남구 지역선택 대시보드에서 최근 3개월 관측값과 다음 3개월 ML 예측을 함께 보여 준다. 상단 카드는 다음 달 예상 순 방문자 수·관광소비액으로 변경된다.
- 모델: 방문자 수는 RandomForestRegressor, 소비액은 LinearRegression, 평균 숙박일수는 LinearRegression 또는 전년 동월 기준선이다. 최근 4개월 시간순 테스트에서 방문자·소비액 모델은 전년 동월 seasonal-naive 기준선보다 MAE가 낮을 때만 저장하며, 상단 카드는 현재 달의 다음 달 예측을 표시한다.
- 확장 구조: `ai_server/ml/region_registry.py`에 지원 시군구를 등록하고, `region_service.py`를 통해 API와 일괄 학습 CLI가 같은 지역 모델을 호출한다. 전처리·모델 파일은 각각 `data/processed/ml/<지역코드>/`, `artifacts/ml/<지역코드>/`로 분리한다.
- 재학습: `./backend/.venv/Scripts/python.exe -m ai_server.ml.train_gangnam`. 저장 파일은 `artifacts/ml/`, 재현용 월별 표는 `data/processed/`에 생성한다.
- 업종별 예상 소비 패턴은 별도 업종 모델이 아니라 최신 관측 업종 비중을 전체 소비액 예측에 적용한 가정이다.

현재는 **React + Vite 대시보드, 지도 FastAPI, 지역 원본 기반 Multi-Agent 전략 보고서 AI 서버를 만든 단계**입니다. `/` 소개 화면과 `/dashboard` 업무 화면은 페이지 단위로 지연 로딩되며, 대시보드에는 도·시·군·구 검색과 `전국 시도 선택 → 선택 시도의 시군구 선택` 2단계 지도가 있습니다.

- 실제 월간 카드·차트·소비 진단과 전략기획의 ML 근거는 원본·7개 target·시간순 평가를 모두 통과한 지역에만 연결합니다. 현재 서울 25개 자치구, 강원 17개 시군구, 인천광역시 계양구, 경기도 43개 시군구, 경상남도 3개 시군구까지 **89개 지역**이 준비돼 있으며, React 선택기는 `/ai/v1/regions/catalog`에서 이 목록을 자동으로 읽습니다.
- 원본이 불완전한 지역은 예시 숫자를 대신 보여 주지 않고 선택 목록에서 제외합니다. 예를 들어 양양군은 2025년 방문자 archive를 보완하고 사전점검·학습을 다시 마쳐야 활성화됩니다. OpenAI는 월간 수치를 만들지 않습니다.
- 원본 ZIP 표는 수정하지 않으며, 파일 경로·크기·수정시각 지문이 같을 때 파싱 결과를 메모리에서 재사용합니다. 원본이 바뀌면 캐시는 자동 무효화됩니다.
- 강남구 AI 보고서는 원본 ZIP의 관측값과 OpenAI의 실행 제안을 구분합니다.
- 지역 선택의 `지역 정보 상세보기`는 OpenAI를 호출하지 않고, 서버가 한국관광공사 국문 관광정보 Open API에서 읽은 관광자원 정보를 월간 원자료 요약과 분리해 보여 줍니다.
- AI 전략기획 생성은 서버 백그라운드 작업으로 실행합니다. 화면을 다른 업무 페이지나 탭으로 바꿔도 작업 ID를 통해 상태를 이어서 확인하며, MySQL의 작업 상태와 완료된 기획안·Word/PPT를 다시 조회합니다.
- 기존 `test-gangnam-dashboard/`는 별도의 Streamlit 프로토타입으로 유지합니다.
- React 공개 경로는 `frontend/src/routes.js`에서 관리합니다. 주요 업무는 `/dashboard`, `/planning`, `/strategy`, `/saved-plans`이며 `/diagnosis`는 `/dashboard`, `/proposal`은 `/strategy`의 과거 주소 별칭입니다. 알 수 없는 경로는 404 안내를 표시합니다.

## 팀원 최초 설치

Git으로 받은 직후에는 `backend/.venv`, `frontend/node_modules`, `.env`가 없는 것이 정상입니다.
각 PC에서 새로 만들며 Git에 올리지 않습니다.

### 준비물

- Windows 10/11, Git, VS Code
- Python 3.10 이상 (`python --version`으로 확인)
- Node.js 20.19 이상 또는 22.12 이상 (`node --version`으로 확인)
- 실제 대시보드 수치를 보려면 팀 공유 드라이브의 관광 원본 데이터 묶음
- AI·지도·저장 기능까지 사용할 경우 팀에서 안전하게 전달받은 `.env` 값과 MySQL 정보

### 가장 쉬운 방법

VS Code에서 프로젝트 루트를 연 뒤 터미널에 아래 두 줄을 실행합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\setup-dev.ps1
```

`setup-dev.ps1`는 아래만 자동으로 처리합니다.

1. `backend/.venv` 생성
2. 루트 `requirements.txt`의 Python 패키지 설치
3. `frontend/package-lock.json` 기준 `npm ci` 설치
4. `.env.example`을 `.env`로 복사하되, 기존 `.env`는 덮어쓰지 않음
5. Git에서 제외된 관광 원본 파일이 있는지 확인

이미 설치한 패키지를 다시 설치하려면 아래를 사용합니다.

```powershell
.\setup-dev.ps1 -Refresh
```

### 팀 공유 파일과 비밀정보

| 구분 | Git 포함 여부 | 팀원이 준비할 내용 |
|---|---|---|
| Python 가상환경·`node_modules` | 제외 | `setup-dev.ps1`가 PC별로 생성 |
| 실제 관광 원본 ZIP/CSV/Excel | 제외 | 팀 공유 드라이브에서 `data/raw/` 아래 같은 구조로 복사 |
| ML 모델 artifact | 포함 | 별도 복사 불필요 |
| `.env` API 키·DB 비밀번호 | 제외 | `.env.example`을 복사한 뒤 팀에서 전달받은 값만 직접 입력 |
| MySQL 데이터베이스 | 제외 | 저장 기능까지 시연할 팀원 PC에서 MySQL 생성·계정 설정 |

원본 데이터가 없으면 숫자를 예시값으로 바꾸지 않고 `원자료 미연결` 상태가 표시됩니다. `.env`에는 OpenAI 키나 DB 비밀번호가 있으므로 Git에 추가하거나 단체 채팅에 올리지 않습니다.

- Python Backend와 AI Server의 공통 의존성은 루트 `requirements.txt`로 설치한다.
- React/Vite·지도·그래프 의존성은 `frontend/package-lock.json` 기준으로 `npm ci`로 설치한다.
- 새 라이브러리를 실제 코드에 추가하면 같은 변경에서 `requirements.txt` 또는 `frontend/package.json`과 lock 파일을 갱신한다.

## 프론트엔드 실행

최초 설치가 끝난 뒤 세 서버를 한 번에 실행하려면 프로젝트 루트에서 아래 명령을 사용합니다. Backend, AI Server, Frontend가 각각 별도 PowerShell 창에서 계속 실행됩니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3
.\start-dev.ps1
```

개별 실행이 필요하면 아래 명령을 사용합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3\frontend
$env:VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:8100'
$env:VITE_AI_PROXY_TARGET='http://127.0.0.1:8112'
npm run dev -- --host 0.0.0.0 --port 5176 --strictPort
```

`start-dev.ps1`로 실행한 TP2-3 개발 주소는 `http://localhost:5176`입니다. TP2-2와 동시에 실행해도 충돌하지 않도록 TP2-3은 Backend `8100`, AI Server `8112`, Frontend `5176`을 사용합니다. Windows에서 기존 `8111` 리스너가 중복 잔류한 개발 환경을 피해 AI 포트를 옮겼습니다. 첫 설치 이후에만 `npm install`이 필요합니다.

`start-dev.ps1`에서 `Python virtual environment was not found` 오류가 나오면 프로젝트 루트에서 `.\setup-dev.ps1`를 먼저 실행합니다.

같은 네트워크의 팀원이 접속할 때는 `start-dev.ps1` 실행 후 표시되는 현재 PC의 LAN 주소를 사용합니다. 네트워크 어댑터가 여러 개면 주소가 여러 줄 표시될 수 있으며, 같은 네트워크 대역의 주소를 선택합니다. Windows 방화벽에서 5176 인바운드 허용이 필요할 수 있습니다.

## 발표용 프로젝트 구조 탐색기

관리자 학습 영역의 마지막 `전체 구조` 탭은 별도 `project_tree_explorer/` Streamlit 앱을 표시합니다. 처음 한 번만 설치한 뒤 실행합니다.

```powershell
& .\backend\.venv\Scripts\python.exe -m pip install -r project_tree_explorer/requirements.txt
& .\backend\.venv\Scripts\python.exe -m streamlit run project_tree_explorer/app.py --server.port 8501
```

React 화면에서 `http://localhost:5176/project-tree`를 열면 전체 트리·파일 역할·앱 시작·대시보드·AI 전략·챗봇 실행 흐름을 확인할 수 있습니다. Streamlit 설치 후에는 `start-dev.ps1`이 구조 탐색기 포트 `8501`도 함께 실행합니다. LAN으로 접속할 때도 React와 같은 개발 PC 호스트의 `8501`을 사용합니다. CLI 트리만 출력하려면 `& .\backend\.venv\Scripts\python.exe project_tree_explorer\tree_cli.py`를 사용하고, 의존성·캐시 폴더까지 포함하려면 `--include-generated`를 추가합니다.

## 지도 Backend 실행

새 터미널에서 아래를 실행합니다. 지도에는 루트 `.env`의 `VWORLD_API_KEY`가 있어야 합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

Backend와 프론트엔드가 모두 실행되면 `http://localhost:5176/dashboard`의 지도는 시연 점 대신 클릭 가능한 시도·시군구 면 경계를 표시합니다.

## AI 서버와 Word 기획서 실행

강남구 AI 전략기획서와 Word 다운로드는 별도 AI 서버가 담당합니다. 루트 `.env`에 `OPENAI_API_KEY`가 있어야 합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3
.\backend\.venv\Scripts\python.exe -m uvicorn ai_server.app.main:app --reload --host 127.0.0.1 --port 8112
```

- 화면의 `AI 전략기획서 생성`은 Evidence Agent가 선택 지역 근거를 모으고, Case Scout가 전국 공식 성공사례의 실행 방식·예산·성과를 조사합니다. Transferability Agent가 지역 적합성을 평가한 뒤 Planner가 3~6개월 기획안을 작성하고 Reviewer가 사례 오용과 실행 가능성을 검토합니다. 기준 미달 시 한 번 수정합니다.
- Agent별 코드와 프롬프트·페르소나의 조정 위치는 `ai_server/app/agents/README.md`와 `ai_server/app/agents/prompts.py`에서 확인합니다.
- 우측 `AI 분석 도우미`는 선택 지역 snapshot과 현재 기획안을 함께 읽고 지표 설명, 공식 웹 사례 조사, 기획안 수정안을 제공합니다. 수정안은 사용자가 `기획안 수정안 적용`을 눌러야 화면 보고서에 반영됩니다.
- 같은 구조화 보고서로 `Word 다운로드`와 `PowerPoint 다운로드`를 선택할 수 있습니다. Word는 최대 5쪽의 검토 문서이고, PowerPoint는 사용자가 승인한 최신 디자인을 확장한 편집형 12장 템플릿(`tourism_strategy_12_slide_template.pptx`)을 사용합니다. 3장 대표 사진은 선택 지역의 한국관광공사 관광 Open API 관광지·문화시설·축제·레포츠 이미지를 우선 사용하고, 없으면 중립 이미지를 표시합니다. 4장은 선택한 기획의 작동 방식·대상·필요 자원·산출물을 병렬로 정리하고, 6장은 실제 보고서의 비교·사례 판단을 연결합니다. 7장은 일정·작업·산출물을 우상향 실행 로드맵으로 보여 주며 왼쪽 최종 산출물 레일에서 다음 회차의 유지·보완·확대 판단까지 연결합니다. 9장은 근거 없는 총액 없이 산출 기준과 견적표를, 10~11장은 사업 이후 운영 체계와 관측 데이터·ML·공식 근거·AI 실행 이력을 구분해 표시합니다.
- 보고서 모델은 루트 `.env`의 `OPENAI_REPORT_MODEL`을 우선 사용하고, 비어 있으면 `OPENAI_MODEL`, 둘 다 비어 있으면 `gpt-5.6`을 사용합니다. 키와 모델 설정은 React에 넣지 않습니다.
- Hybrid 모드에서는 `LLMRouter`가 공식 Web Search 단계(Evidence·Case Study)와 최종 검수를 OpenAI로 유지하고, 지역 적합성·초안·수정은 LAN의 Ollama Qwen/Gemma로 보낼 수 있습니다. 개인 노트북 연결과 `.env` 설정은 [LOCAL_LLM_SETUP.md](docs/LOCAL_LLM_SETUP.md)를 확인하세요. `/llm-control`에서 실제 Provider 상태·라우팅·완료 trace를 볼 수 있습니다.

### 개인 GPU 노트북 Ollama 연결

Qwen·Gemma의 페르소나, 실제 근거 조회 도구, 실패 시 정책과 확인 방법은 [로컬 Agent 도구 구성](docs/LOCAL_AGENT_TOOLS.md)에 정리했습니다. ACTIVE와 실제 모델 실행은 다르므로 AI Router의 성공·실패·대체 실행 기록을 확인하세요.

개인 노트북은 Ollama와 모델만 실행하고, 학원 개발 PC는 React·Backend·AI Server를 실행합니다. 개발 PC 루트 `.env`에 `LOCAL_LLM_BASE_URL`, `OLLAMA_QWEN_MODEL`, `OLLAMA_GEMMA_MODEL`을 설정한 뒤 `./start-dev.ps1`만 실행하면 세 서버 창에 같은 설정이 자동 전달됩니다. 연결 상태는 `/llm-control`에서 Qwen·Gemma 카드가 `active`인지 확인합니다.

로컬 모델은 최종안에 실제 원문을 읽은 공식 사례만 인용할 수 있습니다. 목록에서 본 다른 등록 사례를 처음 인용하면 AI Server가 그 원문을 자동 조회해 같은 로컬 모델에 한 번만 재작성을 요청합니다. 이때 OpenAI는 호출하지 않으며, 재작성에서도 새 미조회 사례를 쓰면 안전 검증이 결과를 차단합니다.

## 핵심 기술 흐름

```text
React + Vite → Backend FastAPI(지도) + AI FastAPI(원자료·기획안)
                                      ├─ 공식 ZIP 읽기 전용 분석(현재 연결)
                                      ├─ 지역별 관광 현황 사실표·MySQL·LLM 도구(현재 연결)
                                      ├─ 전국 빅데이터 기간집계·전국 월별 맥락 MySQL 보조 근거(현재 연결)
                                      ├─ 5-Agent + Hybrid Multi-LLM Router(현재 연결)
                                      ├─ ChromaDB 공식 문서 RAG(코드 연결, 색인 보강 중)
                                      └─ 89개 시군구 검증 ML 예측(현재 연결) → MySQL 비교층과 정의 분리
```

## 주의

- [사례 기반 발전 방향·예산·측정 진단](docs/CANDIDATE_FEASIBILITY_20260908.md): 운영 변경 없이 동결 근거로 Qwen 시범 설계→서버 계약 결합→Gemma 본문→Qwen 검토를 비교합니다. 임시 산식·Schema·LLM 승인과 실제 기획 품질을 구분합니다.

- [생성·ML·문서 출력 재검토](docs/GENERATION_REVIEW_20260902.md): 기획 기간과 목표는 `report_projection.py`에서 공통 처리하며 미검수 상태·부분 전망을 숨기지 않습니다.

- 기획안 생성 전 점검: `python -m ai_server.app.scripts.check_generation_readiness --region-code 11680` (LLM 생성·임베딩 호출 없음). 실제 검증 결과와 한계는 [생성 준비 점검](docs/GENERATION_READINESS_20260902.md)을 확인하세요.
- 기획안 미리보기의 검수 상태·후보 비교를 확인하세요. 중요한 오류가 남은 결과는 검토용 초안이며, 챗봇 수정 후에는 이전 검수 승인을 유지하지 않습니다.

- 실제 데이터·성능·사용자 평가 결과가 나오기 전에는 숫자를 공모전 성과로 쓰지 않습니다.
- 데이터랩 사이트의 무단 크롤링은 하지 않습니다.
- 시계열 데이터 랜덤 분할은 하지 않습니다.
- 원본 ZIP과 Open API의 현재 사용 위치는 `docs/DATA_SOURCE_USAGE.md`에서 관리합니다.
- AI 보고서·정책 시나리오·Word 기획서의 역할 분리는 `docs/AI_REPORT_AND_PROPOSAL.md`에서 관리합니다.
- 구현 완료·부분 완료·미구현 항목과 성능 점검 결과는 `docs/PROJECT_AUDIT.md`에서 확인합니다.


### 사례 기반 아이디어와 목표 조정 (2026-09-09)

PPT는 승인된 양식을 유지하며 사례 소개 다음에 선정 근거 페이지를 포함합니다. 월 표시·범례를 분리하고 점에 연결된 수치 레이블을 사용합니다. 비교 지역의 환경 유사성이 확인되지 않은 경우 운영 방식의 참고 근거로 설명합니다.
기획안은 사례 기반 아이디어와 편집 가능 항목을 먼저 보여줍니다. `execution_scenario`가 없으면 최종월 방문·소비 +5%를 계획 가정으로 제안합니다. `target_proposal_basis`에 근거/가정 구분, `reference_estimate`에 항목별 임시 견적을 전달하며 Word/PPT에 동일 반영합니다. 관측·ML·검수 승인 값은 유지합니다. 챗봇에서 “방문 목표 4%, 소비 목표 5%로 바꿔줘”, “견적 총액 1억원으로 변경”처럼 요청할 수 있습니다. 현재 근거 연결 후보 밖의 건물·공원 신축은 지원 범위 밖으로 안내합니다. 상세 정책은 DECISIONS D-124 참조.
# KPI 소비 목표 계산

관리자 OpenAI 탭에는 Agent별 역할·입출력·도구·지시문과 로컬 우선 공급자 분담을 표시합니다. `ai_server/app/agent_learning_guide.py`가 학습 설명을 관리하며 실제 실행 모델은 AI Router와 agent_trace에서 확인합니다.

전체 구조 지도에서도 **ML 결과 → 전략**을 선택해 같은 ML 연결 설명을 기존 단계별 파일 탐색 방식으로 확인할 수 있습니다.

관리자 [머신러닝 결과](http://localhost:5176/ml-test)의 각 Target에는 계산 파일·함수, ML 근거 필드, 사례 조사, Qwen/Gemma 전달, 출력 위치를 설명하는 7단계 안내와 호출 트리가 있습니다. 설명 데이터는 `ai_server/ml/module_usage.py`에서 관리합니다.

PPT 사례 카드는 오른쪽 여백과 자동 줄바꿈을 적용합니다. 출력 버전은 `pptx-case-wrap-v13`입니다.

방문·소비 목표율이 같으면 PPT는 월별 `ML 소비액 ÷ ML 방문 수`를 추가 방문 수에 곱해 소비 목표를 설명합니다. KPI 페이지 하단에 월별 비율과 산식을 표시합니다. 실제 객단가가 아닌 기획용 비율이며, 별도로 지정한 소비 목표율은 유지합니다. [계산 정책](docs/DECISIONS.md)의 D-126을 참고하세요.
# 2026-09-10 기획서 사례·산식 설명

v16부터 미등록 사례도 유형별 유사 사업 웹 이미지로 채웁니다. 실제 사례 이미지와 구분하는 참고 표시, 사진 지역 및 출처를 유지합니다. 확인된 웹 이미지를 캐시하며 생성 시 추가 유료 검색을 하지 않습니다.

사례 이미지 출력은 v15부터 공식 웹에서 받은 사진·홍보물만 사용합니다. 사례 ID별 출처는 `ai_server/app/case_images.py`에 있으며 미등록 사례에는 생성 이미지를 사용하지 않습니다.

PPT v14는 공식 운영 문서를 함수로 연결하고 사례 3열·실행 가이드 통합·견적 예시안 산식을 출력합니다. 선정 알고리즘, 웹/파일/RAG 출처 구분과 아직 없는 환경·전후 성과 자료는 [춘천 감사 기록](docs/CHUNCHEON_PROPOSAL_AUDIT_20260910.md)을 참고하세요.


### 기획 입력 간소화 (`guided_v1`, 2026-09-10)

기획 생성 페이지는 사업 방향, 참고 예산 총액, 시작 월(3개월 시범), 활용 자원 300자, 제외 운영 방식, 메모 500자를 받습니다. KPI 입력·예산 범위/확정 상한·종료일·첨부자료는 기본 생성 화면에서 제거했습니다. 예산은 견적 배분 예시이며 ML 전망이나 실행 가능성을 보장하지 않습니다.

`planning_brief.input_profile="guided_v1"`에서 `business_direction`은 `auto|spend_conversion|stay_conversion|night_time_experience|return_visit`, `excluded_operations`는 `night_time_experience|spend_conversion` 배열입니다. 예산은 `unknown` 또는 `indicative`와 `budget_max_krw` 하나를 사용합니다. 시작 월 미입력은 현재 월부터 3개월로 정규화합니다. 숨겨진 구형 입력 및 충돌은 Pydantic 검증에서 거절합니다. 공식 근거/선정 조건 불일치는 `PLANNING_CONDITIONS_UNSUPPORTED`, 전망 기간 부족은 `PLANNING_PERIOD_UNSUPPORTED`로 안내합니다. 기존 API의 profile 미입력은 `legacy`로 처리하며 저장 보고서를 변경하지 않습니다. 상세 결정: D-136.


지역 준비 표시(D-137): `GET /ai/v1/regions/readiness-audit`는 `local_models_ready`, `local_model_message`, 지역별 `generation_ready`를 반환합니다. 초록색은 최근 24시간 이내 `data_ready`와 현재 설치된 Qwen/Gemma 연결을 모두 확인한 경우입니다. 기존 `verified`(저장 기획안 승인)와 구분하며 새로운 생성 성공을 보장하지 않습니다. 미점검/만료는 초록색으로 표시하지 않습니다. 자료 감사 갱신: `backend/.venv/Scripts/python.exe -m ai_server.app.scripts.audit_all_regions` (LLM 생성·재학습·SQL 쓰기 없음). 모델 목록 연결 확인은 15초 제한, 생성 전 일시 실패에만 1회 재확인합니다.


### D-138 생성 진행 단계 표시 (2026-09-10)

생성 대기 화면 제목은 ‘기획서 초안을 생성중입니다’. 작업 조회 응답에 `progress_step`을 추가한다: 0 데이터 분석(연결 확인 포함), 1 공식사례 확인(지역 근거 병행), 2 기획안 생성(후보 비교·초안), 3 품질검토(보완·재검수 포함), 4 검토 절차 종료 후 본문·문서 준비. null은 단계 미확인이다. 실제 실행 지점에서 요청별 ContextVar 콜백으로 메모리 작업 상태를 갱신하며 기존 3초 상태 조회로 표시한다. 경과 시간으로 단계를 추측하지 않는다. 진행 단계는 파란 음영 애니메이션, 완료 단계는 파란 채움, 대기 단계는 기존 외곽선으로 구분한다. 재접속 시 서버 상태를 다시 읽고 연결 오류에는 확인 지연을 표시한다. 단계 완료는 품질 승인과 다르며 모델/유료 호출 수는 변경하지 않는다.
