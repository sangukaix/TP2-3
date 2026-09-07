"""Agent 3: 기획안의 근거성·실행성·간결성·시각자료 적합성을 검토합니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from ..llm.models import LLMRequest
from ..llm.router import LLMRouter
from .prompts import REVIEW_INSTRUCTIONS


# OpenAI가 자유 문장 대신 검토 점수·문제·수정 지시를 항상 같은 JSON 구조로 반환하게 하는 계약입니다.
# 프런트엔드는 이 결과를 직접 보여 주기보다, 필요할 때 Planner 재작성에만 사용합니다.
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
    """완성 초안이 근거·사례·사용자 조건을 지켰는지 마지막으로 검사하는 Agent입니다."""
    def __init__(self, *, api_key: str, model: str, llm_router: LLMRouter | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.llm_router = llm_router

    async def review(
        self,
        *,
        evidence_pack: dict[str, Any],
        draft_report: dict[str, Any],
        deterministic_precheck: dict[str, Any] | None = None,
        final_pass: bool = False,
    ) -> dict[str, Any]:
        # evidence_pack 원본과 Planner 초안을 함께 보내야 ‘그럴듯하지만 근거 없는 문장’을 비교해 걸러낼 수 있습니다.
        # 점수가 낮으면 오케스트레이터가 이 응답의 issue만 Planner에게 전달해 한 번 재작성합니다.
        request = LLMRequest(
            task='final_reviewer' if final_pass else 'reviewer', agent='reviewer', model=None, instructions=REVIEW_INSTRUCTIONS,
            input_payload={
                'evidence_pack': evidence_pack, 'draft_report': draft_report,
                'deterministic_precheck': deterministic_precheck or {'checked': False, 'issues': []},
            }, schema_name='tourism_plan_quality_review', schema=REVIEW_SCHEMA,
            # 검수 추론 강도는 낮추지 않고 완결된 판정을 반환할 출력 공간을 늘립니다.
            reasoning_effort='high', max_output_tokens=12000,
            retry_max_output_tokens=20000, openai_timeout_seconds=600, local_max_output_tokens=5500,
            local_evidence_tools=bool(getattr(self.llm_router, 'local_first', False) and not final_pass),
        )
        if self.llm_router:
            return await self.llm_router.generate(request)
        return await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=REVIEW_INSTRUCTIONS,
            # 코드가 확인한 기계적 오류도 함께 주어, Reviewer가 사실성·문장 품질 검토에 집중하게 합니다.
            input_payload={
                'evidence_pack': evidence_pack,
                'draft_report': draft_report,
                'deterministic_precheck': deterministic_precheck or {'checked': False, 'issues': []},
            },
            schema_name='tourism_plan_quality_review',
            schema=REVIEW_SCHEMA,
            reasoning_effort='high',
            max_output_tokens=12000, retry_max_output_tokens=20000, timeout_seconds=600,
        )
