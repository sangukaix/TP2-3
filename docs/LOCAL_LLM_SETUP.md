# 로컬 우선 Multi-LLM 연결

## 역할

- OpenAI: 기본 `student_budget`에서는 로컬 검수 통과 후 독립 최종 검수 1회만 사용한다. OpenAI Web Search는 자동 실행하지 않는다. 선택한 무료 검색 API 키가 있으면 Qwen이 만든 제한 질문으로 공식 도메인 검색 요약 후보를 보강할 수 있으며, 최신 공식 지역 근거·사례의 상세 조사는 사용자가 `local_first`로 전환한 경우에만 OpenAI Web Search로 자동 실행한다.
- Qwen (Ollama): 타 지역 사례의 지역 적합성 판단, 사전/재검수, 기획 페이지의 짧은 설명형 챗봇
- Gemma (Ollama): 기획안 초안·보완·수정형 챗봇

로컬 모델은 원자료·ML·RAG를 대신하지 않습니다. 수치는 MySQL/ML, 문서 근거는 검수 RAG가 담당합니다. 무료 공식 검색은 Qwen이 질문만 만들고 서버가 Tavily API(선택적으로 Brave API)에 허용된 공식 도메인만 전달하는 읽기 전용 도구입니다. 모델에 브라우저·파일·SQL·쉘 권한을 주지 않으며, 검색 요약은 원문 검수 전 RAG/확정 인용으로 사용하지 않습니다.

## 개인 노트북(Ollama PC)

1. Ollama를 실행하고 `ollama list`에서 사용할 Qwen·Gemma의 **실제 tag**를 확인합니다.
2. `OLLAMA_HOST=0.0.0.0:11434`를 설정한 뒤 Ollama를 다시 실행합니다.
3. Windows 방화벽에서 TCP 11434 인바운드를 개발 PC의 사설망에만 허용합니다.
4. 개발 PC에서 `Test-NetConnection <개인노트북-IP> -Port 11434`가 성공하는지 확인합니다.

두 PC는 **같은 Wi-Fi/공유기 대역**에 연결하는 것을 기본 운영 방식으로 합니다. 예를 들어 개인 노트북이 `192.168.50.92`이면 개발 PC도 `192.168.50.x` 주소를 받아야 합니다. 개발 PC가 `192.168.0.x` 유선망만 사용하고 두 대역 사이에 라우팅이 없으면, Ollama는 실행 중이어도 연결되지 않습니다. `start-dev.ps1`는 이런 경우 현재 개발 PC의 IPv4 주소를 함께 경고로 표시합니다.

## 개발 PC(TP2-3)

루트 `.env`에 다음 환경변수만 팀 환경에 맞게 입력합니다. IP와 모델명은 코드에 쓰지 않습니다.

```env
# student_budget: OpenAI 최종 독립 검수 1회만 사용(기본)
# local_first: 최신 공식 웹 조사·사례 보강까지 필요할 때 선택
LLM_MODE=student_budget
LOCAL_LLM_BASE_URL=http://개인노트북-IP:11434
OLLAMA_QWEN_MODEL=<ollama list의 Qwen tag>
OLLAMA_GEMMA_MODEL=<ollama list의 Gemma tag>
# Gemma 26B의 첫 로드·구조화 초안 생성까지 기다리는 기본 제한(초)
LOCAL_LLM_TIMEOUT_SECONDS=420
LLM_ADMIN_TOKEN=팀내부에서만공유하는긴토큰
```

`start-dev.ps1`는 루트 `.env`를 Backend·AI Server·Frontend 창에 자동 전달합니다. 따라서 개인 노트북에서 Ollama를 실행해 둔 뒤, 개발 PC에서는 프로젝트 루트에서 `./start-dev.ps1`만 실행하면 됩니다.

