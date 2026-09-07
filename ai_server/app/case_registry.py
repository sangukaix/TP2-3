"""공식 관광사례 JSONL을 검증하고 읽는 공통 저장소입니다.

전국 월별 수치와 정책 사례 문서는 목적이 다릅니다. 이 모듈은 사람이 공식 URL과
성과 의미를 확인한 사례 카드만 다루며, 월별 지표나 LLM 생성 문장을 저장하지 않습니다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CuratedCaseCard(BaseModel):
    """Case Scout가 비교 가능한 최소 필드를 강제하는 검수 사례 한 건입니다."""

    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)
    source_id: str = Field(min_length=5, max_length=160)
    region_code: str = 'ALL'
    region_name: str = '전국 공통 사례'
    document_type: Literal['case_study', 'case_study_budget']
    case_region: str = Field(min_length=1, max_length=200)
    intervention: str = Field(min_length=1, max_length=300)
    problem_addressed: str = Field(min_length=1, max_length=500)
    target_group: str = Field(min_length=1, max_length=500)
    operating_model: str = Field(min_length=1, max_length=2000)
    duration: str = Field(min_length=1, max_length=300)
    public_budget: str = Field(min_length=1, max_length=500)
    observed_result: str = Field(min_length=1, max_length=1000)
    measurement_period: str = Field(min_length=1, max_length=500)
    evidence_strength: Literal['high', 'medium', 'low']
    transfer_conditions: list[str] = Field(min_length=1, max_length=8)
    risks: list[str] = Field(min_length=1, max_length=8)
    title: str = Field(min_length=1, max_length=500)
    source_url: str
    published_or_updated_at: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1, max_length=3000)

    @field_validator('source_url')
    @classmethod
    def validate_official_https_url(cls, value: str) -> str:
        """검색 결과 주소가 아니라 원문 HTTPS 주소만 사례 카드에 허용합니다."""
        if not value.startswith('https://'):
            raise ValueError('source_url은 공식 원문의 https:// 주소여야 합니다.')
        return value


def load_curated_case_registry(path: Path) -> list[dict[str, Any]]:
    """줄 번호를 포함해 JSONL을 검증하므로 잘못된 사례가 조용히 사용되지 않습니다."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            card = CuratedCaseCard.model_validate(value)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f'공식 사례 레지스트리 {line_number}번째 줄이 올바르지 않습니다: {exc}') from exc
        if card.source_id in seen_ids:
            raise ValueError(f'공식 사례 source_id가 중복되었습니다: {card.source_id}')
        seen_ids.add(card.source_id)
        records.append(card.model_dump(mode='json'))
    return records

