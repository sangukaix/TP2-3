"""Web images: exact case first, visibly attributed similar operation second."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'proposal_cases'
IMAGES = {
    'case:gangjin_half_price_2024': {
        'filename': 'gangjin_official.jpg', 'caption': '강진군 · 반값여행 공식 홍보물',
        'credit': '강진 반값여행 공식 홈페이지',
        'page_url': 'https://www.gangjintour.com/',
        'image_url': 'https://gangjintour.com/skin_hub/SKIN006/assets/img/gjimg.jpg',
    },
    'case:291a33370ec9b1': {
        'filename': 'incheon_official.jpg', 'caption': '인천 섬 · 로컬체험 여행 소개 사진',
        'credit': '인천광역시 섬포털',
        'page_url': 'https://isum.incheon.go.kr/theme/themeContent.do?key=2407020018',
        'image_url': 'https://isum.incheon.go.kr/resource/www/images/sub/theme_local.jpg',
    },
    'case:digital_tourism_resident_2024': {
        'filename': 'digital_official.jpg', 'caption': '전국 · 디지털 관광주민증 홍보물',
        'credit': '대한민국 정책브리핑 (2025)',
        'page_url': 'https://www.korea.kr/news/policyNewsView.do?newsId=148947084',
        'image_url': 'https://www.korea.kr/newsWeb/resources/attaches/2025.08/05/0805-1.jpg',
    },
}

SIMILAR_IMAGES = {
    'spend_conversion': IMAGES['case:gangjin_half_price_2024'],
    'stay_conversion': IMAGES['case:291a33370ec9b1'],
    'return_visit': IMAGES['case:digital_tourism_resident_2024'],
    'reservation_conversion': IMAGES['case:291a33370ec9b1'],
    'access_and_mobility': IMAGES['case:digital_tourism_resident_2024'],
    'night_time_experience': {
        'filename': 'yeosu_night.jpg', 'caption': '전남 여수시 야경',
        'credit': '문화체육관광부 코리아넷 (2024)',
        'page_url': 'https://www.korean-culture.org/koreanet/view.do?seq=1047457',
        'image_url': 'https://www.korean-culture.org/CONTENTS/editImage/20240201110349153_XHMYP6Q1.jpg',
    },
}


def case_image(source):
    from .case_mechanism import case_mechanism_family
    metadata = IMAGES.get(source.get('source_id'))
    kind='exact_case'
    if not metadata:
        family=case_mechanism_family(source)
        metadata=SIMILAR_IMAGES.get(family)
        kind='similar_operation'
    if not metadata:
        # General tourism reference is explicit, never portrayed as this case.
        metadata=SIMILAR_IMAGES['stay_conversion']
        kind='general_tourism_reference'
    path = ROOT / metadata['filename']
    prefix={'exact_case':'','similar_operation':'유사 사업 참고 · ',
            'general_tourism_reference':'관광 참고 이미지 · '}[kind]
    return {**metadata, 'caption':prefix+metadata['caption'], 'match_kind':kind,
            'path': path, 'retrieved_at': '2026-09-10'} if path.is_file() else None