AI Server를 재시작한 뒤 `GET /ai/v1/llm/status` 또는 학습 영역의 **AI Router**에서 OpenAI·Qwen·Gemma 상태를 확인합니다. `Ollama 주소가 설정되지 않았습니다`가 표시되면 `.env`의 URL·모델 tag를 확인한 뒤 `start-dev.ps1`로 세 서버를 다시 시작합니다.

## 실패 처리와 보안

- Qwen/Gemma JSON 파싱·스키마 오류에만 1회 교정 요청을 합니다. 각 Agent 요청은 15분 동안 모델을 개인 GPU에 유지하고, 도구 선택에는 짧은 출력만 사용하며 최종 JSON에서는 내부 생각 출력을 끕니다. `local_first`와 `local_only`는 유료 폴백을 금지합니다. 기존 `hybrid`만 로컬 실패를 OpenAI로 대체할 수 있습니다.
- `student_budget`은 OpenAI Web Search를 자동 실행하지 않습니다. `TAVILY_API_KEY` 또는 선택적인 `BRAVE_SEARCH_API_KEY`를 설정하면 Qwen 질문으로 보고서당 최대 2개의 무료 공식 도메인 검색을 시도하고, 키가 없거나 할당량이 끝나면 저장 근거만 사용하며 `research_gaps`에 남깁니다. `local_first`에서만 OpenAI Web Search가 실행되며 OpenAI가 실패하면 `공식 웹 조사 실패`로 남습니다.
- 라우팅 저장은 `LLM_ADMIN_TOKEN` 헤더가 맞을 때만 가능하며, API 키·DB 비밀번호·관리자 토큰은 React에 전달하지 않습니다.
- 실제 실행 Provider·모델·시간·토큰은 `/ai/v1/llm/trace`와 보고서의 `agent_trace`에 남습니다. 현재 비용은 가격표 또는 조직 비용 API를 검증해 연결하기 전까지 추정하지 않습니다.

## 무료 공식 검색 API 설정

루트 `.env`에 필요한 공급자 키만 넣습니다. 키를 하나만 넣어도 되며, 다음 공급자는 앞선 공급자가 공식 결과를 충분히 찾지 못했을 때만 호출됩니다.

```dotenv
ENABLE_LOCAL_OFFICIAL_WEB_SEARCH=true
LOCAL_WEB_SEARCH_PROVIDERS=tavily
LOCAL_WEB_SEARCH_MAX_QUERIES_PER_REPORT=2
TAVILY_API_KEY=발급받은_키
BRAVE_SEARCH_API_KEY=
```

- Tavily는 기본 공급자다. 공식 도메인 필터를 API 요청으로 전달한다.
- Brave는 보조 공급자다. 카드·할당량 조건은 계정 정책을 확인한 뒤 키가 있을 때만 사용한다.
- Naver 검색 API는 약관상 결과를 독립적으로 노출해야 하므로, LLM 내부 입력이 아니라 결과를 그대로 표시하는 별도 UI 기능으로만 추후 검토한다.
- 검색 결과의 원문을 자동 다운로드하거나 Chroma/RAG에 넣지 않는다. 팀원이 공식 원문을 확인한 후에만 기존 문서 등록 절차로 승격한다.

## 로컬 모델의 역할·도구

`local_prompts.py`의 Qwen 적용성 분석가/검수자와 Gemma 실행기획자가 제한된 도구 루프를 사용합니다. 보통 2회 도구 선택(회당 3개), 인자 오류에만 교정용 1회를 추가합니다. 긴 초안은 교정을 포함해 최대 8회입니다. 최종 JSON 교정은 최대 1회이며, 필수 근거를 읽지 않은 결과는 채택하지 않습니다. [도구별 입력/출력](LOCAL_AGENT_TOOLS.md), [비용 정책·검증 계획](LOCAL_FIRST_QUALITY_PLAN.md)을 참고하세요.

관리자 설정 `storage/llm_runtime_config.json`이 있으면 `.env` 기본 모드보다 우선합니다. 실제 적용 모드는 `/ai/v1/llm/config`로 확인합니다. `.env`만 수정한 경우 서버 재시작이 필요합니다.
