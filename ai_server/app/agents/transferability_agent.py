"""Agent 3: 공식 사례를 선택 지역에 적용할 수 있는지 평가하고 시범사업 구조를 만듭니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from .prompts import TRANSFERABILITY_INSTRUCTIONS


TRANSFERABILITY_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'diagnosis_summary': {'type': 'string'},
        'candidate_assessments': {
            'type': 'array',
            'maxItems': 5,
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'case_source_id': {'type': 'string'},
                    'fit_score': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                    'evidence_score': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                    'similarity_reason': {'type': 'string'},
                    'adaptation': {'type': 'string'},
                    'rejection_risks': {'type': 'array', 'maxItems': 4, 'items': {'type': 'string'}},
                    'validation_plan': {'type': 'string'},
                },
                'required': [
                    'case_source_id', 'fit_score', 'evidence_score', 'similarity_reason', 'adaptation',
                    'rejection_risks', 'validation_plan',
                ],
            },
        },
        'recommended_case_ids': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string'}},
        'strategy_brief': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'working_title': {'type': 'string'},
                'target_problem': {'type': 'string'},
                'mechanism': {'type': 'string'},
                'target_users': {'type': 'string'},
                'pilot_scope': {'type': 'string'},
                'budget_formula': {'type': 'string'},
                'success_metrics': {'type': 'string'},
                'stop_or_scale_rule': {'type': 'string'},
                'supporting_case_ids': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string'}},
            },
            'required': [
                'working_title', 'target_problem', 'mechanism', 'target_users', 'pilot_scope',
                'budget_formula', 'success_metrics', 'stop_or_scale_rule', 'supporting_case_ids',
            ],
        },
    },
    'required': ['diagnosis_summary', 'candidate_assessments', 'recommended_case_ids', 'strategy_brief'],
}


class TransferabilityAgent:
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def assess(self, *, evidence_pack: dict[str, Any]) -> dict[str, Any]:
        cases = evidence_pack.get('benchmark_cases') or []
        if not cases:
            return {
                'diagnosis_summary': '공식 성공사례가 충분하지 않아 지역 적합성 비교를 수행하지 못했습니다.',
                'candidate_assessments': [],
                'recommended_case_ids': [],
                'strategy_brief': {
                    'working_title': '공식 사례 추가 조사 필요',
                    'target_problem': '선택 지역 원자료에서 확인된 지표만 사용',
                    'mechanism': '근거 사례 확보 전에는 특정 쿠폰·행사 효과를 가정하지 않음',
                    'target_users': '선택 지역 방문객',
                    'pilot_scope': '사례 조사 후 결정',
                    'budget_formula': '비용 항목 × 수량 × 공식 단가 또는 비교견적',
                    'success_metrics': '방문자 수·관광소비액·숙박 방문 비율의 운영 전후 비교',
                    'stop_or_scale_rule': '공식 근거와 측정 설계가 확보되지 않으면 집행하지 않음',
                    'supporting_case_ids': [],
                },
            }
        return await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=TRANSFERABILITY_INSTRUCTIONS,
            input_payload={
                'region_code': evidence_pack.get('region_code'),
                'region_name': evidence_pack.get('region_name'),
                'period': evidence_pack.get('period'),
                'snapshot': evidence_pack.get('snapshot'),
                'benchmark_cases': cases,
            },
            schema_name='tourism_case_transferability',
            schema=TRANSFERABILITY_SCHEMA,
            reasoning_effort='high',
            max_output_tokens=9000,
        )
