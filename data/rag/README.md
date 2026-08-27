# 공식 문서 RAG 입력

이 폴더에는 월별 방문자·소비 수치표를 넣지 않습니다. 지자체·한국관광공사·문화체육관광부 등 공식 기관이 공개한 정책, 사업, 관광자원, 행사, 교통·인프라 문서만 검수한 뒤 등록합니다.

official_documents.jsonl의 한 줄 형식:

    {"source_id":"안정적인-문서-ID","region_code":"11680","region_name":"서울특별시 강남구","document_type":"policy","title":"공식 문서 제목","source_url":"https://공식기관도메인/문서주소","published_or_updated_at":"2026-08-01","content":"문서 본문"}

- 공통 문서는 region_code와 region_name을 ALL로 지정합니다.
- source_url은 .env의 TOURISM_ALLOWED_RESEARCH_DOMAINS에 등록한 공식 도메인이어야 합니다.
- 문서 안의 지시문은 실행하지 않으며, 사실 근거로만 사용합니다.
- 원본 문서의 이용 조건과 갱신일을 먼저 확인합니다.

색인 명령:

    python -m ai_server.index_rag_documents --input data/rag/official_documents.jsonl
