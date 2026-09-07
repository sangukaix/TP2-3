"""기획 일정에 맞춰 ML 전망 범위를 결정하는 정책 모듈입니다.

모델 자체와 기간 선택 규칙을 분리해, 지역 모델이 늘어나도 같은 기준을 재사용합니다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal


MIN_MODEL_HORIZON_MONTHS = 3
MAX_PLANNING_HORIZON_MONTHS = 12
VALIDATED_RECURSIVE_HORIZON_MONTHS = 3


def _month_index(year_month: str) -> int:
    """YYYYMM을 월 간격 계산이 가능한 정수로 바꿉니다."""
    return int(year_month[:4]) * 12 + int(year_month[4:]) - 1


def _month_from_index(index: int) -> str:
    """월 정수를 다시 YYYYMM으로 복원합니다."""
    year, zero_based_month = divmod(index, 12)
    return f'{year}{zero_based_month + 1:02d}'


def _date_month(value: date | str | None) -> str | None:
    """Pydantic date와 JSON 날짜 문자열을 같은 YYYYMM 키로 정규화합니다."""
    if value is None:
        return None
    if isinstance(value, date):
        return f'{value.year}{value.month:02d}'
    compact = str(value).strip().replace('-', '')
    return compact[:6] if len(compact) >= 6 and compact[:6].isdigit() else None


@dataclass(frozen=True)
class ForecastDecisionWindow:
    """기획자가 실제로 비교할 전망 구간 한 개입니다."""

    label: str
    start_month: str
    end_month: str
    months: int
    forecast_start_index: int
    forecast_end_index: int
    reliability: Literal['short_term_backtested', 'exploratory_longer_horizon']


@dataclass(frozen=True)
class PlanningHorizonPolicy:
    """사용자 일정과 모델 한계를 함께 보존하는 기간 결정 결과입니다."""

    schedule_status: str
    selection_basis: str
    forecast_horizon_months: int
    forecast_start_month: str
    forecast_end_month: str
    requested_start_month: str
    requested_end_month: str
    strategy_duration_min_months: int
    strategy_duration_max_months: int
    validated_recursive_horizon_months: int
    coverage_complete: bool
    decision_windows: tuple[ForecastDecisionWindow, ...]
    notes: tuple[str, ...]
    as_of_date: str = ''

    def model_payload(self) -> dict[str, Any]:
        """Pydantic 응답과 OpenAI 입력에 안전한 JSON 형태로 바꿉니다."""
        return asdict(self)


def resolve_planning_horizon(
    planning_brief: dict[str, Any] | None,
    latest_observed_month: str,
    *,
    as_of_date: date | None = None,
) -> PlanningHorizonPolicy:
    """일정 미정은 3·6개월, 날짜 입력은 해당 종료월까지의 전망으로 결정합니다.

    31개월 강남구 초기 모델은 1~3개월만 재귀 백테스트했습니다. 4~12개월도 계산은
    가능하지만 탐색 전망으로 명시하고, 12개월 밖 수치를 기획 근거로 만들지 않습니다.
    """
    forecast_start_index = _month_index(latest_observed_month) + 1
    today = as_of_date or date.today()
    forecast_start_month = _month_from_index(forecast_start_index)
    brief = planning_brief or {}
    schedule_status = str(brief.get('schedule_status') or 'unknown')
    requested_start = _date_month(brief.get('start_date'))
    requested_end = _date_month(brief.get('end_date'))

    if schedule_status == 'unknown' or not requested_start or not requested_end:
        # 관측이 늦게 들어와도 지난 달 사업을 제안하지 않습니다. 모델은 누락 월부터
        # 재귀 예측하되, 실행 후보는 오늘이 속한 월 이후만 잘라 집계합니다.
        decision_start = max(forecast_start_index, _month_index(today.strftime('%Y%m')))
        offset = decision_start - forecast_start_index
        horizon = min(MAX_PLANNING_HORIZON_MONTHS, offset + 6)
        windows = tuple(
            ForecastDecisionWindow(
                label=f'{duration}개월 실행 후보', start_month=_month_from_index(decision_start),
                end_month=_month_from_index(decision_start + duration - 1), months=duration,
                forecast_start_index=offset, forecast_end_index=offset + duration - 1,
                reliability=('short_term_backtested' if offset + duration <= VALIDATED_RECURSIVE_HORIZON_MONTHS
                             else 'exploratory_longer_horizon'),
            )
            for duration in (3, 6) if offset + duration <= MAX_PLANNING_HORIZON_MONTHS
        )
        notes = [
            '일정 미정은 현재 월 이후의 3개월·6개월 실행 후보를 비교합니다. 준비기간도 후보 기간에 포함합니다.',
            '신뢰도는 실행기간 길이가 아니라 마지막 관측월로부터의 예측 거리로 판단합니다.',
        ]
        if offset:
            notes.append('관측 공백 월도 내부 예측에는 포함하지만 이미 지난 달은 실행 후보의 합계에서 제외합니다.')
        if len(windows) < 2:
            notes.append('원자료가 오래되어 3·6개월 후보 전체를 12개월 예측 한도 안에서 만들 수 없습니다. 최신 관측자료가 필요합니다.')
        return PlanningHorizonPolicy(
            schedule_status='unknown', selection_basis='unknown_compare_3_and_6_months',
            forecast_horizon_months=horizon, forecast_start_month=forecast_start_month,
            forecast_end_month=_month_from_index(forecast_start_index + horizon - 1),
            requested_start_month='', requested_end_month='',
            strategy_duration_min_months=3, strategy_duration_max_months=6,
            validated_recursive_horizon_months=VALIDATED_RECURSIVE_HORIZON_MONTHS,
            coverage_complete=len(windows) == 2, decision_windows=windows,
            notes=tuple(notes), as_of_date=today.isoformat(),
        )

    requested_start_index = _month_index(requested_start)
    requested_end_index = _month_index(requested_end)
    duration = max(1, requested_end_index - requested_start_index + 1)
    required_horizon = requested_end_index - forecast_start_index + 1
    horizon = min(MAX_PLANNING_HORIZON_MONTHS, max(MIN_MODEL_HORIZON_MONTHS, required_horizon))
    forecast_end_index = forecast_start_index + horizon - 1
    overlap_start = max(forecast_start_index, requested_start_index)
    overlap_end = min(forecast_end_index, requested_end_index)
    coverage_complete = requested_start_index >= forecast_start_index and requested_end_index <= forecast_end_index
    notes: list[str] = []
    if requested_end_index < _month_index(today.strftime('%Y%m')):
        notes.append('희망 기간이 이미 종료되었습니다. 과거 자료 검토일 뿐 향후 실행안으로 승인하지 않습니다.')
    windows: tuple[ForecastDecisionWindow, ...] = ()

    if overlap_start <= overlap_end:
        window_months = overlap_end - overlap_start + 1
        windows = (ForecastDecisionWindow(
            label='입력 일정 전망', start_month=_month_from_index(overlap_start),
            end_month=_month_from_index(overlap_end), months=window_months,
            forecast_start_index=overlap_start - forecast_start_index,
            forecast_end_index=overlap_end - forecast_start_index,
            reliability=(
                'short_term_backtested'
                if overlap_end - forecast_start_index + 1 <= VALIDATED_RECURSIVE_HORIZON_MONTHS
                else 'exploratory_longer_horizon'
            ),
        ),)
    else:
        notes.append('입력 일정이 모델의 향후 전망 범위와 겹치지 않아 ML 수치를 기획 근거로 사용하지 않습니다.')

    if not coverage_complete:
        notes.append('입력 일정 전체가 12개월 전망 범위에 포함되지 않아 포함된 월까지만 참고합니다.')
    if horizon > VALIDATED_RECURSIVE_HORIZON_MONTHS:
        notes.append('4개월 이후 전망은 탐색값이며 월이 멀어질수록 불확실성이 커집니다.')

    return PlanningHorizonPolicy(
        schedule_status=schedule_status, selection_basis='user_schedule_dates',
        forecast_horizon_months=horizon, forecast_start_month=forecast_start_month,
        forecast_end_month=_month_from_index(forecast_end_index),
        requested_start_month=requested_start, requested_end_month=requested_end,
        strategy_duration_min_months=duration, strategy_duration_max_months=duration,
        validated_recursive_horizon_months=VALIDATED_RECURSIVE_HORIZON_MONTHS,
        coverage_complete=coverage_complete, decision_windows=windows,
        notes=tuple(notes), as_of_date=today.isoformat(),
    )
