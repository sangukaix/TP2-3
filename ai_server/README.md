# AI Server

선택 지역의 `data/raw/{시도}/{시군구}` 원본과 공식 보조 근거를 이용해 실행 기획안을 생성합니다.

```powershell
cd C:\Users\Admin\mbca\TP2-3
.\backend\.venv\Scripts\python.exe -m uvicorn ai_server.app.main:app --reload --host 127.0.0.1 --port 8111
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
