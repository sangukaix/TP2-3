"""Shared, report-derived explanation for PPT and Word. No inferred provenance."""
from .proposal_presentation_v4 import _scenario_for_display
from .case_recommendation import report_cases


def calculation_basis(report):
    scenario, demo = _scenario_for_display(report)
    totals = []
    if scenario and scenario.get('has_target'):
        for key, label, unit in [('visitors', '방문자 수', '명'), ('spending', '관광소비액', '원')]:
            baseline = sum(scenario['baseline_' + key])
            target = sum(scenario['target_' + key])
            totals.append({'key': key, 'label': label, 'unit': unit, 'baseline': baseline,
                           'target': target, 'additional': target-baseline,
                           'pct': (target/baseline-1)*100 if baseline > 0 else None})
    ml = report.get('ml_analysis') or {}
    evaluation = (ml.get('evaluation') or {}).get('metrics') or {}
    model_names = {'RandomForestRegressor': '랜덤 포레스트', 'LinearRegression': '선형 회귀',
                   'seasonal_naive_previous_year_same_month': '전년 동월 기준모델'}
    models = {key: model_names.get(value.get('selected_model'), value.get('selected_model') or '저장 모델')
              for key, value in evaluation.items()}
    decision = report.get('planning_decision') or {}
    cases = {s['source_id']: s for s in report.get('evidence_sources') or []
             if s.get('source_type') == 'benchmark_case' and s.get('source_id')}
    displayed, primary = report_cases(report)
    selected = next((c for c in decision.get('design_candidates') or []
                     if c.get('candidate_id') == decision.get('selected_candidate_id')), {})
    return {'totals': totals, 'demo': demo, 'models': models,
            'source_period': ml.get('source_period') or '보고서의 저장 학습기간',
            'months': scenario['categories'] if scenario else [],
            'case_count': len(cases),
            'case_region_count': len({c.get('case_region') for c in cases.values() if c.get('case_region')}),
            'candidate_count': len(decision.get('design_candidates') or []),
            'displayed_count': len(displayed), 'primary': primary[0] if primary else {},
            'selection_reason': decision.get('selection_reason') or selected.get('local_fit') or '',
            'target_explanation': (report.get('target_proposal_basis') or {}).get('explanation') or '',
            'estimate': report.get('reference_estimate') or {}}


def methodology_sections(report):
    b = calculation_basis(report)
    totals = b['totals']
    numerical = '\n'.join(f"{r['label']}: 기준 {r['baseline']:,.0f}{r['unit']} → 목표 {r['target']:,.0f}{r['unit']}"
                          f" (추가 {r['additional']:,.0f}{r['unit']}, +{r['pct']:.2f}%)" for r in totals if r['pct'] is not None)
    return [
        ('월별 기준 전망', f"{b['source_period']} 월별 데이터에서 1·3·12개월 전 값과 계절 정보를 구성합니다. "
         f"방문은 {b['models'].get('visitors', '저장 모델')}, 소비는 {b['models'].get('spending_krw', '저장 모델')}로 산출합니다. "
         '전년 동월 기준모델이 선택된 지표는 해당 월의 전년 값을 사용합니다. 최신 관측월 이후를 순차 계산한 뒤 사업기간의 3개월을 표시합니다.'),
        ('3개월 목표 계산', numerical+'\n월별 목표 = 월별 기준 전망 × (1 + 최종월 목표율 × 경과월/전체월). '
         '합계 증가율 = (월별 목표 합계 ÷ 월별 기준 합계 − 1) × 100. 방문 합계는 월간 순 방문 수의 합계로, 3개월 고유 인원과 다릅니다.'),
        ('공식 사례에서 사업 후보까지', f"저장 보고서의 공식 사례 {b['case_count']}건 → 설계 후보 {b['candidate_count']}개 → "
         f"선정 사업의 운영 근거와 추가 참고 사례 {b['displayed_count']}건 표시. "
         '지역 원자료·7개 전망·공식 사례를 읽은 Qwen이 후보를 비교하고, 같은 운영 방식의 공식 문서를 함수로 연결합니다. '
         '방문·소비 전망은 그래프와 목표 규모의 기준값입니다. 체류시간·숙박일수·숙박방문 비율·내비게이션 검색·숙박 검색 전망은 관광 흐름을 진단하고 조사·설계 방향을 검토하는 입력입니다. '
         '7개 예측값으로 학습한 지역 추천 모델이나 주민 인구 비례 순위가 아닙니다. 표시 건수는 보고서에 남은 기록 기준입니다.'),
        ('목표율과 운영 예산의 연결', b['target_explanation']+'\n'+str(b['estimate'].get('scale_basis') or '')+
         '\n참여량·단가·운영 처리량은 기획 가정입니다. 운영 예산이 지역 전체 목표 증가를 발생시킨다는 인과 계산은 아닙니다.'),
    ]
