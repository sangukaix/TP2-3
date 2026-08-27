"""선택 지역의 관광자원 맥락을 한국관광공사 국문관광정보 API에서 읽습니다."""

from __future__ import annotations

import re
from typing import Any

import httpx


def _normalize_name(value: str) -> str:
    value = re.sub(r'\s+', '', value)
    for suffix in ('특별자치시', '특별자치도', '특별시', '광역시'):
        value = value.replace(suffix, '')
    return value


class TourismOpenApiClient:
    """API 키를 브라우저에 노출하지 않는 서버 전용 읽기 클라이언트입니다."""

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip('/')

    async def _get(self, operation: str, **params: Any) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        query = {
            'serviceKey': self.api_key,
            'MobileOS': 'ETC',
            'MobileApp': 'TOUR_INSIGHT',
            '_type': 'json',
            'numOfRows': 100,
            'pageNo': 1,
            **params,
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(f'{self.base_url}/{operation}', params=query)
        response.raise_for_status()
        payload = response.json()
        header = ((payload.get('response') or {}).get('header') or {})
        if str(header.get('resultCode')) not in ('0000', '0', 'None'):
            raise ValueError(str(header.get('resultMsg') or '관광 Open API 응답 오류'))
        items = ((((payload.get('response') or {}).get('body') or {}).get('items') or {}).get('item') or [])
        if isinstance(items, dict):
            return [items]
        return items if isinstance(items, list) else []

    async def collect_region_resources(self, region_name: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """시도·시군구 코드를 API 자체에서 찾아 관광자원 목록을 수집합니다."""
        name_parts = region_name.split()
        if not name_parts:
            return []
        sido_name = _normalize_name(name_parts[0])
        sigungu_name = _normalize_name(''.join(name_parts[1:]))
        sido_rows = await self._get('areaCode2')
        sido = next((row for row in sido_rows if _normalize_name(str(row.get('name', ''))) == sido_name), None)
        if not sido:
            return []
        area_code = str(sido.get('code', ''))
        sigungu_code = ''
        if sigungu_name:
            sigungu_rows = await self._get('areaCode2', areaCode=area_code)
            sigungu = next((row for row in sigungu_rows if _normalize_name(str(row.get('name', ''))) == sigungu_name), None)
            if not sigungu:
                return []
            sigungu_code = str(sigungu.get('code', ''))

        resources = await self._get(
            'areaBasedList2',
            areaCode=area_code,
            sigunguCode=sigungu_code,
            arrange='O',
            numOfRows=limit,
        )
        return [
            {
                'source_id': f"tour-api:{item.get('contentid', index)}",
                'source_type': 'open_api',
                'title': str(item.get('title') or '관광자원'),
                'source_url': self.base_url,
                'content_id': str(item.get('contentid') or ''),
                'content_type_id': str(item.get('contenttypeid') or ''),
                'address': str(item.get('addr1') or ''),
                'image_url': str(item.get('firstimage') or ''),
                'summary': '한국관광공사 국문관광정보 API가 반환한 선택 지역 관광자원',
            }
            for index, item in enumerate(resources[:limit], start=1)
            if item.get('title')
        ]
