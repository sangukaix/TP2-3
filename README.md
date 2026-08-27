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

## 현재 상태

현재는 **React + Vite 대시보드, 지도 FastAPI, 지역 원본 기반 Multi-Agent 전략 보고서 AI 서버를 만든 단계**입니다. `/` 소개 화면과 `/dashboard` 업무 화면은 페이지 단위로 지연 로딩되며, 대시보드에는 도·시·군·구 검색과 `전국 시도 선택 → 선택 시도의 시군구 선택` 2단계 지도가 있습니다.

- 실제 월간 카드·차트·소비 진단과 OpenAI 전략 보고서가 연결된 지역은 서울특별시 강남구와 인천광역시 계양구·서구·옹진군입니다. 이 네 지역의 화면 수치는 `data/raw/{시도}/{시군구}` 공식 ZIP에서 계산하며 OpenAI가 숫자를 만들지 않습니다.
- 미지원 지역은 예시 숫자를 대신 보여 주지 않고 `원자료 미연결` 빈 상태로 표시합니다. 원본 폴더에 방문자·외지인 관광소비·숙박/체류·내비게이션·SNS 표를 추가하고 지역 코드·단위를 검증한 뒤 같은 경로로 확장합니다.
- 원본 ZIP 표는 수정하지 않으며, 파일 경로·크기·수정시각 지문이 같을 때 파싱 결과를 메모리에서 재사용합니다. 원본이 바뀌면 캐시는 자동 무효화됩니다.
- 강남구 AI 보고서는 원본 ZIP의 관측값과 OpenAI의 실행 제안을 구분합니다.
- 지역 선택의 `지역 정보 상세보기`는 OpenAI를 호출하지 않고, 서버가 한국관광공사 국문 관광정보 Open API에서 읽은 관광자원 정보를 월간 원자료 요약과 분리해 보여 줍니다.
- AI 전략기획 생성은 서버 백그라운드 작업으로 실행합니다. 화면을 다른 업무 페이지나 탭으로 바꿔도 작업 ID를 통해 상태를 이어서 확인하며, 완료되면 저장된 기획서 목록에 기록합니다. 개발 서버를 재시작하면 진행 중인 작업은 유지되지 않습니다.
- 기존 `test-gangnam-dashboard/`는 별도의 Streamlit 프로토타입으로 유지합니다.
- 사이드바의 `관광 진단`·`AI 전략기획`·`기획서 제작`은 각각 `/diagnosis`·`/strategy`·`/proposal` 독립 업무 페이지이며, 실제 지역 선택·분석·생성 기능은 `/dashboard`의 검증된 원자료 흐름으로 연결됩니다. `최근 뜨고 있는 관광지`는 `/trending` 독립 페이지입니다.

## 팀원 최초 설치

```powershell
cd C:\Users\Admin\mbca\TP2-3
python -m pip install -r requirements.txt

cd frontend
npm install
```

- Python Backend와 AI Server의 현재 공통 의존성은 루트 `requirements.txt`로 설치한다.
- React/Vite·지도·그래프 의존성은 `frontend/package.json`과 lock 파일을 기준으로 `npm install` 한다.
- 새 라이브러리를 실제 코드에 추가하면 같은 변경에서 `requirements.txt` 또는 `frontend/package.json`을 반드시 갱신한다.

## 프론트엔드 실행

세 서버를 한 번에 실행하려면 프로젝트 루트에서 아래 명령을 사용합니다. Backend, AI Server, Frontend가 각각 별도 PowerShell 창에서 계속 실행됩니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3
.\start-dev.ps1
```

개별 실행이 필요하면 아래 명령을 사용합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3\frontend
$env:VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:8100'
$env:VITE_AI_PROXY_TARGET='http://127.0.0.1:8101'
npm run dev -- --host 0.0.0.0 --port 5175 --strictPort
```

`start-dev.ps1`로 실행한 TP2-3 개발 주소는 `http://localhost:5175`입니다. TP2-2와 동시에 실행해도 충돌하지 않도록 TP2-3은 Backend `8100`, AI Server `8101`, Frontend `5175`를 사용합니다. 첫 설치 이후에만 `npm install`이 필요합니다.

같은 이더넷 네트워크의 팀원이 접속할 때는 `start-dev.ps1` 실행 후 표시되는 PC의 LAN IPv4 주소를 사용합니다. 현재 예시는 `http://192.168.0.22:5175`이며, PC마다 `ipconfig`로 확인합니다. Windows 방화벽에서 5175 인바운드 허용이 필요할 수 있습니다.

## 지도 Backend 실행

새 터미널에서 아래를 실행합니다. 지도에는 루트 `.env`의 `VWORLD_API_KEY`가 있어야 합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

Backend와 프론트엔드가 모두 실행되면 `http://localhost:5175/dashboard`의 지도는 시연 점 대신 클릭 가능한 시도·시군구 면 경계를 표시합니다.

## AI 서버와 Word 기획서 실행

강남구 AI 전략기획서와 Word 다운로드는 별도 AI 서버가 담당합니다. 루트 `.env`에 `OPENAI_API_KEY`가 있어야 합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3
.\backend\.venv\Scripts\python.exe -m uvicorn ai_server.app.main:app --reload --host 127.0.0.1 --port 8101
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
                                      └─ MySQL + 검증된 ML 예측(다음 단계)
```

## 주의

- 실제 데이터·성능·사용자 평가 결과가 나오기 전에는 숫자를 공모전 성과로 쓰지 않습니다.
- 데이터랩 사이트의 무단 크롤링은 하지 않습니다.
- 시계열 데이터 랜덤 분할은 하지 않습니다.
- 원본 ZIP과 Open API의 현재 사용 위치는 `docs/DATA_SOURCE_USAGE.md`에서 관리합니다.
- AI 보고서·정책 시나리오·Word 기획서의 역할 분리는 `docs/AI_REPORT_AND_PROPOSAL.md`에서 관리합니다.
- 구현 완료·부분 완료·미구현 항목과 성능 점검 결과는 `docs/PROJECT_AUDIT.md`에서 확인합니다.
