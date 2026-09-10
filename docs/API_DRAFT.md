# 프론트엔드 연동 API 초안

D-115: 공개 API 변경 없음. 로컬 후보 재생 CLI는 모델 원문 계약과 서버 보정 후 계약을 구분해 `stabilized_candidate_contract_passed`, `stabilized_issues`, `automatic_corrections`, `stabilized_decision`을 추가 기록한다. 이 진단은 유료 호출·보고서 저장·승인을 수행하지 않으며 보정 통과도 의미 품질 승인으로 취급하지 않는다.

D-114: React 화면 경로는 `frontend/src/routes.js`의 명시적 공개 경로와 `/diagnosis`·`/proposal` 별칭을 사용한다. 알 수 없는 주소는 클라이언트 404로 표시하며 `/api`·`/ai` 요청 계약은 바뀌지 않는다.

D-108: 공개 API 변경 없음. `compare_candidate_flow`는 후보 이용 흐름만 보는 로컬 CLI 실험이며 결과를 보고서에 저장하지 않는다. 예시 검토 상태와 보고서 승인은 별개이며 모든 실험의 report_approved는 false다.

D-107: 공개 API 변경 없음. 진단 CLI의 `--compare-thinking`은 동일한 첫 최종 요청을 Qwen `think=false/true`로 각각 한 번 호출하고 자동 교정 없이 종료한다. `comparison_arm`은 원문 응답·Schema/출처/작성 검사·사용량을 구분하며 `report_approved=false`를 유지한다. 운영 라우팅·호출 횟수·출력 한도는 변경하지 않는다.

D-105: 공개 API는 유지한다. 로컬 CLI의 `--fresh`는 기존 후보 없는 설계 비교 진단으로 보고서를 저장하지 않는다. 진단 결과에 candidate_contract_passed와 report_approved=false를 구분한다. KPI 주기 검사에서 분기별/매 분기도 명시적 주기로 인식한다.

내부 후보 출력의 candidate_type은 기존 작성 지시의 spend_conversion/stay_conversion/reservation_conversion/return_visit/access_and_mobility/experience_product만 허용한다. 사례 비교용 night_time_experience를 사업 유형으로 자동 변환하지 않는다. 코드 검사에서 후보 `.candidate_type`, `.title`, `.stop_or_scale_rule` 지적이 추가될 수 있다. 저장된 보고서는 자동 변환하지 않는다.

## 내부 근거 전달 보강 (2026-09-08, D-104)

공개 요청/응답 계약은 유지한다. 내부 get_region_metrics에 dataset_sources와 source_link_rule을 추가하며 관측에 source_id를 추측해 삽입하지 않는다. 오류 피드백이 있는 로컬 후보 재비교의 get_planning_decision에는 review_context.status=rejected_candidate_draft를 포함한다. 저장 보고서 승인 상태와 다른 내부 입력 표시다.

비용 검사에서 `수량×단가 산식:`이라는 표제만으로 통과하지 않는다. 표제를 제외한 본문에 곱셈식이 없는 금액 나열은 기존 budget_formula 작성 오류로 반환한다.

## 후보 작성 지시 보강 (2026-09-08, D-103)

후보 생성 Schema에 필드별 예산·측정·지역 적합성·출처 설명을 추가하고 로컬 시스템 메시지에 전달한다. 공개 요청/응답 필드는 유지한다. 전체 후보 보완 뒤 기계적으로 안전하게 고칠 수 있는 출처 ID·타지역 범위·미확정 예산 산식·측정 원장 문제는 서버 계약으로 보정하고 `needs_evidence` 검토용 본문을 작성한다. 필드 설명 추가나 JSON 성공, 서버 보정을 승인으로 간주하지 않는다.

후보와 strategy_brief의 budget_formula에도 가정 표시 없는 확정 총액 검사를 적용한다(D-103). 오류 field는 `planning_decision.design_candidates[N].budget_formula.fixed_total` 또는 `planning_decision.strategy_brief.budget_formula.fixed_total`이며 severity는 critical이다. N은 기존 검사와 같이 1부터 센다. needs_evidence도 이 검사에서 제외하지 않는다.

## PPT 견적 표시 (2026-09-08)

실제 보고서 다운로드는 저장 strategies[0].budget을 표시합니다. 저장 응답이나 DB를 수정하지 않습니다. 총액 미기재/복수 총액은 미확정으로 나타내며 오프라인 샘플 이외에는 별도 예시 견적을 생성하지 않습니다. 렌더 캐시 버전은 pptx-user35-v9-saved-budget-r3입니다.

## 목표 KPI 입력 (2026-09-08)

planning_brief에 선택 필드 visitor_target_pct(0~20), spending_target_pct(0~30)를 받는다. 둘 다 null 또는 둘 다 유한 숫자여야 한다. 생성 응답 execution_scenario에 명시적 사용자 목표만 전달한다. 미입력은 null이며, 마지막 사업 월 예측값 대비 계획 증가율이다. 효과 예측이 아니다.

## 전체 검수 결과 적용 (2026-09-07)

자동 보완 입력과 최종 quality_review는 코드 검사의 전체 지적을 사용한다. issues가 8개를 초과할 수 있다. 기존 validation_findings도 유지한다. approved 값만으로 화면 통과를 판단하지 않으며 점수 82 이상, 중대 오류 없음, 미검수 상태 아님을 함께 확인한다. 명시적인 final_audit_completed=false는 통과가 아니다.

## 후보 검증 실패 처리 (2026-09-09 변경)

