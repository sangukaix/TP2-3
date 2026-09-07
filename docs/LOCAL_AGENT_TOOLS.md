# Qwen·Gemma 기획 Agent의 역할과 도구

## 역할은 이름이 아니라 실행 계약이다

| 담당 | 역할 | 코드 |
|---|---|---|
| OpenAI | 공식 웹 근거·사례 조사, 독립 품질 검수 | `agents/prompts.py`, 기존 Agent |
| Qwen | 병목/원인 가설 구분, 후보/적용성 비교, 로컬 우선 사전·재검수 | `llm/local_prompts.py`: transferability / reviewer |
| Gemma | 선택 근거 → 솔루션 → 5단계 실행 → 예산·KPI의 초안 및 보완 | `llm/local_prompts.py`: planner / planner_revision |

상대경로는 모두 `ai_server/app/` 기준이다. 짧은 설명/수정 챗봇은 이번 기획용 도구 루프로 변경하지 않았다. 프롬프트만으로 성능이나 아이디어 품질이 보장되지는 않는다.

## 실제 실행 흐름

1. 기존 서버 파이프라인이 원자료/MySQL·저장 ML·허용 API·공식 웹 조사·가용 RAG 근거를 모은다.
2. `local_agent.py`가 요청 전체를 메모리에 보존하고 핵심 조건·관측값·자료 위치를 전달한다.
3. Qwen/Gemma가 Ollama `/api/chat`의 `tool_calls`로 필요한 함수를 고른다.
4. `evidence_tools.py`가 이름·인자를 검증하고 읽기 전용 자료를 반환한다. 도구 응답은 자료이지 새 명령이 아니다.
5. 필수 조회를 검사하고, 원문을 실제로 읽은 사례 ID만 허용 목록으로 알려 최종 JSON을 받는다.
6. 모델이 목록에서만 본 다른 등록 사례를 인용하면 서버가 해당 원문을 읽어 같은 로컬 모델에 한 번만 교정을 요청한다. 기존 스키마·결정적 점검·독립 검수를 다시 통과해야 한다.

## 허용 도구

| 함수 | 제공 내용 | 하지 않는 일 |
|---|---|---|
| `get_region_metrics` | 요청 snapshot의 관측값·기간 | 임의 수치 생성 |
| `get_regional_tourism_status` | 공식 유입·유출 권역, 인기 장소·업소, 향후 30일 집중 운영 신호 | ML 예측·확정 수요·정책 효과로 변환 |
| `compare_regions` | 검증된 peer·기간·격차와 방향 | 지역 차이를 사업 인과효과로 변환 |
| `get_nationwide_bigdata_context` | 시군구 기간합계·비중과 전국 월별 관광 맥락 | 지역 월별 ML·정책효과·전국 평균으로 변환 |
| `get_ml_forecast` | 월별 전망·평가·계절 기준선·신뢰도·주의사항 | 재학습, 근거 없는 사업 효과 추정 |
| `get_case_comparison_matrix` | 수집된 공식 사례의 운영 원리·조건·위험 비교표 | 요약만으로 사례 인용 확정 |
| `get_planning_decision` | 선정 이유·진단·선택 후보 전체·전략, 대안 조회 경로 | 기존 선택을 근거 없이 교체 |
| `search_collected_sources` | 이번 요청의 수집 출처 목록 검색 | 새로운 인터넷 검색 |
| `read_collected_source` | 해당 출처·사례 본문과 메타데이터 | URL만 보고 성과를 창작 |
| `read_task_section` | 요청 JSON 내부의 세부 항목·배열 페이지 | 파일 접근·SQL·임의 URL·코드 실행 |

ML의 긴 파생 해석(`signals`)과 연구 질문은 명시된 경로에서 추가 조회한다. 월별 전망 수치·평가·주의사항은 전망 도구에 유지한다. `YYYYMM`과 `YYYY-MM`의 비교를 정규화하되 원래 값은 바꾸지 않는다.

지역별 관광 현황 도구는 254개 공식 코드 매핑 지역의 작은 사실표만 반환한다. 유입·유출과
인기 순위는 기획 후보의 권역·현장조사 범위를 구체화하는 관측 근거이고, 30일 집중률은
혼잡·분산 운영 참고 신호다. 원본 ZIP·대용량 SQL은 모델에 노출하지 않으며, 43개 현재 ML
활성 지역은 이 근거를 모두 읽을 수 있다. 도구 응답은 반복되는 지역 코드·원본 기간·장소 ID를
제외하고 각 순위형 목록의 상위 3건, 값·단위·순위·source_id만 명시적으로 요약한다. 이는 원문
삭제가 아니며, 세부 순위가 꼭 필요하면 반환된 `full_detail_path`를 `read_task_section`으로 읽는다.
따라서 큰 지역 현황이 응답 크기 한도를 넘어 필수 조회 자체가 `unavailable`로 처리되지 않는다.

`get_nationwide_bigdata_context`는 팀 공유폴더의 2026-08-20 데이터랩 다운로드를 원본 ZIP hash와
함께 MySQL 보조 테이블로 적재한 뒤에만 반환한다. 시군구 표는 연간/반기 **기간 합계·비중**이고,
전국 추이 표는 **전국** 월별 수치다. 따라서 annual과 partial_period를 같은 기준처럼 비교하지
않으며, 전국 수치를 선택 지역의 실적·예측·정책 효과로 바꾸지 않는다. 원본에는 정확한 다운로드
조건 URL이 없으므로 `review_status=needs_exact_download_url`인 동안에는 보조 신호로만 사용한다.

