"""공식 사례 JSONL의 필수 필드·URL·중복 ID를 OpenAI 호출 없이 점검합니다."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..case_registry import load_curated_case_registry


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    path = project_root / 'data' / 'rag' / 'official_case_studies.jsonl'
    cards = load_curated_case_registry(path)
    regions = Counter(card['case_region'] for card in cards)
    print(f'검증 완료: {len(cards)}건 | 지역 {len(regions)}개 | 파일 {path.relative_to(project_root)}')
    for card in cards:
        print(f"- {card['source_id']} | {card['case_region']} | {card['title']}")


if __name__ == '__main__':
    main()