기획안 생성 중 후보 보완 후에도 문제가 남으면 먼저 서버 안전 계약을 적용합니다. 미등록 ID는 제거하고, 타지역 범위는 선택 지역의 조건부 시범 범위로, 출처 없는 총액은 수량×미확정 비교견적 산식으로, 불완전한 측정은 분자·분모·원장·비교 기준이 있는 계약으로 바꿉니다. 이 경우 보고서는 `needs_evidence` 검토용 초안으로 반환되며 자동 승인하지 않습니다. 서버가 안전하게 복구할 수 없는 critical 근거 오류만 HTTP 422 `TRANSFERABILITY_CANDIDATE_VALIDATION_FAILED`로 종료합니다.

완료 작업을 다시 조회할 때 저장 본문이 없거나 현재 응답 Schema로 검증되지 않으면 `completed` 상태를 그대로 반환하지 않습니다. `failed`와 재생성 안내를 반환해 화면의 무한 폴링을 막습니다. 작업 조회 404는 브라우저가 오래된 작업 ID를 제거할 수 있도록 HTTP 상태를 유지합니다.

## 지역 챗봇 실행 정보 (2026-09-07)

`POST /ai/v1/demo/{region_code}/assistant-chat`: 응답 `generation_mode`는 `openai | local | offline_sample`, `execution`은 실제 `provider/model/usage/web_search_used/fallback`을 반환합니다. 대화는 `role/content` 형태로 최근 8개, 각 3,000자까지 받습니다.

웹 검색 허용은 모든 질문에 검색을 실행하라는 의미가 아닙니다. 수정·설명은 해당 라우트를 사용하고 명시적인 검색 요청만 검색 작업으로 보냅니다. 학생 절약 모드의 유료 검색 차단은 유지합니다. 수정안은 사용자 적용·저장 전에는 영구 반영하지 않으며 기존 검수 상태를 무효화합니다. 긴 기존 본문 수정의 근거 범위와 제약은 [점검 기록](QUALITY_INTEGRATION_AUDIT_20260907.md)을 참조합니다.

## 지역 검증 상태

`GET /ai/v1/regions/readiness-audit`는 최근 24시간 점검 결과의 지역코드·이름·data_ready·verified·issues만 노출한다. 서버 경로·개인 노트북 주소는 노출하지 않는다. 만료/파일 없음/조회 실패는 미검증이며 초록색으로 보이지 않는다.
`python -m ai_server.app.scripts.audit_all_regions`는 89개 활성 카탈로그의 실제 원자료·ML·SQL 비교·사례 및 최신 저장 기획안 목표·승인·출력을 점검한다. 로컬 AI 서버 8112가 필요하며 LLM 호출·SQL 변경·재학습은 하지 않는다. 초록색은 검사 시점의 통과이며 향후 생성 성공률이나 자료 100% 확보 보장이 아니다.

## 2026-09-07 PPT v9 실행 상세 추가

- endpoint/JSON schema 유지. 렌더 버전 `pptx-user35-v9-execution-detail-r1`.
- 6장 단계·기간 별도 열 및 중앙 정렬 헤더, 7장 세부 실행내역 추가. 이후 KPI 8장, 견적 9장, 출처 10장부터, 전체 11~12장.
- 상세 페이지는 저장된 사업 내용에 맞춘 실행 방법 제안이며, 미확정 협약·지원율·현장 조건을 새 사실처럼 만들지 않는다. 원문 업무와 발표자 노트를 보존한다.

## 2026-09-07 PPT v8 출력 계약

- endpoint·저장 JSON schema 변경 없음. 렌더 버전은 `pptx-user35-v8-readable-monthly-target-r1`.
- 3장 사업 설명, 4장 사업 설계와 방문자·소비액 비교 차트, 5장 서로 다른 운영방식 우선 사례, 6장 4단계 업무표(산출물은 노트 보존), 7장 방문·소비 별도 월별 예측·목표·증가율 표, 8장 견적, 9장부터 출처 1~2장과 감사 장.
- 비교 차트는 사업 기간의 처음 3개 저장 예측 월을 사용한다. 목표는 기존 `execution_scenario`의 명시적 목표율만 사용하며 미입력 시 비교선을 만들지 않는다. 예측 검증 범위 경고도 표시한다.
- 5개 실행 단계가 있으면 마지막 2개를 네 번째 표시 단계에 합쳐 원문 업무·산출물을 모두 보존한다. 역할·추가 확인 항목은 제안으로 구분한다.
- 출처명 생략 부호를 사용하지 않는다. 전체 명칭은 1~2장에, 원문 URL은 하이퍼링크와 발표자 노트에 보존한다. 텍스트가 최소 가독 크기에도 들어가지 않으면 누락 대신 명확한 배치 오류를 반환한다.
- 사진 캡션은 API 응답의 장소명·주소를 사용하며 확인하지 않은 위치를 만들지 않는다. AI/ML/SQL 원본을 변경하지 않고 출력 사본만 편집한다.

## 2026-09-07 실행 근거 계약과 자료 요청

기존 endpoint·요청 schema는 유지합니다. 새 보고서 `quality_review`에 다음 선택 필드를 저장합니다.

- `quality_contract_version`: `execution-evidence-v1`. 작성/검수에 같은 실행 근거 규칙을 적용한 버전입니다.
- `validation_findings`: 상위 항목으로 줄이지 않은 결정적 코드 점검 전체. 각 행은 `severity`, `field`, `problem`, `revision_instruction`입니다.
- `completion_checklist`: `id`, `title`, `action`, `required_materials`(문자열 배열), `owner`, `status`를 가진 보완 안내 배열입니다. '없음'이 확정된 데이터 목록이 아니라, 생성 결과에 따라 재조회/확인이 필요한 자료입니다.

