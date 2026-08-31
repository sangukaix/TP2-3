"""React 대시보드용 일반 Backend 진입점입니다."""

from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.schemas import BoundaryFeatureCollection
from app.services.vworld import get_sido_boundaries, get_sigungu_boundaries


app = FastAPI(title='STAY-UP AI Backend', version='0.1.0')
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

# 개발 중 Vite 화면에서 직접 API를 확인할 수 있도록 허용합니다. 배포 시 실제 도메인으로 제한합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:5175', 'http://127.0.0.1:5175'],
    allow_credentials=False,
    allow_methods=['GET'],
    allow_headers=['*'],
)


@app.get('/health')
async def health_check() -> dict[str, str]:
    """서버가 실행 중인지 확인하는 가장 작은 상태 확인 API입니다."""
    return {'status': 'ok'}


@app.get('/api/v1/boundaries/sigungu', response_model=BoundaryFeatureCollection)
async def read_sigungu_boundaries(
    sido_code: str | None = Query(default=None, pattern=r'^\d{2}$'),
) -> dict[str, Any]:
    """React 지도에 필요한 전국 또는 선택 시도의 시군구 경계입니다."""
    collection = await get_sigungu_boundaries()
    if not sido_code:
        return collection
    features = [
        feature for feature in collection['features']
        if feature['properties']['region_code'].startswith(sido_code)
    ]

    # 2026-07-01 인천 행정체제 개편 전에 집계된 서구 원자료를 선택할 수 있게
    # 현재 서해구·검단구 경계를 합친 "원자료 기준" 분석 영역을 추가합니다.
    # 현재 행정통계를 합산하는 기능이 아니라, 2026년 6월까지의 기존 서구 자료 표시용입니다.
    if sido_code == '28' and not any(feature['properties']['region_code'] == '28260' for feature in features):
        former_seogu_parts = [
            feature for feature in features
            if feature['properties']['region_code'] in {'28275', '28290'}
        ]
        if len(former_seogu_parts) == 2:
            coordinates: list[Any] = []
            for feature in former_seogu_parts:
                coordinates.extend(feature['geometry']['coordinates'])
            features.append({
                'type': 'Feature',
                'properties': {
                    'region_code': '28260',
                    'region_name': '인천광역시 서구',
                    'display_name': '인천광역시 서구 (2026.06 원자료 기준)',
                },
                'geometry': {'type': 'MultiPolygon', 'coordinates': coordinates},
            })
    return {
        'type': 'FeatureCollection',
        'features': features,
    }


@app.get('/api/v1/boundaries/sido', response_model=BoundaryFeatureCollection)
async def read_sido_boundaries() -> dict[str, Any]:
    """React 지도에서 첫 단계로 표시할 전국 시도 경계입니다."""
    return await get_sido_boundaries()
