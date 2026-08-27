"""VWorld WFS를 서버에서 호출해 시도·시군구 경계 GeoJSON을 제공하는 서비스입니다."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import get_settings


# 레이어마다 하루 동안 캐시합니다. 지도 클릭 때마다 VWorld를 다시 호출하지 않습니다.
_cache: dict[str, dict[str, Any]] = {}
_cache_expires_at: dict[str, datetime] = {}
_cache_lock = asyncio.Lock()
_CACHE_TTL = timedelta(hours=24)
_KOREA_BOUNDS = (32.0, 123.0, 40.5, 133.0)
_DISK_CACHE_DIRECTORY = Path(__file__).resolve().parents[2] / '.cache' / 'vworld'
_DISK_CACHE_VERSION = 'v2'
_MAP_SIMPLIFY_TOLERANCE = 0.001


def _read_disk_cache(cache_key: str, now: datetime) -> dict[str, Any] | None:
    """서버 재시작 후에도 24시간 안의 키 없는 GeoJSON 캐시를 재사용합니다."""
    cache_path = _DISK_CACHE_DIRECTORY / f'{cache_key}-{_DISK_CACHE_VERSION}.json'
    try:
        modified_at = datetime.fromtimestamp(cache_path.stat().st_mtime, timezone.utc)
        if now - modified_at >= _CACHE_TTL:
            return None
        payload = json.loads(cache_path.read_text(encoding='utf-8'))
        if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
            return None
        return payload
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError):
        return None


def _write_disk_cache(cache_key: str, collection: dict[str, Any]) -> None:
    """API 키가 제거된 병합 경계만 임시 파일을 거쳐 안전하게 저장합니다."""
    try:
        _DISK_CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        cache_path = _DISK_CACHE_DIRECTORY / f'{cache_key}-{_DISK_CACHE_VERSION}.json'
        temporary_path = cache_path.with_suffix('.tmp')
        temporary_path.write_text(
            json.dumps(collection, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        temporary_path.replace(cache_path)
    except OSError:
        # 캐시 저장 실패는 지도 자체의 실패가 아니므로 메모리 캐시로 계속 서비스합니다.
        return


def _polygon_parts(geometry: dict[str, Any] | None) -> list[Any]:
    """Polygon·MultiPolygon을 모두 MultiPolygon 좌표 목록으로 정규화합니다."""
    if not geometry:
        return []
    if geometry.get('type') == 'Polygon':
        return [geometry.get('coordinates')]
    if geometry.get('type') == 'MultiPolygon':
        return geometry.get('coordinates') or []
    return []


def _point_segment_distance(point: list[float], start: list[float], end: list[float]) -> float:
    """경위도 평면에서 점과 선분 사이의 근사 거리를 계산합니다."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
    ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)))
    projected_x = start[0] + ratio * dx
    projected_y = start[1] + ratio * dy
    return ((point[0] - projected_x) ** 2 + (point[1] - projected_y) ** 2) ** 0.5


