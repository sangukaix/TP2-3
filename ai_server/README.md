# AI Server

`python -m ai_server.app.scripts.compare_candidate_flow FROZEN_INPUT --run`은 저장된 D-107 근거로 후보 하나의 이용 흐름만 생성하는 진단입니다. `--run` 생략 시 입력만 준비합니다. `--reviewed-example FILE`은 사람 검토 상태의 예시만 허용하며 초안은 거절합니다. 운영 파이프라인에 적용되지 않습니다. [범위·실측](../docs/CANDIDATE_FLOW_EXPERIMENT_20260908.md).

`python -m ai_server.app.scripts.replay_candidate_repair REPORT_ID --fresh --compare-thinking`은 첫 최종 입력을 고정해 Qwen의 `think=false/true`를 각각 한 번 비교합니다. 필수 근거 조회·현재 Schema·출력 상한을 유지하며 자동 교정 없이 종료합니다. 입력은 `storage/candidate_comparison_input_*.json`, 응답/시간/사용량은 stdout JSONL에 기록합니다. 준비 단계 사용량과 두 최종 호출을 구분하며 사고 과정 원문은 기록하지 않습니다. 이는 명시 실행 진단이며 운영 설정·보고서 승인과 별개입니다.

후보 유형은 기존 허용 6개를 Schema enum과 코드 검사에서 함께 확인합니다. `예산 편성 모델 도입` 같은 우회 제목과 근거/가정 없는 성공·중단 수치도 차단합니다. 기존에 저장된 결과는 자동 수정하지 않습니다.

운영 생성에서는 Qwen 보완 뒤 남은 기계적 오류를 서버 계약으로 한 번 안전 보정합니다. 미등록 출처·타지역 범위·출처 없는 총액·측정 분모를 정리하고 `needs_evidence` 검토용 본문을 보존하며, 의미 판단이 필요한 지역 적합성·후보 차이는 최종 검수에 남깁니다. 자동 보정은 승인이나 실제 성과 검증이 아닙니다.

`replay_candidate_repair REPORT_ID --fresh`는 같은 근거·저장 ML로 이전 후보 없는 최초 설계를 비교하는 진단입니다. 기본 보완 경로와 별개이며 OpenAI 호출·보고서 저장·승인을 차단합니다. candidate_contract_passed는 작성 검사 결과이고 report_approved는 항상 false입니다.

로컬 후보 보완은 등록 사례 순서로 운영 원리를 재비교하고 이전 선택안은 오류 대조용으로 보존합니다. get_region_metrics는 dataset 출처 원문도 반환하며 모델이 관측과 지표·값·기간을 대조해야 합니다(D-104).

후보 예산·측정·지역 적합성·출처의 필드별 설명을 로컬 시스템 메시지에도 전달합니다(D-103). 도구 조회 후 전체 보완 피드백 보존과 직접 provider 경로를 회귀 검사하며, 실제 모델 품질 검증과 구분합니다.

후보와 선택안 요약의 가정 표시 없는 확정 총액도 본문 작성 전에 검출합니다. 근거 없는 금액을 임의 교정하거나 승인하지 않습니다.

로컬 후보 보완 진단은 `python -m ai_server.app.scripts.replay_candidate_repair REPORT_ID`로 명시 실행합니다. 현재 저장 근거와 snapshot을 사용하고 OpenAI 호출·보고서 저장은 차단합니다. [실측 기록](../docs/LOCAL_CANDIDATE_REPLAY_20260908.md).

실제 PPT 견적은 저장 기획안의 budget 본문을 사용합니다. 별도 예시 총액으로 바꾸지 않으며 금액의 타당성을 자동 승인하지 않습니다(D-101).

기획 조건의 선택 목표율은 생성 결과 execution_scenario와 문서 projection으로 전달됩니다. 방문/소비 두 값을 함께 입력해야 하며 미입력 목표를 자동 생성하지 않습니다(D-100).

자동 보완에는 전체 코드 검수 지적을 전달하며 최종 승인도 전체 검사로 확인합니다(D-099). GPU 미연결 상태의 오프라인 테스트 통과는 실제 LLM 기획 품질 승인과 다릅니다.

후보 재작성 뒤 서버 계약으로도 복구할 수 없는 critical 근거 오류만 본문 작성 전에 종료합니다. 그 밖의 보완 항목은 미승인 검토용 본문과 함께 보존합니다. 과거 차단 기준과 변경 이유는 [검증 기록](../docs/CANDIDATE_GATE_FIX_20260907.md)과 D-112를 참고하세요.

선택 지역의 `data/raw/{시도}/{시군구}` 원본과 공식 보조 근거를 이용해 실행 기획안을 생성합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3
.\backend\.venv\Scripts\python.exe -m uvicorn ai_server.app.main:app --reload --host 127.0.0.1 --port 8112
```

- OpenAI 키는 루트 `.env`에서만 읽고 React에는 전달하지 않습니다.
- 보고서는 `지역 근거 수집 → 공식 성공사례 탐색 → 지역 적합성 평가 → 기획 작성 → 품질 검토` 순서로 생성합니다.
- Agent별 코드와 프롬프트·페르소나 조정 위치는 [`app/agents/README.md`](app/agents/README.md)에 정리합니다.
- 품질검토가 82점 미만이거나 중대 오류가 있으면 기획 작성 Agent가 한 번 수정하고 다시 검토합니다.
- Evidence Agent는 데이터랩 ZIP, 한국관광공사 국문관광정보 Open API, 지역 공식 문서를 구분해 기록합니다.
- Case Scout Agent는 공식 평가·결산·예산·보도자료에서 실행 방식과 관측 성과가 있는 전국 사례를 수집합니다.
- Transferability Agent는 선택 지역의 실제 지표와 사례 조건을 비교해 적용·제외 이유와 시범사업 구조를 만듭니다.
- 보고서는 실제 관측값과 실행 제안을 분리한 JSON으로 반환하며 `quality_review`, `evidence_sources`, `research_gaps`, `agent_trace`를 포함합니다.
- Sol 기반 작성·검수의 단계별 제한시간은 `AI_AGENT_TIMEOUT_SECONDS`로 설정하며 기본값은 300초입니다.
- 기획 Agent는 구조화 기획안과 고추론 토큰을 포함해 최대 16,000 출력 토큰을 허용하며, Reviewer는 승인 기준을 별도로 적용합니다.
- 월간 그래프는 OpenAI가 만든 값이 아니라 원본 ZIP에서 계산한 최근 12개월 순 방문자 수와 외지인 관광소비액을 실제 단위로 반환합니다. 두 지표는 집계 기준이 달라 1인당 소비액으로 단정하지 않습니다.
- `app/raw_data_repository.py`가 ZIP·CSV 파싱 결과를 원본 지문 기준으로 캐시합니다. 원본 파일은 수정하지 않으며 파일이 바뀌면 자동으로 다시 읽습니다.
- 실행 전략은 하나의 3~6개월 기획안으로 작성합니다. 예산의 구체 금액은 근거 자료가 없는 동안 만들지 않고, 산정에 필요한 항목·수량·단가 확보처·계산식만 표시합니다.
- 12개월 강남구 표본이므로 ML 예측이나 정책 효과를 주장하지 않습니다.

공식 문서 RAG 색인:

```powershell
python -m ai_server.index_rag_documents --input data/rag/official_documents.jsonl
python -m ai_server.index_rag_documents --input data/rag/official_case_studies.jsonl
```
