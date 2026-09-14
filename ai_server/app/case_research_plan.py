"""Build an auditable search brief from SQL peers and the selected ML window.

Peers guide discovery, not eligibility. No business-effect or regional-similarity
model is trained here; observed distances and forecast signals remain separate.
"""
from __future__ import annotations

from copy import deepcopy
import re

VERSION = 'regional-case-research-v1'
GROUPS = (
    ('visit', ('visitors', 'navigation_searches'), '관심을 방문·예약으로 연결한 운영'),
    ('stay', ('stay_minutes', 'lodging_nights', 'lodging_rate_pct', 'lodging_searches'), '체류·체험·숙박을 연결한 운영'),
    ('spend', ('spending_krw',), '지역 상권·콘텐츠 이용과 소비를 늘린 운영'),
)


def build_case_research_plan(snapshot: dict) -> dict:
    comparison = snapshot.get('nationwide_comparison') or {}
    ml = snapshot.get('ml_analysis') or {}
    signals = [deepcopy(s) for s in ml.get('signals') or [] if s.get('kind') == 'forecast_signal']
    peers = deepcopy(comparison.get('peer_regions') or []) if comparison.get('available') else []
    groups = []
    for key, metrics, question in GROUPS:
        values = [s for s in signals if s.get('metric') in metrics]
        changes = [s['change_percent'] for s in values if isinstance(s.get('change_percent'), (int, float))]
        groups.append({'id': key, 'question': question, 'signals': values,
                       'search_priority_change_pct': sum(changes) / len(changes) if changes else None})
    # Lower forecast change first is a transparent search ordering, not an impact score.
    groups.sort(key=lambda g: (g['search_priority_change_pct'] is None, g['search_priority_change_pct'] or 0))
    latest = str(ml.get('latest_observed_month') or snapshot.get('period') or '')[:4]
    years = list(range(int(latest) - 3, int(latest) + 1)) if latest.isdigit() else []
    period = ' '.join(map(str, years))
    tasks = [{'region_code': p.get('region_code'), 'region_name': p.get('region_name'),
              'reason': '동일 기간 관광 관측지표 거리로 찾은 우선 조사 지역',
              'comparison': p,
              'query': f"{p.get('region_name', '')} {period} 관광사업 성과평가 방문객 관광소비 전년 운영 결과"}
             for p in peers[:5]]
    tasks.extend({'region_code': None, 'region_name': '전국 확장',
                  'reason': '유사지역 목록 밖의 성공 운영도 비교; 지역 조건의 차이는 적용 설계에서 조정',
                  'query': f"전국 {period} {g['question']} 관광사업 성과평가 전후 비교"}
                 for g in groups)
    return {'version': VERSION, 'selected_region': snapshot.get('region_name'),
            'peer_method': comparison.get('method'), 'peer_period': comparison.get('period'),
            'selected_observed_profile': deepcopy(comparison.get('selected_region') or {}),
            'peer_source_ids': comparison.get('source_ids') or [],
            'signal_groups': groups, 'search_tasks': tasks,
            'eligibility': 'peer는 검색 우선순위이며 필수 일치 조건이 아니다. 일부 조건이 다른 지역의 운영도 비교한다.',
            'comparison_contract': [
                '실제 지역과 사업명이 있는 서로 다른 운영 사례를 우선 3건 이상 조사한다. 없는 사례는 만들지 않는다.',
                '사업 시행연도·운영방식·시행 전후 동일기간 방문/소비 수치와 각 원문 URL을 확인한다.',
                '성과 미확인 운영 사례와 수치가 확인된 성과 사례를 구분한다. 전후 증가는 사업 단독 효과가 아니다.',
                '선택 지역의 관측/ML 신호 → 사례 운영과 실적 → 공통점/차이 → 바꿀 운영조건 → 대안보다 선택한 이유를 연결한다.',
                'ML이 약한 지표는 관측 자료와 함께 해석한다. 인구·지리·교통은 확인된 별도 근거가 있을 때만 비교한다.',
            ]}


def comparison_coverage(cases: list[dict]) -> dict:
    """Minimum diversity of evidence, deliberately no exact-peer requirement."""
    from .case_scope import _location_parts
    from .case_recommendation import budget_only
    from .case_mechanism import case_mechanism_family
    usable = [c for c in cases if c.get('source_url') and c.get('operating_model') and not budget_only(c)]
    locations = set()
    city_provinces = {'서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종'}
    for card in usable:
        province, local = _location_parts(card.get('case_region'))
        if not province:
            continue
        # '인천 전역' / '인천 송도·월미도'는 다른 지역이 아니다.
        # 도에서는 첫 시·군, 광역시에서는 명시된 구·군까지만 비교 단위로 쓴다.
        unit = re.match(r'^([가-힣]+(?:시|군|구))(?=$|[\s(·,/])', local)
        if unit:
            locations.add((province, unit.group(1)))
        elif province in city_provinces:
            locations.add((province, ''))
    # 광역시 전체와 그 안의 구를 함께 가져왔어도 독립 지역 둘로 세지 않는다.
    locations = {(province, local) for province, local in locations
                 if not local or (province, '') not in locations}
    families = {case_mechanism_family(c) for c in usable} - {'other_operation'}
    return {'concrete_region_count': len(locations), 'operation_family_count': len(families),
            'sufficient_for_comparison': len(locations) >= 2 and len(families) >= 2,
            'rule': '시·군 또는 명시된 광역시 구·군 단위로 중복을 제거한다. 광역시 전체와 포함 구는 중복 집계하지 않는다. 지역 완전 일치는 요구하지 않는다. 최소 2개 실제 지역·2개 운영 원리를 비교; 성과의 사실성은 별도 검수.'}
