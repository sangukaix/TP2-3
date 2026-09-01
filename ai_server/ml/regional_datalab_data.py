"""여러 시군구의 동일한 관광데이터랩 CSV 구조를 공통 월별 학습표로 바꿉니다.

지역마다 파일명 앞에 다운로드 시각이 붙어도, 표의 제목과 열 정의가 같으면 이 모듈을
재사용합니다. 원본 ``data/raw``는 읽기만 하고, 검증을 통과한 결과만 ``data/processed``에 씁니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from .gangnam_data import PROJECT_ROOT
from .validation import validate_monthly_data


@dataclass(frozen=True)
class StandardDatalabRegion:
    """관광데이터랩의 직접 다운로드 CSV를 가진 한 시군구의 최소 설정입니다."""

    region_code: str
    region_name: str
    short_name: str
    raw_directory: Path


def _read_csv(path: Path) -> pd.DataFrame:
    """관광데이터랩 CSV의 UTF-8·CP949·EUC-KR 인코딩을 순서대로 읽습니다."""
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'ML_CSV_ENCODING: {path.name} 인코딩을 읽지 못했습니다.')


def _number(value: object) -> float:
    """쉼표·지수 표기를 포함한 원본 수치를 학습용 실수로 정규화합니다."""
    return float(str(value).replace(',', '').strip())


def _year_names(base: Path) -> list[str]:
    """숙박·체류 폴더의 연도 이름만 골라 오래된 자료부터 처리합니다."""
    return sorted(
        (path.name for path in (base / '숙박_체류시간').iterdir() if path.is_dir() and path.name.isdigit() and len(path.name) == 4),
    )


def _find_table(folder: Path, title: str) -> Path:
    """파일명 앞의 다운로드 시각과 공백 차이를 무시하고 필요한 표를 찾습니다."""
    if not folder.exists():
        raise FileNotFoundError(f'ML_CATEGORY_MISSING: {folder}')
    matches = [path for path in folder.glob('*.csv') if title.replace(' ', '') in path.name.replace(' ', '')]
    if not matches:
        raise FileNotFoundError(f'ML_TABLE_MISSING: {folder}/{title}')
    # 같은 제목의 파일이 중복되면 파일명 순서가 아닌 최신 수정본 하나를 사용합니다.
    return max(matches, key=lambda path: path.stat().st_mtime)


def _month_column(frame: pd.DataFrame) -> str:
    """기관별 표기 차이인 기준연월/기준년월을 하나의 월 키로 맞춥니다."""
    for candidate in ('기준연월', '기준년월'):
        if candidate in frame.columns:
            return candidate
    raise ValueError('ML_MONTH_COLUMN_MISSING: 기준연월 또는 기준년월 열이 없습니다.')


def _value_column(frame: pd.DataFrame, *candidates: str) -> str:
    """정의가 확인된 후보 열 가운데 실제 원본에 있는 값을 선택합니다."""
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    raise ValueError(f'ML_VALUE_COLUMN_MISSING: {candidates} 열이 없습니다.')


def _put_all_rows(target: dict[str, float], frame: pd.DataFrame, value_column: str) -> None:
    """한 표의 월별 단일 값을 YYYYMM 키로 넣습니다."""
    month_column = _month_column(frame)
    for row in frame.to_dict('records'):
        month = str(row.get(month_column) or '').strip()
        if len(month) == 6 and month.isdigit():
            target[month] = _number(row[value_column])


def _put_filtered_rows(
    target: dict[str, float], frame: pd.DataFrame, value_column: str, predicate: Callable[[dict[str, object]], bool],
) -> None:
    """전체·선택 지역처럼 필요한 행만 골라 월별 수치로 저장합니다."""
    month_column = _month_column(frame)
    for row in frame.to_dict('records'):
        month = str(row.get(month_column) or '').strip()
        if len(month) == 6 and month.isdigit() and predicate(row):
            target[month] = _number(row[value_column])


def load_standard_datalab_monthly_demand(spec: StandardDatalabRegion) -> pd.DataFrame:
    """직접 내려받은 방문·소비·체류·검색 CSV에서 7개 공통 Target을 만듭니다.

    모든 Target이 있는 월만 사용합니다. 결측치를 0으로 채우면 전년 동월·시차 피처가 왜곡되므로
    월 누락은 ``validate_monthly_data``에서 명시적으로 중단합니다.
    """
    series: dict[str, dict[str, float]] = {
        'visitors': {}, 'spending_krw': {}, 'lodging_nights': {}, 'lodging_rate_pct': {},
        'stay_minutes': {}, 'navigation_searches': {}, 'lodging_searches': {},
    }
    # 소비 원본은 천 원 단위이므로 누적 수집 중에는 원래 단위를 유지하고, 최종 표를 만들 때 한 번만 원으로 바꿉니다.
    spending_thousand: dict[str, float] = {}
    if not spec.raw_directory.exists():
        raise FileNotFoundError(f'ML_REGION_RAW_MISSING: {spec.raw_directory}')

    for year in _year_names(spec.raw_directory):
        # 한 지역의 체류·숙박 원본은 방문자, 숙박 비율, 숙박일, 체류시간, 숙박검색을 함께 제공합니다.
        stay_root = spec.raw_directory / '숙박_체류시간' / year
        visitor_frame = _read_csv(_find_table(stay_root, '순 방문자 수 및 숙박 비율'))
        _put_all_rows(series['visitors'], visitor_frame, _value_column(visitor_frame, '순 방문자수'))

        lodging_frame = _read_csv(_find_table(stay_root, '평균 숙박일'))
        _put_all_rows(series['lodging_nights'], lodging_frame, _value_column(lodging_frame, '평균 숙박일수'))

        lodging_rate_frame = _read_csv(_find_table(stay_root, '숙박방문자 비율 추이'))
        _put_filtered_rows(
            series['lodging_rate_pct'], lodging_rate_frame,
            _value_column(lodging_rate_frame, '숙박방문자 비율'),
            lambda row: str(row.get('지역명') or '').strip() == spec.short_name,
        )

        stay_frame = _read_csv(_find_table(stay_root, '평균 체류시간 추이'))
        _put_filtered_rows(
            series['stay_minutes'], stay_frame, _value_column(stay_frame, '체류시간(분)'),
            lambda row: str(row.get('지역명') or '').strip() == spec.short_name,
        )

        lodging_search_frame = _read_csv(_find_table(stay_root, '숙박 목적지 검색건수'))
        _put_all_rows(series['lodging_searches'], lodging_search_frame, _value_column(lodging_search_frame, '검색건수'))

        spending_frame = _read_csv(_find_table(spec.raw_directory / '관광소비' / year, '관광소비 추이_외지인'))
        _put_filtered_rows(
            spending_thousand, spending_frame, _value_column(spending_frame, '소비액(천원)'),
            lambda row: str(row.get('업종대분류명') or '').strip() == '전체',
        )

        navigation_frame = _read_csv(_find_table(spec.raw_directory / '방문자' / year, '내비게이션 목적지 유형별 검색량'))
        _put_filtered_rows(
            series['navigation_searches'], navigation_frame, _value_column(navigation_frame, '목적지 검색량'),
            lambda row: str(row.get('목적지 유형') or '').strip() == '전체',
        )

        # stay_root는 읽기 전용 위치임을 코드 리뷰에서 분명히 드러내기 위한 확인 변수입니다.
        if not stay_root.exists():
            raise FileNotFoundError(f'ML_CATEGORY_MISSING: {stay_root}')

    # 관광소비 원본 단위는 천 원이므로 서비스·기획안의 원 단위로만 변환합니다.
    series['spending_krw'] = {month: value * 1000 for month, value in spending_thousand.items()}
    common_months = sorted(set.intersection(*(set(values) for values in series.values())))
    if len(common_months) < 24:
        raise ValueError(f'ML_COMMON_MONTHS_INSUFFICIENT: {spec.region_name} 공통 월이 {len(common_months)}개입니다.')
    frame = pd.DataFrame({
        'region_code': spec.region_code,
        'region_name': spec.region_name,
        'year_month': common_months,
        **{
            key: [round(series[key][month]) if key in {'visitors', 'spending_krw', 'navigation_searches', 'lodging_searches'} else series[key][month]
                  for month in common_months]
            for key in series
        },
    })
    validate_monthly_data(frame, spec.region_code)
    return frame


def write_standard_datalab_dataset(spec: StandardDatalabRegion) -> pd.DataFrame:
    """검증된 지역별 학습 표를 코드별 경로에 재현 가능하게 저장합니다."""
    frame = load_standard_datalab_monthly_demand(spec)
    destination = PROJECT_ROOT / 'data' / 'processed' / 'ml' / spec.region_code / 'monthly_demand.csv'
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False, encoding='utf-8-sig')
    return frame
