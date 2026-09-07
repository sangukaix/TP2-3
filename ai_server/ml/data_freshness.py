"""새 전략기획 생성 전에 공식 월별 원자료의 최신성을 확인합니다.

대시보드와 저장 문서는 이미 확정된 관측값을 읽는 기능이므로 막지 않습니다.
이 모듈은 새 기획안에서 오래된 관측값과 오래된 ML 전망을 현재 상황처럼
사용하지 않도록 생성 시작점만 보호합니다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal


DATA_REFRESH_BLOCK_MONTHS = 3


def _month_index(year_month: str) -> int:
    return int(year_month[:4]) * 12 + int(year_month[4:]) - 1


def _month_from_index(index: int) -> str:
    year, zero_based_month = divmod(index, 12)
    return f'{year}{zero_based_month + 1:02d}'


def _normalize_month(value: object) -> str | None:
    compact = str(value or '').strip().replace('-', '').replace('.', '')
    if len(compact) != 6 or not compact.isdigit():
        return None
    month = int(compact[4:])
    return compact if 1 <= month <= 12 else None


def format_year_month(year_month: str) -> str:
    """사용자 메시지에 YYYY-MM 대신 읽기 쉬운 한국어 월을 사용합니다."""
    return f'{year_month[:4]}년 {int(year_month[4:])}월'


@dataclass(frozen=True)
class DataFreshnessStatus:
    """기획안 생성 가능 여부와 필요한 갱신 범위를 함께 전달하는 안전한 API 계약입니다."""

    status: Literal['ready', 'update_required', 'unavailable']
    can_generate: bool
    reason_code: str
    latest_observed_month: str = ''
    latest_complete_month: str = ''
    missing_month_count: int = 0
    update_start_month: str = ''
    update_end_month: str = ''
    block_threshold_months: int = DATA_REFRESH_BLOCK_MONTHS
    checked_at: str = ''
    message: str = ''
    required_steps: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        """FastAPI와 React가 그대로 쓸 수 있는 JSON 친화 형태입니다."""
        result = asdict(self)
        result['required_steps'] = list(self.required_steps)
        return result


def assess_data_freshness(
    latest_observed_month: object,
    *,
    as_of_date: date | None = None,
    block_threshold_months: int = DATA_REFRESH_BLOCK_MONTHS,
) -> DataFreshnessStatus:
    """마지막 관측월과 마지막 완료 월의 간격으로 새 기획안 생성 가능 여부를 정합니다.

    예를 들어 2026-12-04에 마지막 공식 관측월이 2026-07이면, 8~11월 네 달이
    비어 있으므로 생성은 중단됩니다. 12월은 아직 진행 중인 달이라 누락으로 세지
    않습니다. 월별 자료가 들어오면 별도 적재·검증·재학습 절차를 수행해야 합니다.
    """
    today = as_of_date or date.today()
    normalized = _normalize_month(latest_observed_month)
    checked_at = today.isoformat()
    if not normalized:
        return DataFreshnessStatus(
            status='unavailable',
            can_generate=False,
            reason_code='DATA_FRESHNESS_UNAVAILABLE',
            checked_at=checked_at,
            message=(
                '마지막 확정 관측월을 확인하지 못해 새 기획안을 생성하지 않습니다. '
                '지역 원자료의 월 정보와 적재 상태를 먼저 확인해 주세요.'
            ),
            required_steps=('원자료 적재 상태 확인', '월별 기간·지역 코드 검증', 'ML 재학습 및 계절 기준모델 비교'),
        )

    latest_complete_index = _month_index(f'{today.year}{today.month:02d}') - 1
    latest_complete_month = _month_from_index(latest_complete_index)
    observed_index = _month_index(normalized)
    missing_count = max(0, latest_complete_index - observed_index)
    update_start = _month_from_index(observed_index + 1) if missing_count else ''
    update_end = latest_complete_month if missing_count else ''
    required_steps = ('공식 원자료 적재', '월별 기간·지역 코드·단위 검증', 'ML 재학습', '계절 기준모델과 성능 비교')

    if missing_count >= block_threshold_months:
        return DataFreshnessStatus(
            status='update_required',
            can_generate=False,
            reason_code='DATA_REFRESH_REQUIRED',
            latest_observed_month=normalized,
            latest_complete_month=latest_complete_month,
            missing_month_count=missing_count,
            update_start_month=update_start,
            update_end_month=update_end,
            block_threshold_months=block_threshold_months,
            checked_at=checked_at,
            message=(
                f'최신 확정 관측월이 {format_year_month(normalized)}이므로 '
                f'{format_year_month(update_start)}~{format_year_month(update_end)} '
                f'({missing_count}개월) 공식 원자료 업데이트가 필요합니다. '
                '원자료 적재 → 데이터 검증 → ML 재학습 → 계절 기준모델 비교가 완료될 때까지 '
                '새 기획안 생성은 잠시 중단됩니다. 기존 대시보드와 저장 기획안은 계속 볼 수 있습니다.'
            ),
            required_steps=required_steps,
        )

    if missing_count:
        message = (
            f'최신 확정 관측월은 {format_year_month(normalized)}이며 '
            f'{format_year_month(update_start)}~{format_year_month(update_end)} '
            f'({missing_count}개월) 자료가 아직 반영되지 않았습니다. '
            f'{block_threshold_months}개월 미만의 반영 지연이라 새 기획안은 생성할 수 있습니다. '
            '새 자료를 반영할 때는 원자료 적재 → 데이터 검증 → ML 재학습 → 계절 기준모델 비교를 함께 진행하세요.'
        )
    else:
        message = (
            f'최신 확정 관측월은 {format_year_month(normalized)}입니다. '
            '새 기획안 생성에 필요한 월별 원자료 최신성 기준을 충족했습니다.'
        )
    return DataFreshnessStatus(
        status='ready',
        can_generate=True,
        reason_code='DATA_FRESHNESS_READY',
        latest_observed_month=normalized,
        latest_complete_month=latest_complete_month,
        missing_month_count=missing_count,
        update_start_month=update_start,
        update_end_month=update_end,
        block_threshold_months=block_threshold_months,
        checked_at=checked_at,
        message=message,
        required_steps=required_steps if missing_count else (),
    )
