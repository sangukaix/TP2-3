"""Agent 3: 공식 사례를 선택 지역에 적용할 수 있는지 평가하고 시범사업 구조를 만듭니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from .prompts import TRANSFERABILITY_INSTRUCTIONS


# 타 지역 성공사례를 그대로 복사하지 않도록, ‘우리 지역에 적용 가능한 이유·위험·검증 방식’을 따로 받는 JSON 계약입니다.
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
    """사례의 효과를 보장하지 않고, 선택 지역에서 시험할 수 있는 조건부 시범사업으로 바꾸는 Agent입니다."""
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def assess(self, *, evidence_pack: dict[str, Any]) -> dict[str, Any]:
        # 공식 사례가 하나도 없으면 모델에게 내용을 지어내게 하지 않고, 안전한 ‘추가 조사 필요’ 결과를 즉시 반환합니다.
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
        # 선택 지역 snapshot, 사용자 여건, 사례 카드만 전달합니다.
        # 실제 수치 계산은 ML·원자료 계층이 담당하고 이 Agent는 적용 판단만 담당합니다.
        return await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=TRANSFERABILITY_INSTRUCTIONS,
            input_payload={
                'region_code': evidence_pack.get('region_code'),
                'region_name': evidence_pack.get('region_name'),
                'period': evidence_pack.get('period'),
                'snapshot': evidence_pack.get('snapshot'),
                'planning_brief': evidence_pack.get('planning_brief'),
                'benchmark_cases': cases,
            },
            schema_name='tourism_case_transferability',
            schema=TRANSFERABILITY_SCHEMA,
            # 후보 사례를 새로 조사하는 단계가 아니라 이미 수집된 사례를 정해진 6개 기준으로
            # 비교하는 단계입니다. medium이면 구조화 판단 품질을 유지하면서 장시간 timeout을 줄입니다.
            reasoning_effort='medium',
            max_output_tokens=7000,
        )