React는 `issues`와 `validation_findings`를 중복 제거해 전부 표시합니다. 이전 저장 보고서에 새 필드가 없어도 표시·다운로드는 유지합니다.
수동 본문 편집 후에는 이전 검수와 자료 안내도 재확인이 필요합니다. HTTP 성공·저장 성공이 집행 승인이라는 뜻은 아닙니다.
Qwen 후보 보완은 로컬 우선 경로에서 최대 1회이며 `agent_trace`에 남습니다. 학생 절약 모드의 유료 최종 검수 1회 상한·82점/major 차단 정책은 유지합니다.
[정비 원인과 자료 요구사항](WONJU_PROPOSAL_QUALITY_AUDIT_20260907.md).

## 2026-09-05 PPT 예측·KPI·견적·전체 출처 보완

- `GET /ai/v1/strategy-reports/{report_id}/documents/pptx`의 경로·요청 계약은 그대로입니다.
- 렌더 버전 `pptx-user35-v6-exact-ml-kpi-full-sources-r2`와 `tourism_strategy_12_slide_template_v6.pptx`로 이전 PPT 캐시를 갱신합니다.
- 월별 방문자·소비액은 `select_report_forecast`가 선택한 사업 기간의 저장 예측입니다. 관측월을 예측 차트에 섞거나 반올림 값을 재계산 입력으로 쓰지 않습니다.
- 입력된 `execution_scenario`가 있으면 최종 월 목표를 표시합니다. 없으면 지역 전체 증가율을 만들지 않고, 명시적 견적 가정에 따른 별도의 참여·환급 목표를 표시합니다. 이 값은 보고서 JSON·ML·검수 상태를 변경하지 않습니다.
- 참고 견적은 수량×가정 단가이며 확정 견적이 아닙니다. 고정비보다 작은 입력 예산은 실행 가능하다고 표시하지 않습니다.
- MySQL `data_source`에서 기존 source ID의 파일명만 읽어 출력 사본을 보완합니다. DB 조회 실패 시 저장 출처를 삭제하지 않습니다. 11장부터 전체 출처를 이어 싣고, 마지막에 감사 페이지를 둡니다. 모든 원자료명·URL·원수치·검증값은 발표자 노트에도 보존합니다.
- 파일 다운로드에서는 OpenAI·Ollama·재학습을 호출하지 않습니다. 기존 지역 사진 캐시/공식 사진 다운로드는 사용할 수 있습니다.

## 2026-09-02 출력 안전성 보완

- `execution_scenario` 생략/null 가능. 객체에는 `visitor_target_pct`, `spending_target_pct` 둘 다 필수이며 기본 증가율은 없다.
- `ml_analysis.evaluation.metrics.*`, `signals.*`의 `model_reliability`로 연결과 성능을 구분한다.
- 공통 기획 월·목표 산식, Word 캐시 버전 `strategy-docx-v3-period` 적용. PPT의 최신 버전은 위 2026-09-05 항목을 따른다.
- 문서 준비 동안 작업은 running, 형식별 경고를 포함한 completed 가능. production 결제 오류는 샘플로 반환하지 않는다.

## 2026-09-02 생성 전 검토 계약 추가

- 토큰 부족(`status=incomplete`, `reason=max_output_tokens`)에는 같은 Agent 요청만 더 큰 출력 상한으로 1회 재시도한다. 전체 기획 파이프라인을 다시 실행하지 않는다. 단계별 값은 `GENERATION_TOKEN_BUDGETS.md` 참조.
- `/ai/v1/llm/trace`의 이벤트에 `attempts`, `retry_count`, `max_output_tokens`를 추가한다. 실패 이벤트의 `error_code`와 API가 보고한 `usage`도 보존하며, OpenAI 폴백 실패도 별도 이벤트로 남긴다.
- 각 `attempts` 항목은 시도 번호·상한·상태·이유·소요 시간·보고된 사용량·`usage_reported`를 제공한다. 프롬프트·답변 원문·인증값은 포함하지 않는다. 이벤트 `usage`는 모든 시도의 합계이며 내부 추론 토큰은 출력 토큰에 이미 포함된다.
- 사용량 요약의 `usage_unknown_attempts`는 토큰 수를 확인하지 못한 시도 수다. 0토큰/무료로 해석하지 않는다. 기존 요청 본문·응답 기획안 계약·품질 승인 기준은 유지한다.

- 생성·저장 `ReportResponse`에 `planning_decision` 추가(기존 보고서는 `{}`). 후보별 작동 원리·지역 적합성·차별성·확보 조건·비용/측정/중단 기준 및 선정 이유를 보존한다.
- `quality_review.approved`는 82점 이상이며 critical/major가 모두 없을 때만 참이다. 미승인 초안도 복구·수정을 위해 반환할 수 있으므로 HTTP 성공을 품질 통과로 해석하지 않는다.
- React에서 챗봇 수정을 반영하면 `quality_review.review_stale=true`, `approved=false`로 이전 승인 상태를 무효화한다.
- ML `horizon_policy.as_of_date`는 기획 기준일이다. 일정 미정의 `decision_windows`는 현재 월 이후 3·6개월이며 관측 공백 월은 실행 합계에서 제외한다. 12개월 한도를 넘으면 `coverage_complete=false`다.
- Ollama 문맥 예산 초과/미완료 출력은 `OLLAMA_CONTEXT_BUDGET_EXCEEDED` / `OLLAMA_INCOMPLETE_RESPONSE`로 추적한다. Hybrid는 한 번 OpenAI 폴백 가능, local_only는 불가하다.
- 공식 웹 필수 호출의 실제 실행/URL 확인 실패는 `OPENAI_WEB_SEARCH_NOT_EXECUTED` / `OPENAI_UNVERIFIED_WEB_SOURCE`로 남긴다. 실패한 조사를 성공한 것으로 캐시하지 않는다.