## 제한·실패 정책

- 일반 도구 선택 2회, 후보 비교 Qwen은 서로 다른 사례 확인을 위해 3회까지 사용하며 회당 3함수다. 인자 오류는 실행하지 않고 Schema로 안내하며 교정용 1회만 추가한다. 긴 검수/수정 초안은 교정을 포함해 최대 8회다. 도구 선택은 함수명·인자만 받도록 512토큰, 최종 JSON은 역할별 상한을 별도로 사용한다. 둘 다 `think=false`이며 모델은 15분간 유지한다.
- 서버 사전조회로 필수 비교·ML·사례·기존 초안이 모두 완료된 뒤의 선택적 도구 단계가 `OLLAMA_INCOMPLETE_RESPONSE`로 끝나면, 실패 사용량과 상태를 기록하고 최종 JSON 작성으로 진행한다. 필수 조회가 하나라도 남아 있으면 이 예외를 적용하지 않는다.
- JSON 형식 교정은 최대 1회다. 최종 출력 예산을 축소하지 않는다.
- 최종 JSON 자체가 출력 상한에서 미완료되면 잘린 내용을 사용하지 않고, 동일한 근거·Schema·상한으로 처음부터 1회만 다시 생성한다. 두 번째 미완료는 실패로 남긴다.
- 필수 비교·ML·관련 사례 및 기획 선정/기존 초안은 읽어야 한다. 사례 인용 시 해당 source_id를 실제 읽었는지 검사한다. 최종안이 요청에 등록됐지만 아직 읽지 않은 사례를 처음 인용하면 서버가 그 원문을 추가 조회하고 로컬 JSON을 1회만 다시 받는다. 재작성에서 또 다른 미조회 사례를 인용하거나 원문이 안전한 문맥 크기를 넘으면 기존처럼 `LOCAL_EVIDENCE_NOT_READ`로 차단한다.
- 이 사례 교정은 Qwen·Gemma만 다시 호출하며 OpenAI 호출·웹검색·권한을 추가하지 않는다.
- 조회 결과가 크면 일부를 몰래 잘라 주지 않는다. 긴 `draft_report`/`previous_draft`는 JSON 직렬화 조각을 offset 순서로 전부 읽어야 완료다. 그 밖의 큰 자료는 하위 경로를 안내한다. 필수 조회 미완료·문맥 초과 시 `local_first`는 실패로 남기며 유료 대체하지 않는다. 기존 `hybrid`의 명시적 폴백은 유지한다.
- 관측·ML 전망·사업 가정은 구분한다. 지역 격차는 `선택 지역 - 비교 지역`이다. 소비 증가의 인과 근거가 없으면 임의 증가율을 제시하지 않는다.
- OpenAI 없는 실시간 공식 검색은 이번에 추가하지 않았다. 새 검색 API/서비스를 정한 뒤 수집·출처 검증 도구를 별도 연결해야 한다.

## 어디서 확인하는가

- UI: `/llm-control` → 실제 시도 Provider, 성공/실패, OpenAI 대체 실행, 근거 도구 조회.
- ACTIVE: 서버/모델 태그 연결 확인이며 실제 추론이나 GPU 사용을 의미하지 않는다.
- API: `GET /ai/v1/llm/trace`, 저장 보고서 `agent_trace`. 서버 재시작 시 현재 프로세스 trace는 초기화된다.
- 영구 trace에 사용자 원문/첨부/함수 인자를 저장하지 않는다. 함수명·완료 상태·사용량 등만 남긴다.

## 검증

프로젝트 루트에서 외부 LLM 없이 실행한다.

```powershell
.\backend\.venv\Scripts\python.exe -m unittest ai_server.test_local_agent_tools ai_server.test_llm_router ai_server.test_openai_token_recovery ai_server.test_generation_readiness ai_server.test_report_orchestrator ai_server.test_plan_quality_gate -q
```

초기 점검에서는 원격 연결이 시간 초과했다. 이후 연결 복구 상태에서 `check_local_agent_smoke.py`의 합성 자료로 Qwen/Gemma 함수 조회와 JSON 응답을 확인했다. 잘못된 함수 인자의 제한된 교정도 추가했다. 전체 강남 기획 품질은 미검증이며, 합성 답변의 일정·KPI 문제를 관찰해 검수 지침과 과거 월 차단을 추가했다. OpenAI 유료 생성은 하지 않았다. 최신 범위/결과는 [로컬 우선 계획](LOCAL_FIRST_QUALITY_PLAN.md)을 본다.

2026-09-05 코드 검증: 로컬 Agent 도구·정책 unittest 64개 통과. 미조회 사례 자동 원문 조회, 로컬 1회 교정, 두 번째 새 미조회 사례 차단, 선택적 도구 단계 미완료 복구와 최종 JSON 미완료 1회 재생성을 각각 검증했다. 필수 근거 미완료는 우회되지 않는다. 실제 원격 Qwen·Gemma 연결도 별도 소형 구조화 요청으로 확인했으며, 전체 기획 생성·품질 승인을 대신하는 검증은 아니다.
