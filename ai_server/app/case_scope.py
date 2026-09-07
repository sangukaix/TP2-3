"""전국 사례의 탐색 범위. 지역 사실/ML 조인이나 정책 효과 계산은 하지 않는다."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re
from typing import Any, Callable


CASE_SCOPE_VERSION = 'nationwide-case-scope-v1'
CASE_DOCUMENT_TYPES = ('case_study', 'case_study_budget')
PROVINCE_ALIASES = {
    '서울': ('서울특별시', '서울시', '서울'), '부산': ('부산광역시', '부산시', '부산'),
    '대구': ('대구광역시', '대구시', '대구'), '인천': ('인천광역시', '인천시', '인천'),
    '광주': ('광주광역시', '광주시', '광주'), '대전': ('대전광역시', '대전시', '대전'),
    '울산': ('울산광역시', '울산시', '울산'), '세종': ('세종특별자치시', '세종시', '세종'),
    '경기': ('경기도', '경기'), '강원': ('강원특별자치도', '강원도', '강원'),
    '충북': ('충청북도', '충북'), '충남': ('충청남도', '충남'),
    '전북': ('전북특별자치도', '전라북도', '전북'), '전남': ('전라남도', '전남'),
    '경북': ('경상북도', '경북'), '경남': ('경상남도', '경남'),
    '제주': ('제주특별자치도', '제주도', '제주'),
}


def _location_parts(value: Any) -> tuple[str, str]:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    for province, aliases in PROVINCE_ALIASES.items():
        for alias in aliases:
            if text == alias or text.startswith(alias + ' '):
                return province, text[len(alias):].strip()
    return '', text


def _mentions_location(text: str, name: str) -> bool:
    """검수 카드의 소재지 표시만 대조한다. 애매한 중구/서구 단독 이름은 매칭하지 않는다."""
    province, local = _location_parts(name)
    if not province or not local:
        return False
    return any(re.search(r'(?<![가-힣])' + re.escape(alias) + r'\s+' + re.escape(local)
                         + r'(?![가-힣])', text)
               for alias in PROVINCE_ALIASES[province])


def build_case_search_policy(snapshot: dict[str, Any]) -> dict[str, Any]:
    comparison = snapshot.get('nationwide_comparison') or {}
    peers = (comparison.get('peer_regions') or []) if comparison.get('available') else []
    region_name = str(snapshot.get('region_name') or '')
    province, _ = _location_parts(region_name)
    return {
        'version': CASE_SCOPE_VERSION,
        'selected_region': region_name, 'selected_province': province,
        'search_scope': 'nationwide',
        'review_order': ['same_province', 'cross_province_peer', 'national_mechanism'],
        'cross_province_review': 'always',
        'peer_regions': [{key: peer.get(key) for key in ('region_code', 'region_name', 'rank')}
                         for peer in peers],
        'peer_period': comparison.get('period') if comparison.get('available') else None,
        # 현재 peer 계산에는 주민등록 인구가 없다. 방문자를 주민 수로 바꾸지 않는다.
        'resident_population_comparison': 'not_available_in_current_peer_features',
        'rule': '같은 시도는 우선 탐색할 맥락이지 제한이 아니다. 전국 사례의 운영 방식·수요·예산·접근성 차이를 검토하고, 인구 유사성이나 성과 이전을 추정하지 않는다.',
    }


def case_relation(card: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    text = str(card.get('case_region') or card.get('region_name') or '')
    policy = build_case_search_policy(snapshot)
    province, _ = _location_parts(text)
    selected_province = policy['selected_province']
    peer = next((row for row in policy['peer_regions']
                 if _mentions_location(text, str(row.get('region_name') or ''))), None)
    # region_code=ALL은 RAG 검색 범위일 수 있어 사업 소재지로 사용하지 않는다.
    if _mentions_location(text, policy['selected_region']):
        scope = 'selected_region'
    elif province and province == selected_province:
        scope = 'same_province'
    elif peer:
        scope = 'cross_province_peer'
    elif province and selected_province:
        scope = 'cross_province'
    else:
        scope = 'national_or_unresolved'
    return {'scope': scope, 'peer_region_code': peer.get('region_code') if peer else None}


def select_case_cards(cards: list[dict[str, Any]], snapshot: dict[str, Any], *,
                      mechanism_key: Callable[[dict[str, Any]], str], limit: int = 8
                      ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """검수 원문을 자르지 않고 작은 비교 후보군을 선정. 이것은 적합성/효과 점수가 아니다."""
    unique: dict[str, dict[str, Any]] = {}
    for card in cards:
        key = str(card.get('source_url') or card.get('source_id') or '')
        if key:
            unique.setdefault(key, deepcopy(card))
    rows = list(unique.values())
    for row in rows:
        row['retrieval_context'] = case_relation(row, snapshot)
    scope_order = {'selected_region': 0, 'same_province': 1, 'cross_province_peer': 2,
                   'cross_province': 3, 'national_or_unresolved': 4}
    rows.sort(key=lambda row: (scope_order[row['retrieval_context']['scope']],
                              {'high': 0, 'medium': 1, 'low': 2}.get(row.get('evidence_strength'), 3),
                              str(row.get('source_id') or '')))
    chosen: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> None:
        if len(chosen) < limit and row not in chosen:
            chosen.append(row)

    # 인근 사례가 많아도 타시도 peer·새 운영 원리의 사례가 Top-K에서 모두 밀리지 않게 한다.
    for group in ({'selected_region', 'same_province'}, {'cross_province_peer'},
                  {'cross_province', 'national_or_unresolved'}):
        candidate = next((row for row in rows if row['retrieval_context']['scope'] in group), None)
        if candidate:
            add(candidate)
    for row in rows:
        if mechanism_key(row) not in {mechanism_key(item) for item in chosen}:
            add(row)
    for row in rows:
        add(row)
    counts = dict(Counter(row['retrieval_context']['scope'] for row in rows))
    coverage = {'catalog_candidates': len(rows), 'selected_candidates': len(chosen),
                'excluded_candidates': len(rows) - len(chosen), 'scope_counts': counts,
                'selected_source_ids': [row['source_id'] for row in chosen]}
    return chosen, coverage


def nationwide_case_query(snapshot: dict[str, Any]) -> str:
    """무료 검색의 두 번째 슬롯은 항상 타 시도/전국으로 열어 둔다."""
    policy = build_case_search_policy(snapshot)
    peers = [row['region_name'] for row in policy['peer_regions']
             if _location_parts(row.get('region_name'))[0] != policy['selected_province']]
    names = ' '.join(peers[:2])
    return f'전국 {names} 관광사업 운영 방식 예산 성과평가 유사 지역 사례 공식'.strip()