> 상태: UI 골격용 초안. 실제 데이터 파일의 컬럼·지역 코드·기간을 검증한 뒤 Pydantic schema로 확정한다.

## 기본 원칙

### 로컬 우선 비용 정책 (D-063)

- `PUT /ai/v1/llm/config`: `mode=student_budget`은 Qwen·Gemma 중심의 학생용 기본 모드다. 자동 OpenAI Web Search를 막으며, 로컬 통과본의 독립 최종 검수 1회만 허용한다. 무료 검색 API 키가 있을 때만 Qwen 검색 질문→서버 제한 도구→공식 도메인 요약 후보 경로를 추가한다. `local_first`는 최신 공식 웹 조사·사례 보강까지 포함한 최대 3회 모드다.
- `GET /ai/v1/llm/status`: `effective_routes`는 비용/능력 잠금을 적용한 실제 경로다. `student_budget`의 `evidence`·`case_study` provider는 `local_sources`로 표시되며 OpenAI Web Search가 아니라 MySQL·공식 Open API·검수 RAG와 선택적 무료 공식 검색 도구 경로임을 뜻한다. `cost_policy.free_official_web_search`는 키 존재 여부·공급자 이름·보고서당 질문 상한만 제공하며 비밀값은 반환하지 않는다.
- trace의 `paid_reason`은 유료 요청 목적, `status=blocked`와 `provider_called=false`는 실제 호출하지 않은 차단이다. 차단을 성공/0토큰 추론으로 표시하지 않는다.
- 오류 `LOCAL_FIRST_MODELS_UNAVAILABLE`: 유료 조사 전 개인 모델 연결 실패. `STUDENT_BUDGET_WEB_SEARCH_DISABLED`: 학생 절약 모드에서 자동 웹 조사를 요청함. `CLOUD_CALL_BUDGET_EXCEEDED`: 허용되지 않은 유료 단계 또는 해당 모드의 요청 상한 초과.
- 보고서 `quality_review.final_audit_completed`는 최종 독립 검수 완료 여부다. `approved=false`를 우회하지 않으며, 미완료 시 초안을 보존한다. `review_error_code`는 1차 검수 연결 실패다.
- 3회는 생성당 Provider 요청 상한이지 웹검색 내부 호출/원화 상한이 아니다. [전체 범위](LOCAL_FIRST_QUALITY_PLAN.md).

### 로컬 기획 Agent 실행 기록 (D-062)

기존 `GET /ai/v1/llm/trace`의 각 이벤트와 보고서 `agent_trace`에 다음 선택 필드를 추가한다. 기존 소비자는 추가 필드를 무시할 수 있다.

- `provider`: 실제 시도 역할 `qwen` / `gemma` / `openai`. `status`는 `completed` 또는 `failed`다.
- `tool_trace`: `{tool, status}` 목록. 인자·본문·첨부 원문·비밀정보는 포함하지 않는다.
- `input_preparation`: 성공 시 `mode=request_scoped_evidence_tools`, 원본/개요 바이트 수, 가용/조회 출처 수. 토큰 수와 바이트 수를 혼동하지 않는다.
- `attempts[].phase`: 로컬의 `tool_selection` / `final_json` / `json_repair` / `citation_repair`. `citation_repair`는 최종안이 등록된 미조회 사례를 인용했을 때 서버가 그 원문을 읽고 같은 로컬 모델에 한 번만 재작성을 요청한 기록이다. 도구 선택은 오류 재시도 횟수에 합산하지 않는다.
- 실패 코드: `LOCAL_TOOL_NOT_ALLOWED`, `LOCAL_TOOL_ARGUMENTS_INVALID`, `LOCAL_TOOL_LIMIT`, `LOCAL_REQUIRED_EVIDENCE_MISSING`, `LOCAL_EVIDENCE_NOT_READ`, 기존 `OLLAMA_CONTEXT_BUDGET_EXCEEDED` 등. 설정된 Hybrid 폴백은 원래 요청 전체를 보존해 별도 이벤트로 기록한다.

`LOCAL_EVIDENCE_NOT_READ`는 첫 미조회 사례 인용 즉시 발생하지 않는다. 요청에 등록된 공식 사례라면 서버가 원문을 읽고 로컬 교정을 한 번 시도한 뒤에도 새 미조회 사례를 인용하거나 원문 전달이 불가능할 때 반환한다. 이 복구는 OpenAI 호출 예산을 소비하지 않는다.

도구 선택 단계의 `OLLAMA_INCOMPLETE_RESPONSE`는 필수 사전조회가 모두 완료됐을 때만 `attempts[].status=continued_without_optional_tools`로 기록하고 최종 JSON 단계로 진행할 수 있다. 필수 근거가 남아 있으면 기존처럼 작업을 실패시킨다. 이는 잘린 기획 본문을 채택하는 정책이 아니며 최종 JSON의 완료·Schema·출처 검증은 그대로 적용한다.

최종 JSON 단계에서 같은 오류가 발생하면 `attempts[].status=retrying_after_output_limit`, 다음 phase는 `incomplete_retry`로 기록한다. 부분 응답은 폐기하고 동일 근거·Schema·출력 상한으로 처음부터 한 번만 재생성한다. 두 번째 미완료는 `OLLAMA_INCOMPLETE_RESPONSE`로 실패한다.

이 도구들은 내부 함수이며 외부 HTTP 실행 엔드포인트를 새로 열지 않는다. `search_collected_sources`는 기존 수집 자료 검색이지 실시간 웹검색이 아니다. 도구 사용이 가능한 코드와 실제 모델 실행 성공 여부는 구분한다.

