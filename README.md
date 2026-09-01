# STAY-UP AI

관광 빅데이터를 활용하여 인구감소지역의 관광수요를 예측하고 체류·소비 활성화 전략을 생성하는 공모전 프로젝트입니다.

## 시작하기 전

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

### 전략기획 입력 페이지 (2026-08-28)

- 메뉴: 지역선택 → **전략기획** (`/planning`) → AI 전략기획 (`/strategy`) → 저장된 기획서.
- 공무원은 예산·추진 시기·확보/협의 중인 자원·필수 제약을 제공합니다. 분야·목표·사업 방식은 정답으로 요구하지 않으며 AI가 원자료와 공식 사례로 제안합니다. 현장 정보·선호·참고자료는 선택 입력입니다.
- 미정은 0원·확정으로 바꾸지 않습니다. 필수 제약과 선호를 구분하고, 사용자 문서를 공식 근거로 취급하지 않습니다.
- 초안은 지역별 브라우저 localStorage에 임시 저장합니다. 단, 첨부 문서의 본문은 브라우저·결과·저장된 보고서에 남기지 않고 생성 작업 중에만 사용합니다. 생성 당시 조건은 작업·결과·저장된 보고서에 복사되고 Word/PPT에 예산·일정 요약을 표시합니다. 작업 상태와 완료 결과는 MySQL에 저장합니다. 첨부가 없는 중단 작업은 AI Server 재시작 뒤 재개하며, 첨부가 있던 작업은 본문 비저장 원칙 때문에 재요청을 안내합니다.
- 참고자료: 한글(HWPX)·Word(DOCX)·텍스트(TXT/MD)·PDF·Excel(XLSX)을 파일당 2MB·6,000자, 최대 3개까지 받습니다. 텍스트만 메모리에서 추출하고 원본·공용 RAG·서버 DB에는 저장하지 않습니다. 생성 요청 시 모델 입력에 포함되므로 개인정보·민감정보는 제외합니다. 기존 HWP는 HWPX 또는 PDF로 저장해 첨부합니다.
- PDF·Excel 참고문서 추출에는 `pypdf`, `openpyxl`을 사용하며 `requirements.txt`에 기록합니다.
- 개발 위치: `frontend/src/features/planning/`, `frontend/src/pages/TourismPlanningPage.jsx`, `ai_server/app/planning_brief.py`. 조건별 지시문은 `ai_server/app/agents/prompts.py`의 `PLANNING_CONTEXT_RULES`에서 관리합니다.
- 검증 명령: `python -m unittest ai_server.test_planning_brief ai_server.test_report_orchestrator`, frontend에서 `node --test src/features/planning/planningBrief.test.js`, `npm run lint`, `npm run build`.

### 강남구 3개월 수요 예측 (2026-08-28)

- 개발 위치: `ai_server/ml/`. 원본 ZIP을 읽는 `gangnam_data.py`, 학습·평가·예측을 담당하는 `gangnam_forecast.py`, 수동 재학습 CLI `train_gangnam.py`로 나뉜다.
- 화면: 강남구 지역선택 대시보드에서 최근 3개월 관측값과 다음 3개월 ML 예측을 함께 보여 준다. 상단 카드는 다음 달 예상 순 방문자 수·관광소비액으로 변경된다.
- 모델: 방문자 수는 RandomForestRegressor, 소비액은 LinearRegression, 평균 숙박일수는 LinearRegression 또는 전년 동월 기준선이다. 최근 4개월 시간순 테스트에서 방문자·소비액 모델은 전년 동월 seasonal-naive 기준선보다 MAE가 낮을 때만 저장하며, 상단 카드는 현재 달의 다음 달 예측을 표시한다.
- 확장 구조: `ai_server/ml/region_registry.py`에 지원 시군구를 등록하고, `region_service.py`를 통해 API와 일괄 학습 CLI가 같은 지역 모델을 호출한다. 전처리·모델 파일은 각각 `data/processed/ml/<지역코드>/`, `artifacts/ml/<지역코드>/`로 분리한다.
- 재학습: `./backend/.venv/Scripts/python.exe -m ai_server.ml.train_gangnam`. 저장 파일은 `artifacts/ml/`, 재현용 월별 표는 `data/processed/`에 생성한다.
- 업종별 예상 소비 패턴은 별도 업종 모델이 아니라 최신 관측 업종 비중을 전체 소비액 예측에 적용한 가정이다.

현재는 **React + Vite 대시보드, 지도 FastAPI, 지역 원본 기반 Multi-Agent 전략 보고서 AI 서버를 만든 단계**입니다. `/` 소개 화면과 `/dashboard` 업무 화면은 페이지 단위로 지연 로딩되며, 대시보드에는 도·시·군·구 검색과 `전국 시도 선택 → 선택 시도의 시군구 선택` 2단계 지도가 있습니다.