def _simplify_open_line(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """재귀 깊이 문제 없이 Ramer-Douglas-Peucker 방식으로 표시용 선을 단순화합니다."""
    if len(points) <= 2:
        return points
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start_index, end_index = stack.pop()
        start, end = points[start_index], points[end_index]
        farthest_index = -1
        farthest_distance = 0.0
        for index in range(start_index + 1, end_index):
            distance = _point_segment_distance(points[index], start, end)
            if distance > farthest_distance:
                farthest_distance = distance
                farthest_index = index
        if farthest_index >= 0 and farthest_distance > tolerance:
            keep.add(farthest_index)
            stack.append((start_index, farthest_index))
            stack.append((farthest_index, end_index))
    return [[round(points[index][0], 5), round(points[index][1], 5)] for index in sorted(keep)]


def _simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    """닫힌 Polygon ring을 단순화하고 유효한 최소 꼭짓점 수를 보존합니다."""
    if len(ring) < 5:
        return ring
    open_ring = ring[:-1] if ring[0] == ring[-1] else ring
    simplified = _simplify_open_line(open_ring, tolerance)
    if len(simplified) < 3:
        return ring
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def _simplify_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """분석용이 아닌 전국 지도 표시용 경계를 약 100m 허용오차로 가볍게 만듭니다."""
    simplified_features: list[dict[str, Any]] = []
    for feature in features:
        polygons = feature.get('geometry', {}).get('coordinates') or []
        simplified_polygons = [
            [_simplify_ring(ring, _MAP_SIMPLIFY_TOLERANCE) for ring in polygon]
            for polygon in polygons
        ]
        simplified_features.append({
            **feature,
            'geometry': {'type': 'MultiPolygon', 'coordinates': simplified_polygons},
        })
    return simplified_features


def _deduplicate_features(features: list[dict[str, Any]], code_field: str) -> list[dict[str, Any]]:
    """BBOX 경계에 걸쳐 두 번 응답된 동일 도형은 한 번만 남깁니다."""
    unique: dict[str, dict[str, Any]] = {}
    for feature in features:
        properties = feature.get('properties') or {}
        geometry = feature.get('geometry') or {}
        key = f"{properties.get(code_field, '')}:{json.dumps(geometry, ensure_ascii=False, separators=(',', ':'))}"
        unique[key] = feature
    return list(unique.values())


def _merge_region_features(
    features: list[dict[str, Any]],
    code_field: str,
    name_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    """섬·분리 지역 도형을 동일 행정구역 코드별 MultiPolygon 하나로 병합합니다."""
    grouped: dict[str, dict[str, Any]] = {}

    for feature in features:
        properties = feature.get('properties') or {}
        region_code = str(properties.get(code_field, ''))
        parts = _polygon_parts(feature.get('geometry'))
        if not region_code or not parts:
            continue

        if region_code not in grouped:
            region_name = next((properties.get(field) for field in name_fields if properties.get(field)), '이름 미확인 지역')
            grouped[region_code] = {
                'type': 'Feature',
                'properties': {'region_code': region_code, 'region_name': region_name},
                'geometry': {'type': 'MultiPolygon', 'coordinates': []},
            }

        grouped[region_code]['geometry']['coordinates'].extend(parts)

    return list(grouped.values())


async def _fetch_wfs_in_bounds(
    client: httpx.AsyncClient,
    base_url: str,
    params: dict[str, str],
    bounds: tuple[float, float, float, float],
    depth: int = 0,
) -> list[dict[str, Any]]:
    """
    VWorld WFS는 한 요청에 1,000개 도형까지만 응답합니다.
    BBOX를 반으로 나누어 전국의 섬 경계까지 빠짐없이 가져옵니다.
    EPSG:4326 WFS BBOX는 위도, 경도 순서입니다.
    """
    min_lat, min_lon, max_lat, max_lon = bounds
    bbox = f'{min_lat},{min_lon},{max_lat},{max_lon},EPSG:4326'
    response = await client.get(base_url, params={**params, 'BBOX': bbox})
    response.raise_for_status()
    payload = response.json()

    if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
        raise ValueError('VWorld WFS 응답이 GeoJSON FeatureCollection이 아닙니다.')

    total_features = int(payload.get('totalFeatures') or len(payload['features']))
    if total_features <= 1000:
        return payload['features']
    if depth >= 8:
        raise ValueError('행정구역 경계의 공간 분할 깊이가 너무 깊습니다.')

    # 더 긴 축을 분할하면 빈 요청 수를 줄이면서 1,000개 제한을 피할 수 있습니다.
    if (max_lon - min_lon) >= (max_lat - min_lat):
        mid_lon = (min_lon + max_lon) / 2
        first, second = (min_lat, min_lon, max_lat, mid_lon), (min_lat, mid_lon, max_lat, max_lon)
    else:
        mid_lat = (min_lat + max_lat) / 2
        first, second = (min_lat, min_lon, mid_lat, max_lon), (mid_lat, min_lon, max_lat, max_lon)

    left_features, right_features = await asyncio.gather(
        _fetch_wfs_in_bounds(client, base_url, params, first, depth + 1),
        _fetch_wfs_in_bounds(client, base_url, params, second, depth + 1),
    )
    return [*left_features, *right_features]


async def _get_boundary_collection(
    *,
    cache_key: str,
    layer_name: str,
    code_field: str,
    name_fields: tuple[str, ...],
) -> dict[str, Any]:
    """VWorld 레이어 하나를 조회·병합·캐시해 React에 전달할 GeoJSON으로 만듭니다."""
    now = datetime.now(timezone.utc)
    if cache_key in _cache and now < _cache_expires_at[cache_key]:
        return _cache[cache_key]

    async with _cache_lock:
        now = datetime.now(timezone.utc)
        if cache_key in _cache and now < _cache_expires_at[cache_key]:
            return _cache[cache_key]

        disk_collection = _read_disk_cache(cache_key, now)
        if disk_collection is not None:
            _cache[cache_key] = disk_collection
            _cache_expires_at[cache_key] = now + _CACHE_TTL
            return disk_collection

        settings = get_settings()
        if not settings.vworld_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={'code': 'VWORLD_KEY_MISSING', 'message': 'VWorld 지도 키가 서버 환경변수에 설정되지 않았습니다.'},
            )

        # 키는 이 서버에서만 VWorld에 전달되고, React가 받는 GeoJSON에는 포함되지 않습니다.
        params = {
            'key': settings.vworld_api_key,
            'domain': settings.vworld_domain,
            'service': 'WFS',
            'request': 'GetFeature',
            'version': '2.0.0',
            'typename': layer_name,
            'outputFormat': 'application/json',
            'srsName': 'EPSG:4326',
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                raw_features = await _fetch_wfs_in_bounds(client, settings.vworld_wfs_base_url, params, _KOREA_BOUNDS)
        except (httpx.HTTPError, ValueError) as exc:
            # 외부 URL·응답 전문을 브라우저로 전달하지 않아 키가 오류 메시지에 섞이지 않게 합니다.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={'code': 'VWORLD_BOUNDARY_UNAVAILABLE', 'message': '행정구역 경계 정보를 불러오지 못했습니다.'},
            ) from exc

        merged_features = _merge_region_features(_deduplicate_features(raw_features, code_field), code_field, name_fields)
        collection = {
            'type': 'FeatureCollection',
            'features': _simplify_features(merged_features),
        }
        _cache[cache_key] = collection
        _cache_expires_at[cache_key] = datetime.now(timezone.utc) + _CACHE_TTL
        _write_disk_cache(cache_key, collection)
        return collection


async def get_sido_boundaries() -> dict[str, Any]:
    """전국 시도 경계 레이어(lt_c_adsido)를 반환합니다."""
    # 시도 응답을 전국 시군구 응답에 의존시키지 않습니다. 시군구 GeoJSON은 훨씬 크므로
    # 세종 보완을 기다리면 첫 지도까지 함께 늦어집니다. 세종 보완은 두 응답을 이미 받는
    # React에서 비동기로 합쳐, 사용자가 시도 지도를 먼저 볼 수 있게 합니다.
    return await _get_boundary_collection(
        cache_key='sido',
        layer_name='lt_c_adsido',
        code_field='ctprvn_cd',
        name_fields=('ctp_kor_nm',),
    )


async def get_sigungu_boundaries() -> dict[str, Any]:
    """전국 시군구 경계 레이어(lt_c_adsigg)를 반환합니다."""
    return await _get_boundary_collection(
        cache_key='sigungu',
        layer_name='lt_c_adsigg',
        code_field='sig_cd',
        name_fields=('full_nm', 'sig_kor_nm'),
    )
