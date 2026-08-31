# AI 전략 Agent 폴더

이 폴더는 관광 전략기획서 생성 흐름을 역할별 Agent로 분리한 곳입니다.

```text
evidence_agent.py       → 선택 지역 데이터·Open API·지역 공식 문서 수집
case_study_agent.py     → 전국 공식 성공사례의 실행 방식·성과·예산·조건 수집
transferability_agent.py → 사례와 선택 지역의 적합성 평가, 시범사업 구조 작성
planner_agent.py        → 근거와 적합성 평가를 실행 기획안 JSON으로 작성
reviewer_agent.py       → 근거성·실행성·간결성·사례 오용 여부 검토
report_orchestrator.py  → 다섯 Agent 실행, 캐시, 1회 보완, 실행 이력 기록
chat_assistant_agent.py → 지역 snapshot·현재 기획안을 읽고 설명·공식 조사·수정안 제안
prompts.py              → 다섯 Agent의 프롬프트·페르소나를 한곳에서 관리
```

## 조정 위치

| 바꾸려는 내용 | 수정할 파일 | 주의 |
|---|---|---|
| 조사 범위·공식 웹 검색 관점 | `prompts.py`의 `EVIDENCE_RESEARCH_INSTRUCTIONS` | 허용 도메인은 `.env`에서 관리 |
| 성공사례 종류·성과 조사 기준 | `prompts.py`의 `CASE_STUDY_RESEARCH_INSTRUCTIONS` | 공식 평가·결산·예산 자료 우선 |
| 사례의 지역 적합성·시범사업 구성 | `prompts.py`의 `TRANSFERABILITY_INSTRUCTIONS` | 인과효과·지역 조건을 임의로 만들지 않음 |
| 기획안의 말투·실행 단계·예산 표현 | `prompts.py`의 `PLANNER_INSTRUCTIONS` | 출처 밖 수치 생성 금지 규칙 유지 |
| 통과 기준·검수 항목 | `prompts.py`의 `REVIEW_INSTRUCTIONS`, `reviewer_agent.py` | 현재 82점 + critical 0건 |
| 보고서 JSON 필드 | `../main.py`의 `REPORT_SCHEMA` | React·Word 출력도 함께 확인 |
| Agent 실행 순서·재작성 횟수 | `report_orchestrator.py` | 현재 한 번만 자동 보완 |
| 챗봇 말투·웹 조사·수정안 형식 | `chat_assistant_agent.py` | 자동 저장 금지, 허용 공식 도메인만 사용 |

## 공식 성공사례 RAG

`data/rag/official_case_studies.jsonl`에는 팀이 URL과 내용을 직접 검수한 사례 카드를 저장합니다.
월간 수치표가 아니라 사업의 대상·운영 방식·공개 예산·관측 결과·적용 조건을 저장합니다.

```powershell
python -m ai_server.index_rag_documents --input data/rag/official_case_studies.jsonl
```

라이브 웹 조사는 최신 사례를 찾고, RAG는 이미 검수한 사례를 빠르게 재사용합니다. 두 경로 모두
공식 URL이 없으면 Planner 입력에서 제외합니다.

월별 숫자는 RAG나 LLM이 만들지 않습니다. `data/raw` 원본을 읽어 계산한 snapshot만 사실 수치로 사용합니다.
