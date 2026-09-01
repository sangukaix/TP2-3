"""여러 시군구 ML 파이프라인의 등록 정보와 공통 진입점을 관리합니다.

새 지역을 추가할 때 화면 코드를 복사하지 않습니다. 이 파일에 지역 코드와
전용 데이터 어댑터를 등록한 뒤, 같은 train/predict 인터페이스를 사용합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from .gangnam_data import load_gangnam_monthly_demand
from .gangnam_forecast import predict_future_months, train_gangnam_models
from .region_catalog import list_region_data_catalog
from .standard_region_pipeline import build_standard_pipeline_functions


@dataclass(frozen=True)
class RegionMlPipeline:
    """한 시군구의 학습·예측 함수를 묶는 최소 계약입니다."""

    region_code: str
    region_name: str
    train: Callable[[], dict[str, Any]]
    predict: Callable[[int], dict[str, Any]]
    # 기획안의 전년 동월 비교에도 동일한 원자료를 쓰기 위한 읽기 전용 함수입니다.
    load_history: Callable[[], Any] | None = None


def _build_region_pipelines() -> dict[str, RegionMlPipeline]:
    """카탈로그를 읽어 표준 CSV 지역을 같은 ML 계약으로 자동 등록합니다.

    강남구는 중첩 ZIP이라는 별도 원본 구조 때문에 예외 어댑터를 유지합니다.
    나머지 표준 관광데이터랩 CSV 지역은 카탈로그 한 줄만 추가하면 됩니다.
    """
    pipelines = {
        '11680': RegionMlPipeline(
            '11680',
            '서울특별시 강남구',
            train_gangnam_models,
            predict_future_months,
            load_gangnam_monthly_demand,
        ),
    }
    for entry in list_region_data_catalog():
        if entry.region_code == '11680' or entry.adapter_type != 'standard_datalab_csv':
            continue
        functions = build_standard_pipeline_functions(entry)
        pipelines[entry.region_code] = RegionMlPipeline(
            entry.region_code,
            entry.region_name,
            functions.train,
            functions.predict,
            functions.load_history,
        )
    return pipelines


# 모듈 시작 시 한 번 구성합니다. 원본을 바꾼 경우 서버를 재시작한 뒤 점검·재학습합니다.
_PIPELINES = _build_region_pipelines()


def get_region_pipeline(region_code: str) -> RegionMlPipeline:
    """등록되지 않은 지역에 강남 모델을 잘못 적용하지 않도록 명시적으로 거절합니다."""
    try:
        return _PIPELINES[str(region_code)]
    except KeyError as exc:
        raise ValueError(f'{region_code} 지역의 ML 파이프라인이 아직 등록되지 않았습니다.') from exc


def list_region_pipelines() -> tuple[RegionMlPipeline, ...]:
    """관리 화면·일괄 학습 CLI가 지원 지역 목록을 재사용할 수 있게 합니다."""
    return tuple(_PIPELINES.values())