- 실제 월간 카드·차트·소비 진단과 OpenAI 전략 보고서가 연결된 지역은 서울특별시 강남구와 인천광역시 계양구·서구·옹진군입니다. 이 네 지역의 화면 수치는 `data/raw/{시도}/{시군구}` 공식 ZIP에서 계산하며 OpenAI가 숫자를 만들지 않습니다.
- 미지원 지역은 예시 숫자를 대신 보여 주지 않고 `원자료 미연결` 빈 상태로 표시합니다. 원본 폴더에 방문자·외지인 관광소비·숙박/체류·내비게이션·SNS 표를 추가하고 지역 코드·단위를 검증한 뒤 같은 경로로 확장합니다.
- 원본 ZIP 표는 수정하지 않으며, 파일 경로·크기·수정시각 지문이 같을 때 파싱 결과를 메모리에서 재사용합니다. 원본이 바뀌면 캐시는 자동 무효화됩니다.
- 강남구 AI 보고서는 원본 ZIP의 관측값과 OpenAI의 실행 제안을 구분합니다.
- 지역 선택의 `지역 정보 상세보기`는 OpenAI를 호출하지 않고, 서버가 한국관광공사 국문 관광정보 Open API에서 읽은 관광자원 정보를 월간 원자료 요약과 분리해 보여 줍니다.
- AI 전략기획 생성은 서버 백그라운드 작업으로 실행합니다. 화면을 다른 업무 페이지나 탭으로 바꿔도 작업 ID를 통해 상태를 이어서 확인하며, MySQL의 작업 상태와 완료된 기획안·Word/PPT를 다시 조회합니다.
- 기존 `test-gangnam-dashboard/`는 별도의 Streamlit 프로토타입으로 유지합니다.
- 사이드바의 `관광 진단`·`AI 전략기획`·`기획서 제작`은 각각 `/diagnosis`·`/strategy`·`/proposal` 독립 업무 페이지이며, 실제 지역 선택·분석·생성 기능은 `/dashboard`의 검증된 원자료 흐름으로 연결됩니다. `최근 뜨고 있는 관광지`는 `/trending` 독립 페이지입니다.

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
$env:VITE_AI_PROXY_TARGET='http://127.0.0.1:8111'
npm run dev -- --host 0.0.0.0 --port 5176 --strictPort
```

`start-dev.ps1`로 실행한 TP2-3 개발 주소는 `http://localhost:5176`입니다. TP2-2와 동시에 실행해도 충돌하지 않도록 TP2-3은 Backend `8100`, AI Server `8111`, Frontend `5176`를 사용합니다. Windows에서 `8101`과 `5175`가 예약·점유된 환경을 피한 포트입니다. 첫 설치 이후에만 `npm install`이 필요합니다.

`start-dev.ps1`에서 `Python virtual environment was not found` 오류가 나오면 프로젝트 루트에서 `.\setup-dev.ps1`를 먼저 실행합니다.

같은 이더넷 네트워크의 팀원이 접속할 때는 `start-dev.ps1` 실행 후 표시되는 PC의 LAN IPv4 주소를 사용합니다. 현재 예시는 `http://192.168.0.22:5176`이며, PC마다 `ipconfig`로 확인합니다. Windows 방화벽에서 5176 인바운드 허용이 필요할 수 있습니다.

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
.\backend\.venv\Scripts\python.exe -m uvicorn ai_server.app.main:app --reload --host 127.0.0.1 --port 8111
```

- 화면의 `AI 전략기획서 생성`은 Evidence Agent가 선택 지역 근거를 모으고, Case Scout가 전국 공식 성공사례의 실행 방식·예산·성과를 조사합니다. Transferability Agent가 지역 적합성을 평가한 뒤 Planner가 3~6개월 기획안을 작성하고 Reviewer가 사례 오용과 실행 가능성을 검토합니다. 기준 미달 시 한 번 수정합니다.
- Agent별 코드와 프롬프트·페르소나의 조정 위치는 `ai_server/app/agents/README.md`와 `ai_server/app/agents/prompts.py`에서 확인합니다.
- 우측 `AI 분석 도우미`는 선택 지역 snapshot과 현재 기획안을 함께 읽고 지표 설명, 공식 웹 사례 조사, 기획안 수정안을 제공합니다. 수정안은 사용자가 `기획안 수정안 적용`을 눌러야 화면 보고서에 반영됩니다.
- 같은 구조화 보고서로 `Word 다운로드`와 `PowerPoint 다운로드`를 선택할 수 있습니다. Word는 최대 5쪽의 검토 문서, PowerPoint는 현황 그래프·문제·솔루션·5단계 로드맵·공식 출처를 담은 최대 5장의 발표 자료입니다.
- 보고서 모델은 루트 `.env`의 `OPENAI_REPORT_MODEL`을 우선 사용하고, 비어 있으면 `OPENAI_MODEL`, 둘 다 비어 있으면 `gpt-5.6`을 사용합니다. 키와 모델 설정은 React에 넣지 않습니다.

## 핵심 기술 흐름

```text
React + Vite → Backend FastAPI(지도) + AI FastAPI(원자료·기획안)
                                      ├─ 공식 ZIP 읽기 전용 분석(현재 연결)
                                      ├─ 5-Agent + OpenAI 전략 생성(현재 연결)
                                      ├─ ChromaDB 공식 문서 RAG(코드 연결, 색인 보강 중)
                                      └─ 강남구 검증 ML 예측(현재 연결) → MySQL 이전은 다음 단계
```

## 주의

- 실제 데이터·성능·사용자 평가 결과가 나오기 전에는 숫자를 공모전 성과로 쓰지 않습니다.
- 데이터랩 사이트의 무단 크롤링은 하지 않습니다.
- 시계열 데이터 랜덤 분할은 하지 않습니다.
- 원본 ZIP과 Open API의 현재 사용 위치는 `docs/DATA_SOURCE_USAGE.md`에서 관리합니다.
- AI 보고서·정책 시나리오·Word 기획서의 역할 분리는 `docs/AI_REPORT_AND_PROPOSAL.md`에서 관리합니다.
- 구현 완료·부분 완료·미구현 항목과 성능 점검 결과는 `docs/PROJECT_AUDIT.md`에서 확인합니다.
