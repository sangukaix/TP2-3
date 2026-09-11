"""관리자 학습 화면용 코드 경로 설명. 예측·LLM 실행에는 관여하지 않습니다."""

GUIDES = {
    'visitors': ('방문 규모', '합계', '방문·내비게이션 검색',
        '검색 관심과 방문 전망을 함께 보고 방문으로 연결하는 운영 사례를 조사합니다. 방문 감소만으로 환급사업을 자동 선택하지 않습니다.',
        '검색은 늘고 방문 전망은 약하다는 조건이라면, 이동·예약·현장 이용 연결을 개선한 사례의 운영 방법을 비교할 수 있습니다.'),
    'spending_krw': ('소비 규모', '합계', '소비·계절 조건',
        '소비 전망을 쿠폰·환급·숙박 연계 사례 조사에 전달합니다. 관광소비 총액은 사업자 순이익이나 환급사업의 추가 매출이 아닙니다.',
        '방문 규모에 비해 소비 흐름이 약하다는 조건이라면, 지역 가맹점 이용과 재소비를 유도하는 사례를 검토할 수 있습니다.'),
    'lodging_nights': ('숙박의 길이', '월별 값의 산술평균', '숙박·체류',
        '숙박 비율·숙박검색과 함께 전달해 숙박을 하는 사람의 체류 연장 방안을 조사합니다. 숙박일수가 곧 숙박 방문자 비율은 아닙니다.',
        '숙박 전환은 있지만 숙박일수 전망이 짧다는 조건이라면, 다음 날 체험·연박 콘텐츠를 운영한 사례를 비교할 수 있습니다.'),
    'lodging_rate_pct': ('숙박 전환 비중', '월별 값의 산술평균', '숙박·체류',
        '방문 가운데 숙박으로 이어지는 비중의 전망을 숙박검색·숙박일수와 함께 조사에 사용합니다. 기간 집계는 월별 비율의 단순 평균이며 방문자 수로 가중한 전체 숙박률이 아닙니다.',
        '숙박 관심은 있으나 숙박 비율 전망이 낮다는 조건이라면, 예약·숙박 연계 혜택의 대상과 이용 절차를 조사할 수 있습니다.'),
    'stay_minutes': ('지역 내 체류 시간', '월별 값의 산술평균', '숙박·체류',
        '지역에 머무는 시간 전망을 숙박 지표와 함께 전달합니다. 체류시간이 짧다는 것만으로 야간 콘텐츠 부족을 입증하지 않습니다.',
        '체류시간 전망이 약하다는 조건이라면, 지역 장소 자료를 대조해 여러 거점을 연결하는 체험·야간 프로그램의 운영 조건을 비교할 수 있습니다.'),
    'navigation_searches': ('목적지 관심', '합계', '방문·내비게이션 검색',
        '방문 전망과 함께 관심을 실제 이용으로 연결한 사례를 조사합니다. 검색 건수는 방문 인원이나 실제 전환율이 아닙니다.',
        '검색 관심이 유지되는 조건이라면, 안내·교통·쿠폰 연결 사례를 조사할 수 있습니다. 검색 대비 방문 비율을 실제 전환율로 계산하지 않습니다.'),
    'lodging_searches': ('숙박 목적지 관심', '합계', '숙박·체류',
        '숙박 방문 비율·숙박일수·체류시간과 함께 숙박 전환 사례 조사에 사용합니다. 숙박 목적지 검색은 예약 완료 건수가 아닙니다.',
        '숙박검색 전망과 숙박 비율 전망이 엇갈리는 조건이라면, 예약 접근성과 숙박 연계 프로그램 사례를 비교할 수 있습니다.'),
}


