"""Agent 3: 기획안의 근거성·실행성·간결성·시각자료 적합성을 검토합니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from .prompts import REVIEW_INSTRUCTIONS


REVIEW_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'approved': {'type': 'boolean'},
        'overall_score': {'type': 'integer', 'minimum': 0, 'maximum': 100},
        'dimension_scores': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'evidence_validity': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'comparison_quality': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'implementation_detail': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'clarity_and_brevity': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'public_official_usefulness': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'visual_material_readiness': {'type': 'integer', 'minimum': 0, 'maximum': 100},
            },
            'required': [
                'evidence_validity',
                'comparison_quality',
                'implementation_detail',
                'clarity_and_brevity',
                'public_official_usefulness',
                'visual_material_readiness',
            ],
        },
        'strengths': {'type': 'array', 'minItems': 1, 'maxItems': 5, 'items': {'type': 'string'}},
        'issues': {
            'type': 'array',
            'maxItems': 8,
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'severity': {'type': 'string', 'enum': ['critical', 'major', 'minor']},
                    'field': {'type': 'string'},
                    'problem': {'type': 'string'},
                    'revision_instruction': {'type': 'string'},
                },
                'required': ['severity', 'field', 'problem', 'revision_instruction'],
            },
        },
        'summary': {'type': 'string'},
    },
    'required': ['approved', 'overall_score', 'dimension_scores', 'strengths', 'issues', 'summary'],
}

class ReviewerAgent:
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def review(self, *, evidence_pack: dict[str, Any], draft_report: dict[str, Any]) -> dict[str, Any]:
        return await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=REVIEW_INSTRUCTIONS,
            input_payload={'evidence_pack': evidence_pack, 'draft_report': draft_report},
            schema_name='tourism_plan_quality_review',
            schema=REVIEW_SCHEMA,
            reasoning_effort='high',
            max_output_tokens=5500,
        )
