"""Backend 응답 형식을 고정하는 Pydantic schema입니다."""

from typing import Any, Literal

from pydantic import BaseModel


class BoundaryProperties(BaseModel):
    """React 지도가 표시·선택하는 최소 시군구 속성입니다."""

    region_code: str
    region_name: str
    display_name: str | None = None


class BoundaryGeometry(BaseModel):
    """GeoJSON MultiPolygon geometry입니다."""

    type: Literal['MultiPolygon']
    coordinates: list[Any]


class BoundaryFeature(BaseModel):
    """시군구 하나를 나타내는 GeoJSON Feature입니다."""

    type: Literal['Feature']
    properties: BoundaryProperties
    geometry: BoundaryGeometry


class BoundaryFeatureCollection(BaseModel):
    """React Leaflet에 전달하는 전국 시군구 GeoJSON 응답입니다."""

    type: Literal['FeatureCollection']
    features: list[BoundaryFeature]
