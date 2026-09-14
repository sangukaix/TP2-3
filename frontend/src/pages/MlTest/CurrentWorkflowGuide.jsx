const guides = {
  openai: [
    ['근거 준비', 'MySQL 관측·전국 비교 + 로컬 원본의 소비 구성·관광 현황을 조회합니다. 저장 모델의 7개 전망과 출처를 별도 필드로 전달합니다.', 'app/main.py → ml/planning_evidence.py'],
    ['사례와 후보 비교', 'Evidence·CaseStudy가 근거를 준비하고 Qwen이 운영 조건과 후보 차이를 비교합니다. 지역 비교는 코드 계산이며 사업 성공을 학습한 추천 모델은 아닙니다.', 'agents/report_orchestrator.py → case_scope.py'],
    ['작성과 검수', 'Gemma가 본문을 작성하고 코드·로컬 검수를 거칩니다. 학생 절약 모드는 로컬 검수 통과본에만 OpenAI 독립 최종 검수 1회를 허용합니다.', 'llm/local_prompts.py → llm/router.py'],
    ['저장과 출력', '기획 JSON을 MySQL에 저장하고 같은 전망·목표를 Word와 PPT에 사용합니다. 목표 KPI는 사업 효과 예측과 구분한 계획값입니다.', 'strategy_store.py → report_projection.py'],
  ],
  react: [
    ['지역 선택', '서버 카탈로그에서 지역 목록을 받습니다. 자료 점검과 현재 로컬 모델 연결을 함께 통과한 지역에 준비 상태를 표시합니다.', 'tourismWorkspace.js → /ai/v1/regions/catalog'],
    ['조건 입력', '사업 방향·참고 예산·자원·현장 선호를 선택합니다. 서버가 한국 시간 기준 다음 달부터 3개월의 사업기간을 확정합니다.', 'TourismPlanningPage.jsx → planning_brief.py'],
    ['진행 상태', '생성 작업 ID를 받은 뒤 상태를 조회합니다. 분석·사례·작성·검수 진행은 서버가 보고한 단계로 표시합니다.', 'dashboardApi.js → strategy-report/jobs'],
    ['수정과 다운로드', '화면은 구조화된 응답을 표시합니다. 챗봇 수정과 저장을 거쳐 서버에서 Word·PPT를 생성하며 React에서 ML을 학습하지 않습니다.', 'TourismStrategyPage.jsx → strategy_store.py'],
  ],
  router: [
    ['모드와 작업', '같은 Agent라도 모드와 작업 종류에 따라 Provider가 달라집니다. 저장 설정과 실제 적용 경로를 아래 표에서 함께 확인합니다.', 'llm/router.py · effective_routes()'],
    ['로컬 모델', 'Qwen은 비교·질문 설계·로컬 검수, Gemma는 본문 작성·개정을 맡습니다. 연결 확인과 실제 추론 완료는 다릅니다.', 'llm/ollama_provider.py'],
    ['유료 호출 경계', '학생 절약 모드는 저장 근거·선택적 무료 공식 검색을 우선합니다. 로컬 실패를 이유로 OpenAI에 자동 대체하지 않습니다.', 'llm/router.py · cost_policy'],
    ['실행 기록', '실제로 끝난 시도의 Provider·모델·오류·사용량을 확인합니다. 설정 저장은 모델 학습이나 기획서 생성을 실행하지 않습니다.', 'llm/trace_store.py'],
  ],
}

export default function CurrentWorkflowGuide({ topic }) {
  return <section className="current-workflow-guide" aria-label="현재 구현된 데이터와 생성 흐름">
    <header><span>현재 구현</span><h2>{topic === 'router' ? '설정에서 실제 실행까지' : topic === 'react' ? '사용자 화면에서 기획서까지' : '데이터가 기획으로 이어지는 과정'}</h2><p>사전 준비와 사용자 요청 처리를 구분해 읽어보세요.</p></header>
    <ol>{guides[topic].map(([title, description, file], index) => <li key={title}><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{title}</h3><p>{description}</p><code>{file}</code></div></li>)}</ol>
    <details><summary>데이터 준비·재사용과 아직 개발하지 않은 기능</summary><p><b>사전 준비</b> — 로컬 ZIP → 검증된 CSV·MySQL → 지역별 7개 모델 학습·저장. 공유폴더는 생성 시 조회하지 않습니다.</p><p><b>생성 요청</b> — 저장 모델로 예측을 계산합니다. 원본 읽기·근거 조사 캐시는 조건이 맞을 때 재사용하며, 새 생성 요청은 본문을 다시 작성합니다.</p><p><b>개발 제안</b> — 여러 지역을 함께 학습하는 공통 모델, 발전 기회 점수, 월별 운영 추천은 아직 구현·검증된 기능이 아닙니다. 통계 지역 확대가 사례 문서 확대나 예측 정확도 향상을 자동으로 의미하지 않습니다.</p></details>
  </section>
}
