"""Agent 2: 근거 패키지를 공무원 검토용 실행 기획안으로 작성합니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from .prompts import PLANNER_INSTRUCTIONS

class PlannerAgent:
    def __init__(self, *, api_key: str, model: str, report_schema: dict[str, Any]) -> None:
        self.api_key = api_key
        self.model = model
        self.report_schema = report_schema

    async def write(self, evidence_pack: dict[str, Any], revision_feedback: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {'evidence_pack': evidence_pack}
        instructions = PLANNER_INSTRUCTIONS
        if revision_feedback:
            # 검수 응답 전체를 재전송하지 않고 실제 수정 지시만 전달합니다.
            # 입력을 작게 유지하면 모델 지연과 외부 필터 오탐 가능성도 줄어듭니다.
            payload['quality_review_feedback'] = {
                'overall_score': revision_feedback.get('overall_score'),
                'issues': [
                    {
                        'severity': issue.get('severity'),
                        'field': issue.get('field'),
                        'revision_instruction': str(issue.get('revision_instruction') or '')[:600],
                    }
                    for issue in (revision_feedback.get('issues') or [])
                ],
            }
            instructions += (
                '\n이전 기획안의 품질 검토 결과가 함께 제공된다. 근거 패키지 밖의 사실을 추가하지 말고, '
                '검토에서 지적한 항목만 정확히 고쳐 전체 기획안을 다시 작성한다.'
            )
        return await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=instructions,
            input_payload=payload,
            schema_name='regional_tourism_plan',
            schema=self.report_schema,
            reasoning_effort='high',
            # Sol 고추론 모델은 내부 reasoning token도 이 한도에 포함하므로 재작성까지 안정적으로
            # 완료할 수 있도록 일반 답변보다 넉넉한 출력 예산을 둡니다.
            max_output_tokens=16000,
        )