### 사업 여건 계약 (2026-08-28 구현)

`POST /ai/v1/demo/{region_code}/strategy-report/jobs`의 기존 요청에 선택 필드 `planning_brief`를 추가한다. 생략하면 기존 호출과 호환된다.

```json
{
  "region_name": "서울특별시 강남구",
  "planning_brief": {
    "version": 1,
    "region_code": "11680",
    "budget_status": "confirmed",
    "budget_min_krw": null,
    "budget_max_krw": 30000000,
    "budget_hard_limit": true,
    "schedule_status": "fixed",
    "start_date": "2026-10-01",
    "end_date": "2026-12-31",
    "resources_confirmed": "",
    "resources_possible": "",
    "hard_constraints": "신규 시설 설치 제외",
    "preferences": "",
    "field_context": "",
    "references": []
  }
}
```

- 예산 상태: `unknown | indicative | confirmed`. 미정 금액은 null. 지정 금액은 1원~1조 원 정수이며 최소≤최대.
- 일정 상태: `unknown | flexible | fixed`. 지정 시 시작일·종료일 모두 필요, 시작≤종료.
- 자원은 확정/협의 중을 구분한다. 제약과 선호도 별도 필드다.
- 문서 `references`: `{name, text}` 최대 3개, 텍스트 각 6,000자 이하. 지시문이 아닌 사용자 제공 데이터로만 사용한다.
- 지역 불일치·조건 오류: HTTP 422. 작업 등록: HTTP 202 + 기존 job_id. 생성 결과에 `planning_brief`와 SHA256 `planning_brief_fingerprint`를 보존한다.
- 기존 채팅 요청도 `planning_brief`를 받는다. 현재 기획안이 있으면 그 기획안의 생성 당시 조건을 우선한다.

`POST /ai/v1/planning/reference?filename=자료.docx`

- body: 파일 바이트, Content-Type: application/octet-stream. TXT/MD/DOCX만 지원한다.
- 성공: `{name, text}`. 파일은 2MB 이하, DOCX 압축 해제 합계 12MB 이하. 초과 413, 잘못된 파일/텍스트 초과 422 + `detail: {code, message}`.
- 유료 AI·웹 호출 없이 메모리에서 읽는다. 원본 디스크 저장·공용 RAG 등록 없음.

- React는 `/api`와 `/ai` 경로만 호출한다.
- 로컬 개발에서는 일반 데이터 Backend FastAPI(`8100`), 원자료·근거 기반 전략 AI FastAPI(`8112`)가 담당한다. 배포 포트는 Nginx 뒤에서 별도로 설정한다.
- OpenAI API 키는 어떤 응답이나 React 코드에도 포함하지 않고 AI 서버의 `.env`에서만 읽는다.
- 모든 실제 수치에는 `region_code`, `year_month`, `source_name`, `source_url`을 함께 보존한다.

## 구현된 테스트·지도 엔드포인트

### `GET /api/v1/boundaries/sido`

첫 지도 단계에서 보여 줄 시도 경계를 반환한다. VWorld의 현행 경계 기준으로 광주·전남 통합처럼 행정구역이 변경된 경우에는 해당 기준을 그대로 표시한다. VWorld 시도 레이어에 누락될 수 있는 세종특별자치시는 시군구 경계에서 보완한다.

### `POST /ai/v1/demo/{region_code}/strategy-report`

`region_name`을 본문에 넣어 요청한다. AI 서버는 선택 지역 원본·Open API·지역 공식 문서를 Evidence Pack으로 만들고, Case Scout가 전국 공식 성과평가·결산·예산·보도자료에서 실제 집행 사례를 찾는다. Transferability Agent가 선택 지역 적용 조건을 평가한 뒤 Planner가 구조화 기획안을 작성한다. Reviewer는 근거·사례 오용·비교·실행성·간결성·공무원 활용성·시각자료를 검토하며 미달 시 한 번 재작성한다. 응답에는 기존 필드와 함께 `quality_review`, `evidence_sources`, `research_gaps`, `agent_trace`가 포함된다.

### `GET /ai/v1/demo/{region_code}/dashboard?region_name={region_name}`

선택 지역 공식 원본을 읽기 전용으로 계산해 상단 카드용 최신 기준월, 외지인 방문자 수, 외지인 관광소비액, 평균 숙박일수와 각각의 전월 대비를 반환한다. 이 경로는 OpenAI를 호출하지 않는다.

강남구(`11680`)는 예외적으로 저장된 ML artifact를 읽어 최근 3개월 관측값과 향후 3개월 예측값을 반환한다. 학습은 이 HTTP 요청에서 실행하지 않는다. `monthly_trend[].is_forecast`로 관측·예측을 구분하며, `forecast`에는 모델 버전·시간순 테스트 기간·MAE·한계를 담는다. `diagnostic.is_forecast=true`인 업종별 소비 금액은 전체 소비액 예측에 최신 관측 업종 비중을 적용한 가정이다.

### `GET /ai/v1/demo/sido-comparison?sido_name={sido_name}`

선택 시도 아래의 원본 보유 시군구를 대상으로, 모든 지역에 공통으로 존재하는 가장 최근 3개월의 순 방문자 수·외지인 관광소비액·숙박 방문 비율·평균 숙박일수 평균을 반환한다. 원본이 없는 시군구의 값은 만들지 않으며, 비교 가능한 시군구가 2개 미만이면 응답하지 않는다.

