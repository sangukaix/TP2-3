"""관리자 화면의 Agent 계약 설명. 모델 실행 없이 공개 코드 지시문을 읽습니다."""
from .agents import prompts

AGENT_CONTRACTS = {
    'EvidenceAgent': {
        'persona': '선택 지역의 공식 근거를 확인하는 관광사업 조사 담당자',
        'method': 'EvidenceAgent.collect', 'prompt_key': 'EVIDENCE_RESEARCH_INSTRUCTIONS',
        'input': 'region_code + snapshot(공식 관측·ML 전망) + planning_brief(사업 조건)',
        'tools': '서버의 관광 Open API 수집, OfficialTourismRagStore 검색, 허용된 공식 웹 조사. Open API는 관광정보 서비스이며 OpenAI와 다릅니다.',
        'output': '지역 근거·source_id·공식 URL·자료 공백을 묶은 evidence_pack → 후보 비교와 본문 작성',
        'provider': '근거 재사용·서버 수집 + 허용된 경우 OpenAI 공식 웹 조사',
        'config': 'task=evidence / OPENAI_RESEARCH_MODEL / 허용 도메인·출처 검사',
    },
    'CaseStudyAgent': {
        'persona': '다른 지역에서 집행한 사업의 운영 방식·비용·성과 조건을 조사하는 사례 조사관',
        'method': 'CaseStudyAgent.collect', 'prompt_key': 'CASE_STUDY_RESEARCH_INSTRUCTIONS',
        'input': '같은 snapshot + ML research_questions + 지역 비교·사업 조건',
        'tools': '검수 사례 레지스트리·공식 문서 RAG, 모드가 허용한 공식 웹 조사. 검색 요약만으로 성과를 확정하지 않습니다.',
        'output': 'benchmark_cases(운영 방식·적용 조건·출처·성과 범위) → evidence_pack에 결합',
        'provider': '검수 사례 재사용 + 필요한 경우 OpenAI 사례 조사',
        'config': 'task=case_study / OPENAI_CASE_RESEARCH_MODEL / 출처·수치 승인 상태 유지',
    },
    'TransferabilityAgent': {
        'persona': '지역 사실과 사례를 대조해 실행 후보를 비교하는 관광전략 기획자',
        'method': 'TransferabilityAgent.assess', 'prompt_key': 'TRANSFERABILITY_INSTRUCTIONS',
        'input': 'evidence_pack: 지역 관측 + ML + 공식 사례 + 사용자 조건',
        'tools': 'get_region_metrics, compare_regions, get_ml_forecast, get_case_comparison_matrix, read_collected_source 등 요청 안의 읽기 전용 도구',
        'output': 'TRANSFERABILITY_SCHEMA: design_candidates·selected_candidate_id·recommended_case_ids·선정 이유와 적용 조건 → Planner',
        'provider': '로컬 우선: Qwen',
        'config': 'task=transferability / local_evidence_tools=True / OLLAMA_QWEN_MODEL / 후보 계약 검사·필요 시 보완',
    },
    'PlannerAgent': {
        'persona': '선정 후보를 사용자가 이해할 실행 기획안으로 작성하는 담당자',
        'method': 'PlannerAgent.write', 'prompt_key': 'PLANNER_INSTRUCTIONS',
        'input': 'evidence_pack + transfer_assessment / 개정 시 previous_draft + quality_review_feedback',
        'tools': 'get_planning_decision, get_ml_forecast, get_region_metrics, read_collected_source, read_task_section 등. 서버가 필수 근거를 사전 조회합니다.',
        'output': 'report_schema에 맞는 기획안 JSON: 핵심 제안·실행 단계·KPI·출처 → 코드 검사와 Reviewer',
        'provider': '로컬 우선: Gemma',
        'config': 'task=planner 또는 planner_revision / local_evidence_tools=True / OLLAMA_GEMMA_MODEL / 초안과 지적사항을 함께 전달',
    },
    'ReviewerAgent': {
        'persona': '초안을 원래 근거와 비교해 사실·출처·실행 조건을 검토하는 검수자',
        'method': 'ReviewerAgent.review', 'prompt_key': 'REVIEW_INSTRUCTIONS',
        'input': 'evidence_pack + draft_report + deterministic_precheck(코드 검사 결과)',
        'tools': '로컬 검수에는 읽기 전용 근거 도구. final_pass=True의 OpenAI 검수에는 준비된 근거와 초안을 구조화 입력으로 전달합니다.',
        'output': 'REVIEW_SCHEMA: 검수 결과·issues·수정 지시 → 필요 시 Planner 개정·재검수, 통과본 최종 검수',
        'provider': '로컬 우선: Qwen 검수 → 통과본 OpenAI 독립 최종 검수',
        'config': 'task=reviewer / final_pass=True이면 final_reviewer / OPENAI_REVIEW_MODEL / 점수만으로 승인하지 않음',
    },
}


def agent_contract(name):
    guide = AGENT_CONTRACTS.get(name)
    if not guide:
        return {}
    # 전체 결합 프롬프트 대신 역할 선언 첫 문단만 화면에 공개합니다.
    instructions = getattr(prompts, guide['prompt_key']).strip().split('\n\n')[0]
    return {**guide, 'prompt_excerpt': instructions,
            'prompt_file': 'ai_server/app/agents/prompts.py'}
