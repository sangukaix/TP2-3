"""API가 지역 코드로 ML을 호출하는 공통 서비스 계층입니다."""

from __future__ import annotations

from typing import Any

from .region_registry import get_region_pipeline


def predict_region_demand(region_code: str, horizon: int) -> dict[str, Any]:
    # API는 지역별 모듈 이름을 알 필요 없이 이 함수만 호출합니다.
    # horizon은 ‘앞으로 몇 개월’을 예측할지 뜻합니다.
    """등록된 해당 지역 모델만 읽어 온라인 예측을 반환합니다."""
    return get_region_pipeline(region_code).predict(horizon)


def train_region_demand(region_code: str) -> dict[str, Any]:
    # 학습은 웹 요청에서 실행하지 않습니다. 원자료가 추가된 뒤 관리자가 CLI로만 실행합니다.
    """운영 요청이 아닌 명시적 CLI에서만 해당 지역 모델을 재학습합니다."""
    return get_region_pipeline(region_code).train()
