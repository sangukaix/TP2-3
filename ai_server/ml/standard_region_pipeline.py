"""표준 관광데이터랩 CSV 지역의 학습·예측 함수를 카탈로그 한 줄에서 만듭니다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from .gangnam_forecast import RegionForecastSettings, predict_region_future_months, train_region_models
from .region_catalog import PROJECT_ROOT, RegionDataCatalogEntry
from .regional_datalab_data import StandardDatalabRegion, load_standard_datalab_monthly_demand, write_standard_datalab_dataset


@dataclass(frozen=True)
class StandardPipelineFunctions:
    """등록표가 필요한 학습·예측·이력 함수의 묶음입니다."""

    train: Callable[[], dict[str, Any]]
    predict: Callable[[int], dict[str, Any]]
    load_history: Callable[[], pd.DataFrame]


def build_standard_pipeline_functions(entry: RegionDataCatalogEntry) -> StandardPipelineFunctions:
    """카탈로그의 표준 CSV 지역을 코드 복사 없이 ML 공통 알고리즘에 연결합니다."""
    if entry.adapter_type != 'standard_datalab_csv':
        raise ValueError(f'ML_STANDARD_ADAPTER_UNSUPPORTED: {entry.adapter_type}')
    spec = StandardDatalabRegion(
        region_code=entry.region_code,
        region_name=entry.region_name,
        short_name=entry.short_name,
        raw_directory=entry.raw_path,
    )

    def load_history() -> pd.DataFrame:
        """해당 지역의 읽기 전용 원본을 공통 7개 Target 표로 검증합니다."""
        return load_standard_datalab_monthly_demand(spec)

    def write_processed() -> pd.DataFrame:
        """검증을 통과한 경우에만 지역 코드별 processed 파일을 생성합니다."""
        return write_standard_datalab_dataset(spec)

    settings = RegionForecastSettings(
        region_code=entry.region_code,
        region_name=entry.region_name,
        load_monthly=load_history,
        write_processed=write_processed,
        artifact_directory=PROJECT_ROOT / 'artifacts' / 'ml' / entry.region_code,
        model_version='regional-demand-v3.1',
    )

    def train() -> dict[str, Any]:
        """관리 CLI에서만 해당 지역의 시간순 모델을 새로 저장합니다."""
        return train_region_models(settings)

    def predict(horizon: int) -> dict[str, Any]:
        """온라인 요청에는 저장된 해당 지역 모델만 사용합니다."""
        return predict_region_future_months(settings, horizon)

    return StandardPipelineFunctions(train=train, predict=predict, load_history=load_history)
