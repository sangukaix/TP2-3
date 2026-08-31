"""저장 모델의 숫자를 기획 근거로 바꿉니다. LLM 호출·웹 검색·학습은 하지 않습니다."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from .horizon_policy import resolve_planning_horizon
from .region_registry import get_region_pipeline
from .validation import data_fingerprint, validate_monthly_data


class PlanningForecast(BaseModel):
    """예측과 전년 같은 달 관측값을 별도 필드로 보관해 출처와 의미를 구분합니다."""
    month: str = Field(pattern=r'^\d{6}$')
    visitors: int = Field(ge=0)
    spending_krw: int = Field(ge=0)
    previous_year_visitors: int = Field(ge=0)
    previous_year_spending_krw: int = Field(ge=0)
    visitor_yoy_percent: float | None = None
    spending_yoy_percent: float | None = None
    lodging_nights: float = Field(ge=0)
    previous_year_lodging_nights: float = Field(ge=0)
    lodging_rate_pct: float = Field(ge=0)
    previous_year_lodging_rate_pct: float = Field(ge=0)
    stay_minutes: float = Field(ge=0)
    previous_year_stay_minutes: float = Field(ge=0)
    navigation_searches: int = Field(ge=0)
    previous_year_navigation_searches: int = Field(ge=0)
    lodging_searches: int = Field(ge=0)
    previous_year_lodging_searches: int = Field(ge=0)
    metric_changes_percent: dict[str, float | None] = Field(default_factory=dict)
    is_forecast: Literal[True] = True


class PlanningMlEvidence(BaseModel):
    """API 응답·저장 보고서·5개 Agent가 공유하는 ML 근거 스키마입니다."""
    status: Literal['available', 'unsupported', 'unavailable']
    region_code: str
    region_name: str
    reason_code: str = ''
    source_id: str = ''
    source_period: str = ''
    latest_observed_month: str = ''
    model_version: str = ''
    data_fingerprint: str = ''
    forecast_type: str = 'historical_trend_not_policy_counterfactual'
    # 사용자 일정과 모델 검증 한계를 함께 전달해 Agent가 임의로 기간을 바꾸지 못하게 합니다.
    horizon_policy: dict[str, Any] = Field(default_factory=dict)
    forecasts: list[PlanningForecast] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


def _change_percent(value: float, previous: float) -> float | None:
    """비교값이 0이면 증감률을 정의할 수 없으므로 0% 대신 null을 반환합니다."""
    return round((value / previous - 1) * 100, 2) if previous else None


def _compact_evaluation(model: dict[str, Any], forecast_horizon_months: int) -> dict[str, Any]:
    """Agent에는 모델 선택에 필요한 핵심 MAE만 전달해 입력 토큰과 해석 혼선을 줄입니다."""
    metrics = {}
    recursive = model['recursive_evaluation']['by_horizon']
    for key, result in model['evaluation'].items():
        metrics[key] = {
            'selected_model': result['selected_model'],
            'test_mae': result['selected_model_metrics']['mae'],
            'baseline_test_mae': result['baseline_metrics']['mae'],
            'beats_baseline_on_test': result['beats_baseline_on_test'],
            'recursive_mae': {
                horizon: {
                    'selected': row['selected']['mae'], 'baseline': row['baseline']['mae'],
                    'sample_count': row['selected']['sample_count'],
                }
                for horizon, row in recursive[key].items()
            },
        }
    return {
        'validation_period': model['validation_period'], 'test_period': model['test_period'],
        'selection_basis': 'validation_mae_only',
        'recursive_backtest_horizon_months': [1, 2, 3],
        'forecast_horizon_months': forecast_horizon_months,
        'longer_horizon_status': (
            'not_requested' if forecast_horizon_months <= 3 else 'exploratory_not_recursively_backtested'
        ),
        'metrics': metrics,
    }


def build_planning_ml_evidence(
    region_code: str,
    region_name: str,
    planning_brief: dict[str, Any] | None = None,
) -> PlanningMlEvidence:
    """지역키·데이터 버전·시험 기록이 맞는 모델만 기획안에 넣습니다. 없으면 수치를 만들지 않습니다."""
    identity = {'region_code': str(region_code), 'region_name': region_name}
    try:
        pipeline = get_region_pipeline(region_code)
    except ValueError:
        return PlanningMlEvidence(status='unsupported', reason_code='ML_REGION_UNSUPPORTED', **identity)
    if pipeline.region_name != region_name:
        return PlanningMlEvidence(status='unavailable', reason_code='ML_REGION_MISMATCH', **identity)
    if pipeline.load_history is None:
        return PlanningMlEvidence(status='unavailable', reason_code='ML_HISTORY_UNAVAILABLE', **identity)
    try:
        history = pipeline.load_history()
        validate_monthly_data(history, str(region_code))
        latest_observed_month = str(history['year_month'].iloc[-1])
        horizon_policy = resolve_planning_horizon(planning_brief, latest_observed_month)
        # 온라인 재학습 없이 저장 모델을 필요한 범위까지만 재귀 호출합니다.
        prediction = pipeline.predict(horizon_policy.forecast_horizon_months)
        model = prediction['model']
        # Validation을 따로 쓰지 않은 구형 산출물은 새 기획안의 검증된 ML 근거로 승격하지 않습니다.
        if not model.get('validation_period') or not model.get('recursive_evaluation'):
            return PlanningMlEvidence(status='unavailable', reason_code='ML_RETRAIN_REQUIRED', **identity)
        fingerprint = data_fingerprint(history)
        if model.get('data_fingerprint') != fingerprint or str(model.get('region_code')) != str(region_code):
            return PlanningMlEvidence(status='unavailable', reason_code='ML_MODEL_STALE', **identity)
        actuals = history.set_index('year_month')
        forecasts = []
        for row in prediction['forecasts']:
            month = row['month']
            previous_year = f'{int(month[:4]) - 1}{month[4:]}'
            previous = actuals.loc[previous_year]
            forecasts.append(PlanningForecast(
                month=month, visitors=row['visitors'], spending_krw=row['spending_krw'],
                previous_year_visitors=int(previous['visitors']),
                previous_year_spending_krw=int(previous['spending_krw']),
                visitor_yoy_percent=_change_percent(row['visitors'], float(previous['visitors'])),
                spending_yoy_percent=_change_percent(row['spending_krw'], float(previous['spending_krw'])),
                lodging_nights=row['lodging_nights'],
                previous_year_lodging_nights=float(previous['lodging_nights']),
                lodging_rate_pct=row['lodging_rate_pct'],
                previous_year_lodging_rate_pct=float(previous['lodging_rate_pct']),
                stay_minutes=row['stay_minutes'],
                previous_year_stay_minutes=float(previous['stay_minutes']),
                navigation_searches=row['navigation_searches'],
                previous_year_navigation_searches=int(previous['navigation_searches']),
                lodging_searches=row['lodging_searches'],
                previous_year_lodging_searches=int(previous['lodging_searches']),
                metric_changes_percent={
                    key: _change_percent(float(row[key]), float(previous[key]))
                    for key in (
                        'lodging_nights', 'lodging_rate_pct', 'stay_minutes',
                        'navigation_searches', 'lodging_searches',
                    )
                },
            ))
        if len(forecasts) != horizon_policy.forecast_horizon_months:
            raise ValueError('ML_FORECAST_LENGTH')
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        # 실패할 때 경로·내부 예외를 사용자나 프롬프트에 흘리지 않고 관측 자료만으로 계속 진행합니다.
        return PlanningMlEvidence(status='unavailable', reason_code='ML_DATA_OR_MODEL_UNAVAILABLE', **identity)

    source_id = f"ml:{region_code}:{model['version']}:{prediction['latest_observed_month']}"
    period = f'{forecasts[0].month}~{forecasts[-1].month}'
    signals, questions = [], []
    # 일정 미정은 3·6개월을 각각 비교하고, 날짜 입력은 실제 겹치는 월만 집계합니다.
    for window in horizon_policy.decision_windows:
        window_rows = forecasts[window.forecast_start_index:window.forecast_end_index + 1]
        window_period = f'{window.start_month}~{window.end_month}'
        for metric, prior_key, label, unit in (
            ('visitors', 'previous_year_visitors', '방문자 수', '명'),
            ('spending_krw', 'previous_year_spending_krw', '관광소비액', '원'),
            ('lodging_nights', 'previous_year_lodging_nights', '평균 숙박일수', '일'),
            ('lodging_rate_pct', 'previous_year_lodging_rate_pct', '숙박방문자 비율', '%'),
            ('stay_minutes', 'previous_year_stay_minutes', '평균 체류시간', '분'),
            ('navigation_searches', 'previous_year_navigation_searches', '내비게이션 검색량', '건'),
            ('lodging_searches', 'previous_year_lodging_searches', '숙박 목적지 검색량', '건'),
        ):
            use_sum = metric in {'visitors', 'spending_krw', 'navigation_searches', 'lodging_searches'}
            divisor = 1 if use_sum else len(window_rows)
            forecast_value = sum(getattr(row, metric) for row in window_rows) / divisor
            previous_value = sum(getattr(row, prior_key) for row in window_rows) / divisor
            change = _change_percent(forecast_value, previous_value)
            direction = '감소' if change is not None and change < 0 else '증가' if change else '유지'
            signals.append({
                'kind': 'forecast_signal', 'window_label': window.label,
                'window_months': window.months, 'reliability': window.reliability,
                'metric': metric, 'period': window_period,
                'aggregation': f'{window.months}_month_sum' if use_sum else f'{window.months}_month_average',
                'forecast_value': forecast_value, 'previous_year_same_months_value': previous_value,
                'change_percent': change, 'unit': unit, 'source_id': source_id,
                'interpretation': f'{window.label}에서 {label}의 전년 동기간 대비 {direction} 추세 예측입니다. 원인 또는 사업 효과를 뜻하지 않습니다.',
            })
    # 지표 7개를 그대로 반복 검색하지 않고, 실제 의사결정 구간을 한 문장에 묶어 조사합니다.
    decision_periods = ', '.join(
        f'{window.label}({window.start_month}~{window.end_month})'
        for window in horizon_policy.decision_windows
    ) or period
    questions.extend([
        f'{region_name}의 {decision_periods} 방문자 수와 내비게이션 검색량 전망을 비교해 관심을 실제 방문으로 연결한 공식 사업의 운영방법·예산·성과·실패조건을 조사하세요.',
        f'{region_name}의 {decision_periods} 숙박검색·숙박방문 비율·평균 숙박일·체류시간 전망을 함께 보고 숙박 전환과 장시간 체류를 높인 공식 사업을 조사하세요.',
        f'{region_name}의 {decision_periods} 관광소비액 전망과 계절 조건이 비슷한 지역의 쿠폰·환급·숙박 연계 사업을 공식 성과자료 중심으로 조사하세요.',
    ])
    return PlanningMlEvidence(
        status='available', **identity, source_id=source_id,
        source_period=model['source_period'], latest_observed_month=prediction['latest_observed_month'],
        model_version=model['version'], data_fingerprint=model['data_fingerprint'],
        horizon_policy=horizon_policy.model_payload(),
        forecasts=forecasts, signals=signals, research_questions=questions,
        evaluation=_compact_evaluation(model, horizon_policy.forecast_horizon_months),
        cautions=[
            '관측 사실·ML 전망·사업 목표를 분리합니다. 전망은 정책 미실행 결과나 인과효과가 아닙니다.',
            '시험 표본이 적습니다. 지표·horizon별 기준선 대비 오차를 확인하고 우수성을 일반화하지 않습니다.',
            '관광소비액은 지역 사업자의 순이익이 아닙니다. 방문자와 소비 표본이 같다는 확인 없이 1인당 소비를 계산하지 않습니다.',
            '업종별 비중 변화·SNS 언급량·쿠폰 지급 효과·사업의 추가 매출은 이 모델이 학습한 대상이 아닙니다.',
            '내비게이션·숙박 검색량은 관심 신호이며 실제 방문·예약 건수로 해석하지 않습니다.',
            *horizon_policy.notes,
        ],
    )