def build_module_usage(key: str) -> dict:
    if key not in GUIDES:
        return {}
    role, aggregation, group, interpretation, example = GUIDES[key]
    direct = key in {'visitors', 'spending_krw'}
    feature = 'make_supervised_frame → _feature_row' if direct else 'make_univariate_supervised_frame → _univariate_feature_row'
    candidate = 'RandomForestRegressor' if key in {'visitors', 'navigation_searches', 'lodging_searches'} else 'LinearRegression'
    display = ('PPT 사업 설계 차트·목표 KPI 표 / Word ML 자연추세와 사업 목표. report_projection.select_report_forecast가 최종 사업 기간의 저장 행을 선택합니다.'
               if direct else '이 관리자 화면의 개별 예측 차트와 보고서 ml_analysis에 보존됩니다. 최종 PPT의 방문·소비 전망 그래프에는 직접 그리지 않으며, 본문 반영은 선택된 사업과 LLM 작성 결과에 따라 달라집니다.')
    return {
        'role': role, 'aggregation': aggregation, 'research_group': group,
        'interpretation': interpretation, 'example': example, 'display': display,
        'steps': [
            {'title': '원자료 → 월별 학습 표', 'file': 'ai_server/ml/standard_region_pipeline.py',
             'function': 'build_standard_pipeline_functions → load_history',
             'detail': '표준 등록 지역은 regional_datalab_data.load_standard_datalab_monthly_demand로 공식 CSV/ZIP을 읽습니다. region_registry가 지역별 어댑터를 선택하고 validation.validate_monthly_data가 지역코드·연속월·값을 확인합니다. 강남 등 전용 어댑터도 같은 예측 계약에 연결됩니다.',
             'output': f'월별 DataFrame: region_code + year_month + {key}'},
            {'title': '관리 CLI에서 모델 학습·선택', 'file': 'ai_server/ml/gangnam_forecast.py',
             'function': f'train_region_models → _training_frame → {feature}',
             'detail': ('방문·소비 각각 1·3·12개월 시차와 예측월 sin/cos를 함께 입력합니다. ' if direct else '해당 지표 자체의 1·3·12개월 시차와 예측월 sin/cos만 입력합니다. ') +
                       f'후보는 {candidate}입니다. evaluation.select_and_evaluate가 Validation 3개월 MAE로 전년 동월 기준선과 비교하고 마지막 Test 4개월은 평가에만 씁니다. 후보가 선택되면 전체 관측 이력으로 최종 모델을 fit하고, 기준선 선택 시 별도 회귀모델을 저장하지 않습니다. 웹 생성마다 재학습하지 않습니다.',
             'output': '지역별 demand_model.joblib + demand_model.metadata.json (선택 모델·Feature·기간·오차·데이터 hash)'},
            {'title': '기획 요청 → 저장 모델 추론', 'file': 'ai_server/app/agents/report_orchestrator.py',
             'function': 'orchestrate_strategy_report → build_planning_ml_evidence',
             'detail': 'planning_evidence.py가 get_region_pipeline으로 지역을 찾고 horizon_policy.resolve_planning_horizon으로 필요한 월 수를 정합니다. pipeline.predict → gangnam_forecast.predict_region_future_months → _load_region_artifact → _recursive_forecasts 순서로 실행합니다. 모델이 선택되지 않은 Target은 전년 동월 값을 사용합니다. 앞 달 예측은 다음 달 입력 이력에 추가합니다.',
             'output': f'snapshot.ml_analysis.forecasts[].{key} (관리자 차트는 pipeline.predict(3); 기획은 사업 일정 기준)'},
            {'title': '예측 숫자 → 비교 가능한 진단 신호', 'file': 'ai_server/ml/planning_evidence.py',
             'function': 'build_planning_ml_evidence → _change_percent / _compact_evaluation',
             'detail': f'사업 기간의 {aggregation}를 전년 같은 기간과 비교합니다. 증감률=(전망÷전년값−1)×100이며 전년값 0은 null입니다. source_id·기간·단위·모델 신뢰도를 함께 붙입니다. 숙박 비율 변화의 %는 상대 증감률이며 %p 차이가 아닙니다. decision_facts.build_decision_facts가 집계 신호를 forecast_windows로 복사합니다.',
             'output': f'signals[metric={key}] → snapshot.decision_facts.forecast_windows; research_questions의 「{group}」 조사 묶음'},
            {'title': '조사 질문 → 공식 사례 확보', 'file': 'ai_server/app/agents/case_study_agent.py',
             'function': 'CaseStudyAgent.collect / EvidenceAgent.collect',
             'detail': 'CaseStudyAgent는 research_questions를 RAG 검색어에 넣고 공식 사례 후보를 찾습니다. 허용된 웹 조사 경로에서는 ml_analysis와 조사 질문을 구조화 입력으로 전달합니다. EvidenceAgent는 지역 자료와 ML 출처를 연결합니다. 질문은 세 묶음의 코드 템플릿이며 수치 부호가 자동으로 특정 사업명을 결정하지 않습니다. 실제 웹 호출·근거 재사용은 모드와 캐시에 따라 달라집니다.',
             'output': 'evidence_pack.snapshot + benchmark_cases + source_id/공식 URL/운영 방식/적용 조건'},
            {'title': 'Qwen 비교 → Gemma 본문 → 검수', 'file': 'ai_server/app/llm/local_agent.py',
             'function': '_prefetch_required_evidence → EvidenceTools._forecast → evidence_json',
             'detail': '로컬 우선 경로에서 서버가 get_ml_forecast를 먼저 실행합니다. evidence_tools.py는 월별 수치·평가·주의사항을 반환하고 signals/research_questions는 별도 조회 경로를 남깁니다. local_agent는 도구 결과를 JSON/무손실 표의 user 메시지로 넣습니다. Qwen TransferabilityAgent.assess가 관측·사례와 함께 후보를 비교하고, Gemma PlannerAgent.write가 선택 판단과 같은 ML 근거로 실행안을 씁니다. 코드·모델 검수가 뒤따르며 실제 공급자는 Router/agent_trace로 확인합니다.',
             'output': 'planning_decision.design_candidates / selected_candidate_id → strategies의 제안·실행 단계·KPI'},
            {'title': '저장 보고서 → 화면·문서', 'file': 'ai_server/app/report_projection.py' if direct else 'ai_server/app/agents/report_orchestrator.py',
             'function': 'select_report_forecast' if direct else 'orchestrate_strategy_report (ml_analysis 반환)',
             'detail': display + (' 목표선은 idea_proposal의 기획 목표와 target_series 등의 산식으로 따로 계산합니다. ML이 사업 효과를 학습한 결과가 아닙니다.' if direct else ''),
             'output': f'report.ml_analysis.forecasts[].{key}; 원래 관측값·예측값·계획 목표를 구분'},
        ],
        'tree': f'''공식 지역 월별 표 [{key}]
├─ 오프라인: train_region_models → 시간순 평가 → Joblib/metadata
├─ 관리자: build_ml_learning_catalog → pipeline.predict(3) → 이 카드
└─ 기획: orchestrate_strategy_report
   └─ build_planning_ml_evidence → pipeline.predict(사업 기간)
      ├─ forecasts[].{key} → get_ml_forecast → Qwen / Gemma
      ├─ signals ({aggregation}) → decision_facts.forecast_windows
      ├─ research_questions ({group}) → RAG / 허용된 공식 웹 조사
      └─ 사례 + 관측 + ML → 후보 비교 → 본문 → 검수 → 저장/출력''',
        'limit': '입력 전달 경로를 설명한 것이며, LLM 내부에서 이 지표가 답변에 기여한 비중을 측정한 결과는 아닙니다. 개별 보고서의 실제 사용은 저장 ml_analysis·planning_decision·인용 출처·agent_trace와 본문을 대조해야 합니다. 해석 예시는 현재 지역의 관측 사실이나 자동 선택 규칙이 아닙니다.',
    }
