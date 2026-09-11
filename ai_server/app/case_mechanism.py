"""One operation-based classification for case retrieval and local evidence reads."""
from typing import Any


def case_mechanism_family(case: dict[str, Any]) -> str:
    # Do not classify by incidental risks, prerequisites, URLs or raw JSON keys.
    for field in ('intervention', 'operating_model', 'title', 'summary'):
        text = str(case.get(field) or '').lower()
        for tokens, family in (
            (('반값', '환급'), 'spend_conversion'),
            (('관광주민증', '회원', '재방문'), 'return_visit'),
            (('야간', '밤', '저녁'), 'night_time_experience'),
            (('숙박', '체크인', '숙소'), 'stay_conversion'),
            (('교통', 'ktx', '항공', '시티투어', '이동'), 'access_and_mobility'),
            (('예약', '재고', '시간대', '입장'), 'reservation_conversion'),
            (('할인', '쿠폰', '상품권', '결제'), 'spend_conversion'),
        ):
            if any(word in text for word in tokens):
                return family
    return 'other_operation'
