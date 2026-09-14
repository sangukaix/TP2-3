from pathlib import Path

p = Path(__file__).with_name('build.mjs')
s = p.read_text(encoding='utf-8')
changes = {
    'ai_server/app/decision_facts.py': 'ai_server/app/agents/decision_facts.py',
    'ai_server/app/planning_requirements.py': 'ai_server/app/agents/planning_requirements.py',
    'ai_server/app/context_tables.py': 'ai_server/app/llm/context_tables.py',
    'ai_server/app/report_chat.py': 'ai_server/app/agents/chat_assistant_agent.py',
    'docs/API.md': 'docs/API_DRAFT.md',
    "'지역 관광사업\\n기획서 생성 웹서비스',56,295,475,140,38": "'지역 관광사업\\n기획서 생성\\n웹서비스',56,285,420,178,35",
    "'공식 데이터와 사례를 연결하는\\n지자체 관광 기획 지원',56,476,410,80,25": "'공식 데이터와 사례 기반\\n지자체 관광 기획 지원',56,490,368,90,23",
    "['01 지역 선택','지역 현황·자료 준비 확인']": "['01 지역 선택','지역 현황\\n자료 준비 확인']",
    "['02 조건 입력','사업 방향·참고 예산·시작 월']": "['02 조건 입력','사업 방향·예산\\n시작 월']",
    "['03 생성·검토','공식 사례 비교와 기획 작성']": "['03 생성·검토','공식 사례 비교\\n기획안 작성']",
    "['04 수정·출력','챗봇 조정·저장·PPTX / DOCX']": "['04 수정·출력','챗봇 조정·저장\\nPPTX / DOCX']",
    "'지역 선택·분석·기획·문서 화면'": "'지역 선택·분석\\n기획·문서 화면'",
    "'FastAPI · 지도 경계 조회와 캐시'": "'FastAPI\\n지도 경계 조회·캐시'",
    "'FastAPI · 관광 데이터와 생성 작업'": "'FastAPI\\n관광 데이터·생성 작업'",
    "'공식 문서 · Qwen · Gemma · OpenAI'": "'공식 문서 · Qwen · Gemma\\nOpenAI API'",
    "866,487,358,106": "866,480,358,121",
    "'fact_tourism_metric_source\\ndata_source'": "'지표별 원자료 연결\\ndata_source'",
    "'strategy_report_jobs\\nmeasurement_baseline / followup'": "'strategy_report_jobs\\n사업 전후 측정 테이블'",
    "['수치·신호 묶음','build_planning_ml_evidence']": "['수치·신호 묶음','planning_evidence.py']",
    "'월별 예측값·단위·기간\\nget_ml_forecast로 원수치 제공'": "'월별 예측값·단위·기간\\nget_ml_forecast로 조회'",
    "'기간 합계·평균과 전년 비교\\n모델 평가와 신뢰도 함께 전달'": "'기간 합계·평균과 전년 비교\\n모델 평가·신뢰도 전달'",
    "'모드·캐시·호출 예산에 따라 실행'": "'모드·캐시·예산에 따라 실행'",
    "'선택 지역의 관측·자원·공식 근거'": "'선택 지역의 관측·자원\\n공식 근거'",
    "'타지역의 운영 방식·출처·성과 조건'": "'타지역의 운영 방식\\n출처·성과 조건'",
    "'evidence_pack으로 결합해 후보 비교와 본문 작성에 전달'": "'근거 묶음으로 결합\\n후보 비교·본문 작성에 전달'",
    "'수치·ID·페이지 전달 회귀 검사'": "'수치·ID·페이지 전달 검사'",
    "'이용 절차·사례 연결·내용의 반복성'": "'이용 절차·사례 연결\\n내용의 반복성'",
    "'동일 기간 오차·재귀 전망 안정성'": "'동일 기간 오차\\n재귀 전망 안정성'",
    "'유용성·수정량·업무 시간·실제 성과'": "'유용성·수정량·업무 시간\\n실제 성과'",
    "minimumScale:0,maximumScale:5": "min:0,max:5,majorUnit:1",
}
for a,b in changes.items():
    if a not in s:
        print('NOT FOUND',a)
    s = s.replace(a,b)
# Expand selected diagram containers to preserve a comfortable bottom margin.
s = s.replace("x+18,y+56,w-36,h-63,21,C.muted", "x+18,y+54,w-36,h-59,20,C.muted")
p.write_text(s,encoding='utf-8')