```json
{
  "region_name": "서울특별시 강남구",
  "latest_month": "2026-07",
  "source": "한국관광 데이터랩 강남구 공식 다운로드 ZIP",
  "metrics": [
    {
      "label": "7월 방문자 수",
      "value": "17,963,441명",
      "detail": "순 방문자 수",
      "change_label": "전월 대비",
      "change_value": "-0.1%",
      "change_direction": "down"
    }
  ]
}
```

현재 지원 지역의 원본 연결을 검증하는 경로다. 정식 서비스에서는 검증·전처리한 월간 지표를 MySQL과 일반 Backend의 `GET /api/v1/regions/{region_code}/dashboard`로 이전한다.

### `GET /ai/v1/demo/{region_code}/tourism-status`

지역별 관광 현황 ZIP에서 전수 검증·정규화한 선택 지역의 유입·유출 권역, 인기 관광지·음식점,
향후 30일 집중 운영 신호와 출처를 반환한다. OpenAI와 로컬 LLM을 호출하지 않는다.

- 성공: `200` — `available`, 기준 기간, 상위 유입·유출 권역, 인기장소 묶음, 집중 신호 및 source record.
- 미지원: `404 REGIONAL_TOURISM_STATUS_UNAVAILABLE` — 공식 코드에 매핑·검증된 사실표가 없는 지역.
- 해석: 유입·유출 비율과 인기 순위는 관측 분포이고, 집중률은 운영 참고 신호다. 월별 ML 예측값·확정 수요·정책 효과로 사용하면 안 된다.

### `GET /ai/v1/demo/{region_code}/region-info?region_name={region_name}`

지역 선택 화면의 `지역 정보 상세보기` 팝업이 호출한다. 서버 `.env`의 한국관광공사 국문 관광정보 API 키로 `areaCode2`와 `areaBasedList2`를 조회하고, 관광자원명·분류·주소·제공 이미지 URL만 반환한다. 이 경로는 OpenAI를 호출하지 않는다.

월간 방문자·관광소비 수치는 이 경로에서 계산하지 않으며, 기존 `/dashboard` 원자료 응답과 화면에서 출처를 분리해 표시한다. API 키 미설정, 일시 오류, 지역명 미일치, 빈 결과는 HTTP 오류 대신 `status`와 사용자용 안내문으로 반환해 대시보드 전체가 멈추지 않게 한다.

### `POST /ai/v1/demo/{region_code}/strategy-report/jobs`

긴 AI 전략기획 생성을 서버 백그라운드 작업으로 등록하고 HTTP `202`와 `job_id`를 즉시 반환한다. React는 작업 ID를 브라우저 localStorage에 지역별로 보관한다. 따라서 사용자가 다른 페이지·탭으로 이동한 뒤 AI 전략기획 화면에 돌아와도 같은 작업을 계속 조회할 수 있다.

### `GET /ai/v1/demo/{region_code}/strategy-report/jobs/{job_id}`

백그라운드 작업의 `queued`, `running`, `completed`, `failed` 상태와 사용자용 안내문을 반환한다. 완료 시에만 구조화된 `ReportResponse`를 포함하며, React는 이를 저장 기획서 목록에 한 번만 기록한다. 개발 서버 재시작은 메모리 작업을 중단하므로, 운영 환경에서는 Redis·Celery 또는 DB 기반 작업 큐로 교체한다.

### `GET /api/v1/boundaries/sigungu?sido_code={2자리 시도 코드}`

