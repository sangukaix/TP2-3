"""강남구 공식 snapshot을 읽어 월별 학습용 표로 만드는 전처리 모듈입니다.

수동 ``data/raw`` 원본과 최신 보완 다운로드는 모두 hash-검증
``data/source_snapshots``에 불변 복제돼 있다. 이 모듈은 snapshot ZIP을
메모리에서 읽고, 학습 실행 시에만 ``data/processed`` 파일을 새로 만든다.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable
import zipfile

import pandas as pd

from .validation import validate_monthly_data


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 지역코드와 snapshot 경로를 상수로 두면, 실행 위치가 달라도 같은 검증 원본을 찾을 수 있습니다.
REGION_CODE = '11680'
GANGNAM_SNAPSHOT_ROOT = PROJECT_ROOT / 'data' / 'source_snapshots' / '서울특별시' / '서울특별시_강남구'
# 2026-07은 이전 공식 다운로드의 최신 보완본이다. 기존 수동 경로를 직접 읽지 않도록
# 동일 hash 원본을 snapshot의 별도 보완 폴더에 보관한다.
SUPPLEMENTAL_202607_ROOT = GANGNAM_SNAPSHOT_ROOT / 'supplemental_202607'
# 대시보드와 같은 정의를 쓰기 위해 연인원이 아니라 체류자료의 월간 순 방문자 수를 사용합니다.
LATEST_STAY_ZIP = SUPPLEMENTAL_202607_ROOT / '강남구_숙박체류시간.zip'
LATEST_SPENDING_ZIP = SUPPLEMENTAL_202607_ROOT / '강남구_관광소비.zip'
LATEST_VISITOR_ZIP = SUPPLEMENTAL_202607_ROOT / '강남구_방문자.zip'
# 지역 코드별로 분리해 50개 이상 시군구의 전처리 표가 서로 덮어쓰지 않게 합니다.
PROCESSED_PATH = PROJECT_ROOT / 'data' / 'processed' / 'ml' / REGION_CODE / 'monthly_demand.csv'


def _decode_csv(raw: bytes) -> str:
    """데이터랩 CSV의 UTF-8/CP949/EUC-KR 인코딩을 순서대로 안전하게 판별합니다."""
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('강남구 원본 CSV 인코딩을 읽지 못했습니다.')


def _number(value: str) -> float:
    """쉼표·지수 표기가 섞인 원본 숫자를 학습용 실수로 바꿉니다."""
    return float(str(value).replace(',', '').strip())


ML_TABLE_NAMES = (
    '순 방문자 수 및 숙박 비율', '관광소비 추이_외지인', '평균 숙박일',
    '숙박방문자 비율 추이', '평균 체류시간 추이', '숙박 목적지 검색건수',
    '내비게이션 목적지 유형별 검색량',
)


def _read_interesting_rows(archive: zipfile.ZipFile) -> Iterable[tuple[str, list[dict[str, str]]]]:
    """검증한 7개 월별 Target 표만 선택해 다른 정의의 표가 섞이지 않게 합니다."""
    for entry in archive.infolist():
        if not entry.filename.lower().endswith('.csv'):
            continue
        if not any(name in entry.filename for name in ML_TABLE_NAMES):
            continue
        rows = list(csv.DictReader(io.StringIO(_decode_csv(archive.read(entry)))))
        yield entry.filename, rows


def _append_metrics(
    archive: zipfile.ZipFile,
    visitors: dict[str, float],
    spending_krw: dict[str, float],
    lodging_nights: dict[str, float],
    lodging_rate_pct: dict[str, float],
    stay_minutes: dict[str, float],
    navigation_searches: dict[str, float],
    lodging_searches: dict[str, float],
) -> None:
    """한 ZIP에서 학습 가능한 7개 월별 수치를 같은 YYYYMM 키로 수집합니다."""
    for file_name, rows in _read_interesting_rows(archive):
        is_visitor = '순 방문자 수 및 숙박 비율' in file_name
        for row in rows:
            month = str(row.get('기준년월') or row.get('기준연월') or '').strip()
            if len(month) != 6 or not month.isdigit():
                continue
            if is_visitor:
                visitors[month] = _number(row['순 방문자수'])
            elif '관광소비 추이_외지인' in file_name and row.get('업종대분류명') == '전체':
                # 원본 단위가 천원이므로, 서비스와 문서에는 원 단위로 통일해 전달합니다.
                spending_krw[month] = _number(row['소비액(천원)']) * 1000
            elif '평균 숙박일' in file_name:
                lodging_nights[month] = _number(row['평균 숙박일수'])
            elif '숙박방문자 비율 추이' in file_name and str(row.get('지역명') or '').strip() == '강남구':
                lodging_rate_pct[month] = _number(row['숙박방문자 비율'])
            elif '평균 체류시간 추이' in file_name and str(row.get('지역명') or '').strip() == '강남구':
                stay_minutes[month] = _number(row['체류시간(분)'])
            elif '숙박 목적지 검색건수' in file_name:
                lodging_searches[month] = _number(row['검색건수'])
            elif ('내비게이션 목적지 유형별 검색량' in file_name
                  and str(row.get('목적지 유형') or '').strip() == '전체'):
                navigation_searches[month] = _number(row['목적지 검색량'])


def _read_snapshot_archives(series: dict[str, dict[str, float]]) -> None:
    """불변 snapshot의 연도별 category ZIP에서 2024~2026 자료를 읽는다."""

    if not GANGNAM_SNAPSHOT_ROOT.is_dir():
        raise FileNotFoundError(f'강남구 snapshot을 찾지 못했습니다: {GANGNAM_SNAPSHOT_ROOT}')
    # 3개 category의 2024~2026 공식 ZIP만 읽는다. 후속 최신 보완 ZIP은 아래 함수가
    # 명시적으로 마지막에 적용하므로, 같은 월에 다른 다운로드가 조용히 선택되지 않는다.
    for category in ('숙박_체류시간', '관광소비', '방문자'):
        category_root = GANGNAM_SNAPSHOT_ROOT / category
        archives = sorted(category_root.glob('20??_*.zip')) if category_root.is_dir() else []
        if not archives:
            raise FileNotFoundError(f'강남구 snapshot category 원본을 찾지 못했습니다: {category_root}')
        for path in archives:
            with zipfile.ZipFile(path) as archive:
                _append_metrics(archive, **series)


def _read_latest_snapshot_supplement(series: dict[str, dict[str, float]]) -> None:
    """7월 최신 관측값은 별도의 공식 snapshot 보완 ZIP으로 적용합니다.

    같은 월이 중복될 경우 최신 다운로드가 기존 값보다 우선합니다. 이 처리 덕분에
    갱신된 월 값이 모델 학습·대시보드 기준값으로 함께 사용됩니다.
    """
    for path in (LATEST_STAY_ZIP, LATEST_SPENDING_ZIP, LATEST_VISITOR_ZIP):
        if not path.exists():
            raise FileNotFoundError(f'강남구 최신월 snapshot 원본을 찾지 못했습니다: {path}')
        with zipfile.ZipFile(path) as archive:
            _append_metrics(archive, **series)


def load_gangnam_monthly_demand() -> pd.DataFrame:
    """2024-01부터 최신 관측월까지의 공통 월별 방문자·소비·숙박일 시계열을 반환합니다."""
    series: dict[str, dict[str, float]] = {
        'visitors': {}, 'spending_krw': {}, 'lodging_nights': {},
        'lodging_rate_pct': {}, 'stay_minutes': {},
        'navigation_searches': {}, 'lodging_searches': {},
    }
    _read_snapshot_archives(series)
    _read_latest_snapshot_supplement(series)

    # 세 지표가 모두 존재하는 월만 공통 키로 사용합니다. 부분 월을 억지로 0으로 채우지 않습니다.
    common_months = sorted(set.intersection(*(set(values) for values in series.values())))
    if len(common_months) < 24:
        raise ValueError(f'강남구 학습에는 최소 24개 공통 월이 필요합니다. 현재 {len(common_months)}개입니다.')
    frame = pd.DataFrame({
        'region_code': REGION_CODE,
        'region_name': '서울특별시 강남구',
        'year_month': common_months,
        'visitors': [round(series['visitors'][month]) for month in common_months],
        'spending_krw': [round(series['spending_krw'][month]) for month in common_months],
        'lodging_nights': [series['lodging_nights'][month] for month in common_months],
        'lodging_rate_pct': [series['lodging_rate_pct'][month] for month in common_months],
        'stay_minutes': [series['stay_minutes'][month] for month in common_months],
        'navigation_searches': [round(series['navigation_searches'][month]) for month in common_months],
        'lodging_searches': [round(series['lodging_searches'][month]) for month in common_months],
    })
    # 날짜 열은 학습 피처의 월/계절을 계산할 때만 사용하고, CSV에는 안정적인 YYYYMM 키를 보관합니다.
    frame['year_month'] = frame['year_month'].astype(str)
    validate_monthly_data(frame, REGION_CODE)
    return frame


def write_processed_dataset() -> pd.DataFrame:
    """재현 가능한 월별 학습 표를 data/processed에 저장하고 같은 DataFrame을 반환합니다."""
    frame = load_gangnam_monthly_demand()
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(PROCESSED_PATH, index=False, encoding='utf-8-sig')
    return frame


def load_latest_consumption_shares() -> list[dict[str, float | str]]:
    """최신 관측월 외지인 관광소비 업종 비중을 반환합니다.

    업종별 수요를 별도 예측하지는 않습니다. 대시보드의 다음 달 소비 패턴은 이
    최신 관측 비중을 유지한다고 가정해, 전체 소비액 예측과 구분하여 표시합니다.
    """
    # 업종별 금액은 전체 금액과 같은 월의 행만 모아야 비중의 분모가 일치합니다.
    amounts_by_month: dict[str, dict[str, float]] = {}
    with zipfile.ZipFile(LATEST_SPENDING_ZIP) as archive:
        for file_name, rows in _read_interesting_rows(archive):
            if '관광소비 추이_외지인' not in file_name:
                continue
            for row in rows:
                month = str(row.get('기준년월') or row.get('기준연월') or '').strip()
                category = str(row.get('업종대분류명') or '').strip()
                if month and category:
                    amounts_by_month.setdefault(month, {})[category] = _number(row['소비액(천원)']) * 1000
    if not amounts_by_month:
        raise ValueError('최신 외지인 관광소비 업종 표를 찾지 못했습니다.')
    latest_month = max(amounts_by_month)
    latest_amounts = amounts_by_month[latest_month]
    total = latest_amounts.get('전체')
    if not total:
        raise ValueError('최신 외지인 관광소비 전체 행을 찾지 못했습니다.')
    return [
        {'name': name, 'share': round(amount / total * 100, 1)}
        for name, amount in sorted(latest_amounts.items(), key=lambda item: item[1], reverse=True)
        if name != '전체' and amount > 0
    ]


def load_latest_lodging_metrics() -> tuple[float, float, float]:
    """세 번째 카드와 호환을 위해 최신 숙박 비율·평균 숙박일·전월 차이를 읽습니다."""
    # 숙박 비율과 평균 숙박일은 서로 다른 표에 있을 수 있어 월 키로 각각 읽은 뒤 교집합을 구합니다.
    lodging_rate: dict[str, float] = {}
    lodging_nights: dict[str, float] = {}
    with zipfile.ZipFile(LATEST_STAY_ZIP) as archive:
        for entry in archive.infolist():
            if not entry.filename.lower().endswith('.csv'):
                continue
            if '숙박방문자 비율 추이' not in entry.filename and '평균 숙박일' not in entry.filename:
                continue
            rows = list(csv.DictReader(io.StringIO(_decode_csv(archive.read(entry)))))
            for row in rows:
                month = str(row.get('기준년월') or row.get('기준연월') or '').strip()
                if not month:
                    continue
                if '숙박방문자 비율 추이' in entry.filename:
                    # 같은 표에 전국 평균과 강남구가 함께 있으므로, 강남구 행만 사용합니다.
                    if str(row.get('지역명') or '').strip() == '강남구':
                        lodging_rate[month] = _number(row['숙박방문자 비율'])
                else:
                    lodging_nights[month] = _number(row['평균 숙박일수'])
    shared_months = sorted(set(lodging_rate) & set(lodging_nights))
    if len(shared_months) < 2:
        raise ValueError('숙박 지표의 최신·전월 값을 함께 찾지 못했습니다.')
    latest_month, previous_month = shared_months[-1], shared_months[-2]
    return lodging_rate[latest_month], lodging_nights[latest_month], lodging_nights[latest_month] - lodging_nights[previous_month]
