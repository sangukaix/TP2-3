"""학습용 React 화면에 모델·데이터·함수·평가 결과를 구조화해 제공합니다."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .region_registry import list_region_pipelines


METRIC_GUIDES = {
    'visitors': {
        'title': '향후 3개월 방문자 수 예측',
        'unit': '명',
        'dataset': '순 방문자 수 및 숙박 비율',
        'feature_function': 'make_supervised_frame()',
        'purpose': '과거 방문·소비 흐름과 월별 계절성을 이용해 다음 3개월의 외지인 순 방문자 수를 추정합니다.',
    },
    'spending_krw': {
        'title': '향후 3개월 관광소비액 예측',
        'unit': '원',
        'dataset': '관광소비 추이_외지인',
        'feature_function': 'make_supervised_frame()',
        'purpose': '과거 외지인 관광소비 흐름을 이용해 다음 3개월의 관광소비 총액을 추정합니다.',
    },
    'lodging_nights': {
        'title': '향후 3개월 평균 숙박일수 예측',
        'unit': '일',
        'dataset': '평균 숙박일',
        'feature_function': 'make_lodging_supervised_frame()',
        'purpose': '과거 평균 숙박일수와 계절성을 이용해 다음 3개월의 평균 숙박일수를 추정합니다.',
    },
    'lodging_rate_pct': {
        'title': '향후 3개월 숙박방문자 비율 예측',
        'unit': '%',
        'dataset': '숙박방문자 비율 추이',
        'feature_function': 'make_univariate_supervised_frame()',
        'purpose': '방문자 가운데 숙박으로 이어지는 비율의 다음 3개월 흐름을 추정합니다.',
    },
    'stay_minutes': {
        'title': '향후 3개월 평균 체류시간 예측',
        'unit': '분',
        'dataset': '평균 체류시간 추이',
        'feature_function': 'make_univariate_supervised_frame()',
        'purpose': '지역 안에서 머무르는 평균 시간의 다음 3개월 흐름을 추정합니다.',
    },
    'navigation_searches': {
        'title': '향후 3개월 내비게이션 검색량 예측',
        'unit': '건',
        'dataset': '내비게이션 목적지 유형별 검색량',
        'feature_function': 'make_univariate_supervised_frame()',
        'purpose': '실제 방문 전 단계의 목적지 관심 수요가 다음 3개월 동안 어떻게 움직일지 추정합니다.',
    },
    'lodging_searches': {
        'title': '향후 3개월 숙박 목적지 검색량 예측',
        'unit': '건',
        'dataset': '숙박 목적지 검색건수',
        'feature_function': 'make_univariate_supervised_frame()',
        'purpose': '숙박시설을 찾는 관심 수요의 다음 3개월 흐름을 추정합니다.',
    },
}

MODEL_EXPLANATIONS = {
    'RandomForestRegressor': '여러 결정트리의 예측을 평균내 비선형적인 관광수요 변화를 학습하는 회귀 모델입니다.',
    'LinearRegression': '입력 변수와 목표값 사이의 선형 관계를 학습하는 회귀 모델입니다.',
    'seasonal_naive_previous_year_same_month': '검증 구간에서 후보 모델보다 안정적이어서 작년 같은 달 값을 사용하는 계절 기준모델입니다.',
}


class MlLearningPoint(BaseModel):
    """한 예측월의 모델 결과와 비교용 전년 동월 관측값입니다."""
    month: str
    predicted: float
    previous_year_actual: float | None = None


class MlLearningModule(BaseModel):
    """페이지 카드 한 장에 필요한 학습 정보입니다."""
    id: str
    title: str
    target_name: str
    purpose: str
    unit: str
    data_sources: list[str]
    open_api_usage: str
    model_name: str
    model_explanation: str
    input_features: list[str]
    functions: list[str]
    techniques: list[str]
    forecast: list[MlLearningPoint]
    evaluation: dict[str, Any]
    conclusion: str


class MlLearningRegion(BaseModel):
    """지역 선택 목록과 해당 지역의 전체 ML 결과입니다."""
    region_code: str
    region_name: str
    status: Literal['available', 'unavailable']
    reason: str = ''
    model_version: str = ''
    source_period: str = ''
    observation_count: int = 0
    train_period: str = ''
    validation_period: str = ''
    test_period: str = ''
    modules: list[MlLearningModule] = Field(default_factory=list)


class MlLearningCatalog(BaseModel):
    """등록 지역이 늘어나면 같은 API 응답에 자동으로 추가되는 최상위 스키마입니다."""
    regions: list[MlLearningRegion]


def _format_result(value: float, unit: str) -> str:
    """카드 결론에 들어가는 숫자를 단위에 맞게 짧게 표시합니다."""
    if unit == '원':
        return f'{value / 100_000_000:,.1f}억 원'
    if unit == '명':
        return f'{value:,.0f}명'
    if unit == '일':
        return f'{value:,.2f}일'
    if unit == '%':
        return f'{value:,.2f}%'
    if unit == '분':
        return f'{value:,.0f}분'
    if unit == '건':
        return f'{value:,.0f}건'
    return f'{value:,.2f}'


def _build_module(
    *,
    target_key: str,
    target_name: str,
    model: dict[str, Any],
    prediction: dict[str, Any],
    history: Any,
    load_function_name: str,
) -> MlLearningModule | None:
    """메타데이터의 target이 늘어나면 동일 규칙으로 새 학습 카드를 만듭니다."""
    forecast_rows = prediction.get('forecasts') or []
    if not forecast_rows or any(target_key not in row for row in forecast_rows):
        return None
    guide = METRIC_GUIDES.get(target_key, {
        'title': f'향후 3개월 {target_name} 예측',
        'unit': '',
        'dataset': target_name,
        'feature_function': 'make_supervised_frame()',
        'purpose': f'검증된 과거 자료로 다음 3개월의 {target_name}을 추정합니다.',
    })
    evaluation = (model.get('evaluation') or {}).get(target_key) or {}
    selected = str(evaluation.get('selected_model') or '모델 정보 없음')
    history_by_month = history.set_index('year_month') if target_key in history.columns else None
    points = []
    for row in forecast_rows:
        month = str(row['month'])
        previous_month = f'{int(month[:4]) - 1}{month[4:]}'
        previous = None
        if history_by_month is not None and previous_month in history_by_month.index:
            previous = float(history_by_month.loc[previous_month, target_key])
        points.append(MlLearningPoint(month=month, predicted=float(row[target_key]), previous_year_actual=previous))
    first, last = points[0], points[-1]
    test = evaluation.get('selected_model_metrics') or {}
    baseline = evaluation.get('baseline_metrics') or {}
    functions = [
        f'{load_function_name}()', 'validate_monthly_data()', guide['feature_function'],
        'select_and_evaluate()', 'error_metrics()', 'predict_future_months()',
    ]
    return MlLearningModule(
        id=target_key,
        title=guide['title'],
        target_name=target_name,
        purpose=guide['purpose'],
        unit=guide['unit'],
        data_sources=[
            '한국관광 데이터랩 공식 다운로드 ZIP',
            f"학습 표: {guide['dataset']}",
        ],
        open_api_usage='학습에는 Open API를 사용하지 않습니다. 공식 다운로드 원자료만 사용합니다.',
        model_name=selected,
        model_explanation=MODEL_EXPLANATIONS.get(selected, 'Validation 결과로 선택된 수치 예측 모델입니다.'),
        input_features=list(
            (model.get('feature_names_by_target') or {}).get(target_key)
            or model.get('feature_names')
            or []
        ),
        functions=functions,
        techniques=[
            '지도학습 회귀', '시차 변수(Lag 1·3·12개월)', '월 계절성 sin·cos 변환',
            '시간순 Train·Validation·Test 분리', '전년 동월 기준모델 비교', '1~3개월 재귀 예측',
        ],
        forecast=points,
        evaluation={
            'selection_basis': evaluation.get('selection_basis'),
            'test_mae': test.get('mae'),
            'test_rmse': test.get('rmse'),
            'test_mape_percent': test.get('mape_percent'),
            'baseline_test_mape_percent': baseline.get('mape_percent'),
            'beats_baseline_on_test': evaluation.get('beats_baseline_on_test'),
            'test_sample_count': test.get('sample_count'),
        },
        conclusion=(
            f'{first.month[:4]}년 {int(first.month[4:])}월 {_format_result(first.predicted, guide["unit"])}에서 '
            f'{last.month[:4]}년 {int(last.month[4:])}월 {_format_result(last.predicted, guide["unit"])}으로 예측했습니다. '
            '이는 기존 이력의 자연 추세이며 정책 효과 예측은 아닙니다.'
        ),
    )


def build_ml_learning_catalog() -> MlLearningCatalog:
    """등록표를 순회하므로 지역·target 추가 시 화면 코드를 수정하지 않아도 됩니다."""
    regions = []
    for pipeline in list_region_pipelines():
        try:
            if pipeline.load_history is None:
                raise ValueError('학습 이력 함수가 등록되지 않았습니다.')
            history = pipeline.load_history()
            prediction = pipeline.predict(3)
            model = prediction['model']
            modules = [
                module
                for key, name in (model.get('target') or {}).items()
                if (module := _build_module(
                    target_key=key, target_name=name, model=model, prediction=prediction,
                    history=history, load_function_name=pipeline.load_history.__name__,
                )) is not None
            ]
            regions.append(MlLearningRegion(
                region_code=pipeline.region_code, region_name=pipeline.region_name, status='available',
                model_version=str(model.get('version') or ''), source_period=str(model.get('source_period') or ''),
                observation_count=int(model.get('observation_count') or len(history)),
                train_period=str(model.get('train_target_period') or ''),
                validation_period=str(model.get('validation_period') or ''),
                test_period=str(model.get('test_period') or ''),
                modules=modules,
            ))
        except (OSError, ValueError, KeyError, TypeError, EOFError):
            regions.append(MlLearningRegion(
                region_code=pipeline.region_code, region_name=pipeline.region_name,
                status='unavailable', reason='모델 또는 학습 원자료를 확인할 수 없습니다.',
            ))
    return MlLearningCatalog(regions=regions)
