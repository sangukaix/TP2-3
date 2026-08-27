"""OpenAI API 잔액이 없을 때 화면 구조를 검증하는 원자료 기반 오프라인 샘플입니다.

이 파일은 LLM을 흉내 내는 대체 운영 기능이 아닙니다. 실제 데이터 수치와 미리 정한
문장 규칙만 사용하며, 공식 웹 조사·RAG·AI 품질 검수를 수행했다고 표시하지 않습니다.
"""

from __future__ import annotations

from typing import Any


def _observation(snapshot: dict[str, Any], metric: str) -> dict[str, Any] | None:
    return next((item for item in snapshot.get('observations', []) if item.get('metric') == metric), None)


def _source_items(region_code: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'source_id': f'offline-dataset:{region_code}:{index}',
            'source_type': 'dataset',
            'title': str(item.get('source') or '한국관광 데이터랩 원자료'),
            'source_url': 'https://datalab.visitkorea.or.kr/',
            'summary': f"{item.get('metric')}: {item.get('value')}",
            'observation_period': item.get('period') or snapshot.get('latest_month', ''),
            'published_or_updated_at': item.get('period') or snapshot.get('latest_month', ''),
        }
        for index, item in enumerate(snapshot.get('observations', []), start=1)
    ]


def build_offline_sample_report(region_code: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """선택 지역의 실제 snapshot을 기존 ReportResponse 형식으로 조립합니다."""
    region_name = str(snapshot['region_name'])
    latest_month = str(snapshot['latest_month'])
    visitors = _observation(snapshot, '월간 순 방문자 수') or {}
    spending = _observation(snapshot, '월간 외지인 관광소비 총액') or {}
    lodging_rate = _observation(snapshot, '외지인 숙박 방문 비율') or {}
    lodging_nights = _observation(snapshot, '외지인 평균 숙박일수') or {}
    navigation = _observation(snapshot, '내비게이션 목적지 검색량') or {}

    comparison = snapshot.get('regional_comparison') or {}
    gaps = comparison.get('selected_gap_from_peer_average') or {}
    scope = comparison.get('scope') or '동일 기준 원본 보유 지역'
    comparison_period = comparison.get('period') or snapshot.get('period')
    visitor_gap = gaps.get('visitors_percent')
    spending_gap = gaps.get('spending_percent')
    lodging_gap = gaps.get('lodging_rate_percentage_points')
    comparison_text = (
        f"{comparison_period} {scope} 비교에서 방문자 수는 평균 대비 {visitor_gap:+.1f}%, "
        f"관광소비액은 {spending_gap:+.1f}%, 숙박 방문 비율은 {lodging_gap:+.1f}%p입니다."
        if comparison.get('available') and all(value is not None for value in (visitor_gap, spending_gap, lodging_gap))
        else '같은 기간·같은 기준으로 비교할 지역 원본이 충분하지 않아 선택 지역의 월별 변화만 사용했습니다.'
    )

    categories = [item for item in snapshot.get('consumption_by_category', []) if item.get('category') not in {'운송업', '전체'}]
    focus_categories = '·'.join(str(item['category']) for item in categories[:2]) or '지역 관광소비 업종'
    evidence_sources = _source_items(region_code, snapshot)
    source_ids = [item['source_id'] for item in evidence_sources]

    return {
        'generation_mode': 'offline_sample',
        'summary': (
            f"{region_name}는 {latest_month} 순 방문자 {visitors.get('value', '자료 없음')}, "
            f"외지인 관광소비 {spending.get('value', '자료 없음')} 규모입니다. "
            f"방문을 {focus_categories} 소비와 체류로 연결하는 3~6개월 시범사업을 제안합니다."
        ),
        'region_name': region_name,
        'period': snapshot['period'],
        'metrics_count': len(snapshot.get('observations', [])),
        'observed_findings': [
            {
                'metric': str(item.get('metric')),
                'value': str(item.get('value')),
                'interpretation': '선택 지역 공식 원자료의 최신 월 관측값입니다.',
                'source': str(item.get('source')),
            }
            for item in snapshot.get('observations', [])[:7]
        ],
        'monthly_trend': snapshot['monthly_trend'],
        'strategies': [{
            'priority': 1,
            'timeframe': '3~6개월 시범 운영',
            'title': '방문을 지역 소비로 연결하는 반나절 관광코스 시범사업',
            'problem_to_solve': (
                f"최근 방문 규모만으로는 지역 안에서 충분한 소비와 체류가 이어졌다고 보기 어렵습니다. "
                f"숙박 방문 비율은 {lodging_rate.get('value', '자료 없음')}, 평균 숙박일수는 {lodging_nights.get('value', '자료 없음')}입니다."
            ),
            'comparison_analysis': comparison_text,
            'solution': (
                f"내비게이션 검색 {navigation.get('value', '자료 없음')}을 출발 수요로 보고, "
                f"검색이 많은 지점과 {focus_categories} 참여 업소를 3~4시간 동선으로 연결합니다. "
                '처음에는 한 개 코스만 운영하고 이용률과 결제 변화를 확인해 확대 여부를 결정합니다.'
            ),
            'implementation_steps': [
                {'step': 1, 'schedule': '1~2주', 'task': '최근 12개월 방문·소비·검색 자료에서 후보 권역 1곳 선정', 'deliverable': '후보 권역 선정표'},
                {'step': 2, 'schedule': '3~4주', 'task': f'{focus_categories} 참여 업소와 관광 지점을 연결한 도보·대중교통 동선 설계', 'deliverable': '시범코스 지도와 참여 기준'},
                {'step': 3, 'schedule': '2개월차', 'task': '모바일 안내 페이지와 공통 혜택을 준비하고 참여 업소 운영 교육', 'deliverable': '안내 페이지와 운영 매뉴얼'},
                {'step': 4, 'schedule': '3~4개월차', 'task': '주말 중심으로 시범 운영하고 이용 건수·업종별 소비·체류 반응 기록', 'deliverable': '월간 운영 결과표'},
                {'step': 5, 'schedule': '5~6개월차', 'task': '운영 전후 같은 달 지표를 비교해 유지·수정·확대 결정', 'deliverable': '성과 비교표와 다음 운영안'},
            ],
            'expected_effect': '방문자가 지역 안에서 이동하고 소비할 이유를 명확히 만들며, 실제 운영 결과를 바탕으로 확대 여부를 판단할 수 있습니다.',
            'budget': '안내 페이지, 홍보물, 참여 업소 운영 지원, 성과 측정 항목별로 수량을 정한 뒤 2개 이상 비교견적으로 산정합니다.',
            'kpi': '코스 이용 건수, 참여 업소 결제 건수, 외지인 관광소비액, 숙박 방문 비율을 운영 전후 같은 기준으로 확인합니다.',
            'evidence': ', '.join(source_ids),
            'visual_asset_source_ids': [],
        }],
        'limitations': ['오프라인 화면 테스트용 규칙 기반 샘플이며 실시간 공식 웹 조사와 OpenAI 품질 검수를 수행하지 않았습니다.'],
        'quality_review': {
            'approved': False,
            'overall_score': None,
            'summary': '오프라인 테스트 결과이므로 AI Reviewer 평가 대상이 아닙니다.',
            'revised_once': False,
        },
        'evidence_sources': evidence_sources,
        'research_gaps': ['공식 웹 조사·RAG·OpenAI 검수는 API 크레딧 충전 후 실행됩니다.'],
        'agent_trace': [{'agent': 'offline_sample', 'stage': 'local_snapshot', 'status': 'completed'}],
    }
