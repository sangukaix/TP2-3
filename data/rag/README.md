# 공식 사례·문서 RAG 저장소

- `official_case_studies.jsonl`: 사람이 원문을 확인한 비교 사례 카드
- `../chroma/`: 긴 공식 문서를 Chunk로 검색하는 영속 ChromaDB
- 월별 방문·소비 수치는 이 폴더에 넣지 않는다.
- 사례 추가 뒤 `python -m ai_server.app.scripts.check_case_registry`를 실행한다.
- URL, 게시일, 측정기간, 예산, 관측결과, 적용 조건, 위험을 확인할 수 없는 사례는 등록하지 않는다.
- 라이브 웹 검색 결과는 자동 영구등록하지 않는다. 사람이 원문을 검수한 뒤 JSONL에 추가한다.