VWorld WFS의 전국 시군구 경계를 Backend에서 불러와, 키가 없는 GeoJSON으로 반환한다. `sido_code`를 보내면 브라우저에는 선택 시도의 경계만 반환한다. VWorld는 한 요청에 1,000개 도형 제한이 있어 Backend가 BBOX 분할·중복 제거·시군구별 MultiPolygon 병합을 수행한다. 지도 표시용 좌표는 약 100m 허용오차로 단순화하며 통계·측량에는 사용하지 않는다.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "region_code": "11680", "region_name": "서울특별시 강남구" },
      "geometry": { "type": "MultiPolygon", "coordinates": [] }
    }
  ]
}
```

이 엔드포인트는 지도 표현용 경계에만 사용한다. 관광 원자료와의 실제 조인은 데이터랩 파일의 지역 코드 기준을 검증한 뒤 별도 매핑표로 수행한다.

2026년 6월까지의 인천 서구 원자료를 선택할 수 있도록, 인천 요청에는 현재 서해구·검단구 경계를 합친 코드 `28260` 호환 Feature를 추가한다. `display_name`은 `인천광역시 서구 (2026.06 원자료 기준)`이며 현재 두 구의 통계를 합산했다는 의미가 아니다.

## 예정 엔드포인트

### `GET /api/v1/regions/{region_code}/dashboard`

지역 대시보드에 표시할 검증된 사실을 반환한다.

```json
{
  "region_code": "11680",
  "region_name": "서울특별시 강남구",
  "period": { "from": "2023-01", "to": "2026-06" },
  "metrics": {
    "visitor_count": null,
    "tourism_spending_krw": null,
    "stay_ratio": null,
    "spending_per_visitor_krw": null
  },
  "monthly_trend": [],
  "sources": []
}
```

### `POST /ai/v1/regions/{region_code}/strategy-report`

저장된 지표·예측·공식 근거 문서를 바탕으로 AI 전략 보고서를 반환한다. LLM은 숫자를 계산하거나 출처 없는 사실을 만들지 않는다.

```json
{
  "region_code": "11680",
  "observation": [],
  "forecast": null,
  "recommendations": [],
  "sources": [],
  "generated_at": "2026-08-24T00:00:00+09:00"
}
```

## 현재 화면과의 연결 위치

- `frontend/src/api/dashboardApi.js`: 위 두 엔드포인트 호출 자리
- `frontend/src/pages/TourismDashboardPage.jsx`: 실제 응답을 카드·차트·진단에 표시하며 미지원 지역은 빈 상태로 처리
- `frontend/vite.config.js`: 개발 중 `/api → 8100`, `/ai → 8112` 프록시 설정
- `backend/app/services/vworld.py`: VWorld 키를 서버에서만 사용하고 시군구 GeoJSON을 캐시·중계
# ML 기획 근거 확인

`GET /ai/v1/ml/{region_code}/planning-evidence?region_name={region_name}`

- 저장 모델만 읽으며 OpenAI 호출이나 온라인 재학습을 하지 않는다.
- `status=available`일 때 방문·소비·체류·검색 7개 지표의 전망, 전년 동월 비교 신호, Validation/Test 오차와 의사결정 단위로 묶은 조사 질문을 반환한다.
- 기획안 내부 호출은 `planning_brief`를 함께 전달한다. 일정 미정이면 3·6개월 후보를 모두 만들고, 희망 일정이면 종료월까지 필요한 전망을 최대 12개월 범위에서 계산한다.
- `horizon_policy`에는 선택 근거, 전망 시작·종료월, 기획 비교 구간, 전체 일정 포함 여부와 신뢰도 구분이 들어간다. 1~3개월은 재귀 백테스트, 이후 월은 탐색 전망이다.
- 미지원 지역은 `unsupported`, 모델 재학습 필요·원자료 불일치는 `unavailable`로 반환하며 다른 지역 모델을 대신 쓰지 않는다.

## ML 학습 페이지 카탈로그

`GET /ai/v1/ml/learning/catalog`

- `region_registry.py`에 등록된 모델만 지역 선택 목록에 반환한다.
- 모델 메타데이터의 `target`을 순회해 데이터셋, 모델, Feature, 함수, 기법, Test 오차와 3개월 결과를 카드 단위로 반환한다.
- 새 지역이나 새 Target이 동일 계약으로 등록되면 React의 `MlTest` 페이지는 별도 카드 코드를 추가하지 않고 자동으로 목록을 늘린다.
- 학습용 읽기 전용 API이며 OpenAI, Open API, 모델 재학습을 실행하지 않는다.

### `POST /ai/v1/ml/learning/{region_code}/assistant`

- 요청: `question`, 최근 대화 `history` 최대 6개.
- AI Server가 선택 지역의 등록 모델 카탈로그, 코드 역할표, 기획안 전망기간 규칙을 OpenAI Responses API에 전달한다.
- 답변: `answer`, `key_points`, `related_modules`, `caution`의 구조화 JSON이다.
- 현재 ML 챗봇은 RAG·웹 검색을 사용하지 않는다. OpenAI 키가 없으면 `503 OPENAI_KEY_MISSING`, 미지원 지역은 `404 ML_LEARNING_REGION_UNAVAILABLE`을 반환한다.

### 독립 후보 진단 CLI (D-109)

`evaluate_candidate_feasibility`, `evaluate_pilot_planner`, `evaluate_pilot_reviewer`는 동결 입력/산출물을 읽는 개발 진단이며 신규 HTTP API가 아닙니다. `--run`일 때만 지정 Ollama에 단회 요청하고, 보고서 저장·OpenAI·운영 Router를 호출하지 않습니다. 서버 소유 임시 예산/측정 계약을 LLM 서술과 분리합니다. 실행과 결과는 [검증 기록](CANDIDATE_FEASIBILITY_20260908.md)을 참조하세요. 기존 생성 API 계약은 변경하지 않습니다.

### `GET /ai/v1/learning/{topic}`

- `topic`은 `openai` 또는 `react`다.
- OpenAI는 Agent 클래스·오케스트레이터·FastAPI route·환경변수 이름을, React는 src 파일·App route·fetch endpoint·package.json을 현재 소스에서 다시 읽는다.
- 파이프라인, 파일 역할, route, 의존성, 설계 원칙과 챗봇 흐름을 반환한다. 절대경로·소스 전문·환경변수 값은 반환하지 않는다.

### `POST /ai/v1/learning/{topic}/assistant`

- 자동 생성한 해당 주제 카탈로그와 최근 대화 최대 6개를 OpenAI에 전달한다.
- 답변은 `answer`, `key_points`, `related_files`, `caution` 구조다.
- RAG·웹 검색을 사용하지 않으며, 현재 프로젝트에 없는 기능을 사용 중이라고 설명하지 않도록 제한한다.


### 사례 기반 아이디어와 목표 조정 (2026-09-09)

PPT 공통 출력 버전은 `pptx-idea-case-basis-v11`입니다. 기존 다운로드 API에서 사례 선정 근거 페이지와 수정된 차트 레이아웃을 반환하며, 추가 LLM 호출 없이 저장된 후보·공식 출처로 구성합니다.
기획안은 사례 기반 아이디어와 편집 가능 항목을 먼저 보여줍니다. `execution_scenario`가 없으면 최종월 방문·소비 +5%를 계획 가정으로 제안합니다. `target_proposal_basis`에 근거/가정 구분, `reference_estimate`에 항목별 임시 견적을 전달하며 Word/PPT에 동일 반영합니다. 관측·ML·검수 승인 값은 유지합니다. 챗봇에서 “방문 목표 4%, 소비 목표 5%로 바꿔줘”, “견적 총액 1억원으로 변경”처럼 요청할 수 있습니다. 현재 근거 연결 후보 밖의 건물·공원 신축은 지원 범위 밖으로 안내합니다. 상세 정책은 DECISIONS D-124 참조.

`POST /ai/v1/strategy-idea-preview`: ReportResponse를 받아 목표·견적을 보완한 미리보기 반환. LLM 호출/DB 쓰기 없음. 과거 브라우저 보고서에도 같은 기본값을 표시한다.
# PPT 목표 소비 계산 표시

프로젝트 학습 카탈로그의 OpenAI `agents[].contract`는 페르소나·입력·출력·도구·설정 이름과 공개 지시문 발췌를 제공합니다. 실제 API 키·환경변수 값은 포함하지 않습니다.

`GET /ai/v1/ml/learning/catalog`의 `regions[].modules[].strategy_usage`는 관리자용 활용 설명을 추가 제공합니다. `role`, `aggregation`, `research_group`, `steps`, `tree`, `display`, `interpretation`, `example`, `limit`을 포함하며 기존 모델·예측·평가 필드는 유지합니다. 미정의 Target은 빈 설명 객체를 반환합니다.

현재 출력 버전은 `pptx-case-wrap-v13`이며 사례 카드의 줄바꿈·여백 수정도 포함합니다. API 계약은 동일합니다.

PPT 출력 버전 `pptx-visitor-spending-formula-v12`는 동일 방문·소비 목표율에 대해 월별 소비/방문 비율과 추가 방문 기반 소비 산식을 표시합니다. 기존 목표값과 동치이며 API 입력·저장 ML은 변경하지 않습니다. 서로 다른 명시 목표율은 각각 적용하며 방문 0인 월의 비율은 추정하지 않습니다.
# 기획서 사례 연결 메타데이터 (2026-09-10)

최신 PPT 렌더 버전: `pptx-similar-case-images-v16`. 사진 메타데이터의 `match_kind`는 `exact_case` / `similar_operation` / `general_tourism_reference`이며 발표자 노트에 출처와 함께 기록합니다.

이미지 변경 후 최신 PPT 렌더 버전은 `pptx-official-case-images-v15`입니다. 사례 ID에 연결된 공식 웹 이미지를 사용하며 요청 스키마는 동일합니다.

`planning_decision.case_linkage` 및 후보별 `case_linkage`는 `operation-document-v1` 규칙, 원래 사례 ID, 함수 연결 ID, 환경 유사성 검증 여부를 제공합니다. 원래 LLM 평가 목록은 `original_candidate_assessments`에 보존합니다. 출처에는 수집 경로 `retrieval_method`와 문서 유형·측정기간을 전달합니다. PPT 렌더 버전은 `pptx-evidence-cases-v14`이며 URL과 요청 스키마는 유지합니다. 원본 보고서를 DB에서 일괄 수정하지 않습니다.


### 기획 입력 간소화 (`guided_v1`, 2026-09-10)

기획 생성 페이지는 사업 방향, 참고 예산 총액, 시작 월(3개월 시범), 활용 자원 300자, 제외 운영 방식, 메모 500자를 받습니다. KPI 입력·예산 범위/확정 상한·종료일·첨부자료는 기본 생성 화면에서 제거했습니다. 예산은 견적 배분 예시이며 ML 전망이나 실행 가능성을 보장하지 않습니다.

`planning_brief.input_profile="guided_v1"`에서 `business_direction`은 `auto|spend_conversion|stay_conversion|night_time_experience|return_visit`, `excluded_operations`는 `night_time_experience|spend_conversion` 배열입니다. 예산은 `unknown` 또는 `indicative`와 `budget_max_krw` 하나를 사용합니다. 시작 월 미입력은 현재 월부터 3개월로 정규화합니다. 숨겨진 구형 입력 및 충돌은 Pydantic 검증에서 거절합니다. 공식 근거/선정 조건 불일치는 `PLANNING_CONDITIONS_UNSUPPORTED`, 전망 기간 부족은 `PLANNING_PERIOD_UNSUPPORTED`로 안내합니다. 기존 API의 profile 미입력은 `legacy`로 처리하며 저장 보고서를 변경하지 않습니다. 상세 결정: D-136.


지역 준비 표시(D-137): `GET /ai/v1/regions/readiness-audit`는 `local_models_ready`, `local_model_message`, 지역별 `generation_ready`를 반환합니다. 초록색은 최근 24시간 이내 `data_ready`와 현재 설치된 Qwen/Gemma 연결을 모두 확인한 경우입니다. 기존 `verified`(저장 기획안 승인)와 구분하며 새로운 생성 성공을 보장하지 않습니다. 미점검/만료는 초록색으로 표시하지 않습니다. 자료 감사 갱신: `backend/.venv/Scripts/python.exe -m ai_server.app.scripts.audit_all_regions` (LLM 생성·재학습·SQL 쓰기 없음). 모델 목록 연결 확인은 15초 제한, 생성 전 일시 실패에만 1회 재확인합니다.


### D-138 생성 진행 단계 표시 (2026-09-10)

생성 대기 화면 제목은 ‘기획서 초안을 생성중입니다’. 작업 조회 응답에 `progress_step`을 추가한다: 0 데이터 분석(연결 확인 포함), 1 공식사례 확인(지역 근거 병행), 2 기획안 생성(후보 비교·초안), 3 품질검토(보완·재검수 포함), 4 검토 절차 종료 후 본문·문서 준비. null은 단계 미확인이다. 실제 실행 지점에서 요청별 ContextVar 콜백으로 메모리 작업 상태를 갱신하며 기존 3초 상태 조회로 표시한다. 경과 시간으로 단계를 추측하지 않는다. 진행 단계는 파란 음영 애니메이션, 완료 단계는 파란 채움, 대기 단계는 기존 외곽선으로 구분한다. 재접속 시 서버 상태를 다시 읽고 연결 오류에는 확인 지연을 표시한다. 단계 완료는 품질 승인과 다르며 모델/유료 호출 수는 변경하지 않는다.
