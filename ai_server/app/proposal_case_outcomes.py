"""Audited display evidence, linked to a selected source rather than a keyword.

This enriches exports only; it never changes saved selection, targets or forecasts.
Seoul's budget (printed p.83) explicitly lists Jung-gu Jeongdong Culture Night.
The two releases count that festival, not all Seoul tourists or causal impact.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'proposal_cases'
SEOUL_ATTACHMENT = 'c4638ecc9ce84bba9e51ecc2e11293e2'
BEFORE_URL = 'https://www.junggu.seoul.kr/content.do?cid=1235161279&cmsid=14390&mode=view'
AFTER_URL = 'https://www.junggu.seoul.kr/content.do?cid=1280957763&cmsid=14390&mode=view'
PHOTO_PAGE = 'https://culture.seoul.go.kr/culture/culture/cultureEvent/view.do?cultcode=146365&menuNo=200009'


def source_outcome(source):
    if source.get('festival_statistics'):
        stats = source.get('festival_statistics') or {}
        c = stats.get('comparison') or {}
        total = c.get('total') or {}
        if total.get('before', 0) > 0 and total.get('after') is not None:
            file = stats.get('source_file') or {}
            return {
                'title': f"{source.get('case_region', '')} · {stats.get('name', '')}",
                'scope': '관광데이터랩 축제 관측구역의 개최기간 방문 실적',
                'action': f"{stats.get('name', '')} · {c['before_days']}일→{c['after_days']}일 개최",
                'metric': '축제 관측구역 전체 방문자',
                'before': int(total['before']), 'after': int(total['after']),
                'before_label': f"{c['before_year']}년 · {c['before_days']}일",
                'after_label': f"{c['after_year']}년 · {c['after_days']}일",
                'before_note': f"외지인 {c['outside']['before']:,.0f}명",
                'after_note': f"외지인 {c['outside']['after']:,.0f}명",
                'interpretation': f"일평균 방문 {c['daily']['change_pct']:+.2f}%. 행사 방문 실적이며 도시 전체 순증·사업 단독 효과가 아닙니다.",
                'references': [(f"한국관광 데이터랩 다운로드 · {file.get('file_name', '')}", file['source_url'])],
                'photo': None, 'source_file': file,
                'verified_at': 'CSV 합계·일수·증감 산술 대조',
            }
    url = urlparse(str(source.get('source_url') or ''))
    query = parse_qs(url.query)
    context = ' '.join(str(source.get(k) or '') for k in ('case_region', 'intervention', 'title'))
    parent_match = (url.hostname == 'culture.seoul.go.kr'
                    and url.path == '/culture/cmmn/file/fileDown.do'
                    and query.get('atchFileId') == [SEOUL_ATTACHMENT]
                    and query.get('fileSn') == ['2']
                    and '서울' in context and '야간' in context
                    and ('문화유산' in context or '문화재' in context))
    event_match = (url.hostname == 'www.junggu.seoul.kr'
                   and query.get('cid', [''])[0] in ('1235161279', '1280957763'))
    if not (parent_match or event_match):
        return None
    return {
        'title': '서울 중구 · 정동야행',
        'scope': '선정한 서울 문화재야행 사업에 포함된 정동야행' if parent_match else '선정 사례 · 정동야행',
        'action': '역사·문화시설을 밤에도 개방하고, 공연과 체험을 함께 운영',
        'metric': '행사 방문객', 'before': 100_000, 'after': 130_000,
        'before_label': '2023년 · 10월 13–14일', 'after_label': '2024년 · 5월 24–25일',
        'before_note': '중구청 발표 · 약 10만 명', 'after_note': '중구청 발표 · 13만 명',
        'interpretation': '두 해의 행사 방문객 비교입니다. 개최 계절이 달라 사업 단독 효과로 해석하지 않습니다.',
        'references': [
            ('중구청 · 2023 정동야행 성공적 개최 (2023.10.15)', BEFORE_URL),
            ('중구청 · 2024 정동야행, 봄밤의 낭만 활짝 (2024.05.27)', AFTER_URL),
            ('서울문화포털 · 2024 정동야행 행사 내용과 사진', PHOTO_PAGE),
        ],
        'photo': {'path': ASSETS / 'jeongdong_2024.jpg', 'caption': '서울 중구 정동 · 정동야행 행사 사진',
                  'credit': '서울문화포털 · 2024 정동야행', 'page_url': PHOTO_PAGE,
                  'image_url': 'https://culture.seoul.go.kr/resources/culture/img/editor/culture/editor_20240530140505_47975.jpg',
                  'match_kind': 'documented_constituent_event', 'retrieved_at': '2026-09-15'},
        'parent_source': source.get('source_url') if parent_match else None,
        'parent_page': 83 if parent_match else None,
        'verified_at': '2026-09-15',
    }


def report_outcome(report):
    from .case_recommendation import report_cases
    _, primary = report_cases(report)
    if not primary:
        return None
    source = primary[0]
    result = source_outcome(source)
    if result:
        return result
    # Existing approved Gangjin result remains bound to a Gangjin selected case.
    basis = report.get('target_proposal_basis') or {}
    context = ' '.join(str(source.get(k) or '') for k in ('case_region', 'intervention', 'title'))
    if '강진' in context and ('반값' in context or '환급' in context) and basis.get('observed_visitors') == 2_480_000:
        from .case_images import case_image
        from .idea_proposal import CASE_URL
        return {
            'title': '전남 강진군 · 반값여행과 축제', 'scope': '반값여행과 축제가 함께 운영된 시기의 지역 관광 실적',
            'action': '여행 지출 일부를 지역상품권으로 환급하고, 축제와 연계해 방문을 유도',
            'metric': '10월 말 누적 관광객', 'before': 1_984_000, 'after': 2_480_000,
            'before_label': '2023년 · 같은 기간', 'after_label': '2024년 · 10월 말',
            'before_note': '역산 약 198.4만 명 · 248만 ÷ 1.25', 'after_note': '공식 발표 · 약 248만 명',
            'interpretation': '전년 값은 발표 증가율 25%로 역산했습니다. 반값여행만의 효과나 ML 전망 대비 증가율은 아닙니다.',
            'references': [('강진군의회 시정연설 (2024.11.20)', CASE_URL)],
            'photo': case_image(source), 'verified_at': '기존 보고서의 확인 근거',
        }
    return None


def outcome_references(report):
    result = report_outcome(report)
    return result['references'] if result else []
