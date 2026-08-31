"""지역별 월별 학습표의 날짜·숫자·지역 키를 검사합니다. 원본은 수정하지 않습니다."""

from __future__ import annotations

from hashlib import sha256
import json

import numpy as np
import pandas as pd


# 모든 지역 어댑터가 같은 Target 이름을 사용하면 검증·hash·학습 페이지를 재사용할 수 있습니다.
TARGETS = (
    'visitors', 'spending_krw', 'lodging_nights', 'lodging_rate_pct',
    'stay_minutes', 'navigation_searches', 'lodging_searches',
)


def validate_monthly_data(frame: pd.DataFrame, region_code: str) -> None:
    """월이 빠지면 lag_12가 전년 동월이 아니므로, 누락을 채우지 않고 학습을 중단합니다."""
    required = {'region_code', 'year_month', *TARGETS}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError('ML_DATA_INVALID: 학습표의 필수 열이나 행이 없습니다.')
    if set(frame['region_code'].astype(str)) != {str(region_code)}:
        raise ValueError('ML_REGION_MISMATCH: 학습표에 다른 지역 코드가 섞였습니다.')
    months = frame['year_month'].astype(str).tolist()
    if any(len(month) != 6 or not month.isdigit() for month in months):
        raise ValueError('ML_MONTH_INVALID: 기준월은 YYYYMM 형식이어야 합니다.')
    dates = pd.to_datetime(months, format='%Y%m', errors='raise')
    expected = pd.date_range(dates[0], periods=len(dates), freq='MS')
    if not dates.equals(expected):
        raise ValueError('ML_MONTH_GAP: 월 누락·중복·정렬 오류를 확인하세요.')
    values = frame[list(TARGETS)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('ML_VALUE_INVALID: 결측·무한대·음수는 학습할 수 없습니다.')


def data_fingerprint(frame: pd.DataFrame) -> str:
    """데이터 버전(hash)은 같은 월의 값이 수정됐을 때도 재학습 필요 여부를 판별합니다."""
    rows = [
        [str(row.region_code), str(row.year_month), *[float(getattr(row, key)) for key in TARGETS]]
        for row in frame.itertuples(index=False)
    ]
    return sha256(json.dumps(rows, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
