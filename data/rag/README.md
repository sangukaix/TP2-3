# 공식 사례·문서 RAG 저장소

- `official_case_studies.jsonl`: 사람이 원문을 확인한 비교 사례 카드
- `official_reference_documents.jsonl`: 공식 PDF의 정책·운영·지표 해석 요약. Chroma 색인 전에도 무료 키워드 검색으로 조회된다.
- `official_reference_chunks.jsonl`: 사용자가 제공한 공식 PDF에서 **사전 검수한 쪽수만** 문단 단위로 나눈 로컬 RAG 청크. PDF 원문과 SHA-256·쪽수·공식 URL을 함께 보존하며, `local_first`에서는 무료 키워드 검색으로 즉시 활용한다. 제공 원문에서 재생성되는 파일이므로 Git에는 올리지 않는다.
- `source_documents/`: 사용자가 제공한 공식 PDF의 변경하지 않은 로컬 사본. SHA-256과 공식 URL은 레지스트리에 기록하고, 대용량 원문은 Git에 올리지 않는다.
- `../chroma/`: 긴 공식 문서를 Chunk로 검색하는 영속 ChromaDB
- 월별 방문·소비 수치는 이 폴더에 넣지 않는다.
- 사례 추가 뒤 `python -m ai_server.app.scripts.check_case_registry`를 실행한다.
- URL, 게시일, 측정기간, 예산, 관측결과, 적용 조건, 위험을 확인할 수 없는 사례는 등록하지 않는다.
- 라이브 웹 검색 결과는 자동 영구등록하지 않는다. 사람이 원문을 검수한 뒤 JSONL에 추가한다.
- 월별 숫자·향후 공개 예정 화면·가상 예시는 RAG 근거로 사용하지 않는다.
- 청크 재생성: `python -m ai_server.app.scripts.build_official_pdf_rag` / Chroma 의미검색 색인(선택): `python ai_server/index_rag_documents.py`. 후자는 한 번만 임베딩 API를 호출하고, 이후 검색은 영속 저장소를 재사용한다.
- 2026-09-07 추출 점검: `2026_요즘_한국관광_2호_지방공항.pdf` 34~44쪽은 텍스트 청크로 준비됐다. `2026_요즘_한국관광_데이터세미나_2차.pdf` 75~99쪽은 다수가 이미지/특수 폰트여서 자동 추출되지 않았다. 화면으로 검수한 76쪽의 **지표 정의 요약**과 텍스트 추출된 89쪽만 등록했으며, 나머지 페이지가 색인됐다고 주장하지 않는다. `--audit-only`로 누락 쪽수를 다시 확인한다.
