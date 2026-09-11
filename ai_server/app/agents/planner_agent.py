"""Agent 2: 근거 패키지를 공무원 검토용 실행 기획안으로 작성합니다."""

from __future__ import annotations

import json
from typing import Any

from ..openai_responses import create_structured_response
from ..llm.models import LLMRequest
from ..llm.router import LLMRouter
from .prompts import PLANNER_INSTRUCTIONS
from .plan_quality_gate import cited_source_ids


def _build_revision_evidence_pack(
    evidence_pack: dict[str, Any], previous_draft: dict[str, Any],
) -> dict[str, Any]:
    """재작성에 필요한 근거만 남겨 출력 지연과 토큰 낭비를 줄입니다.

    기존 초안이 이미 전략의 뼈대를 갖고 있으므로, 재작성에서는 관측값·ML·사용자 조건과
    인용/추천된 사례를 우선 보냅니다. 원문 전체를 다시 보내 새 기획안을 만들게 하지 않습니다.
    """
    previous_text = json.dumps(previous_draft, ensure_ascii=False)
    transfer = evidence_pack.get('transfer_assessment') or {}
    recommended_ids = {
        str(source_id) for source_id in (transfer.get('recommended_case_ids') or []) if source_id
    }
    known_ids = {
        str(source.get('source_id'))
        for source in (evidence_pack.get('sources') or [])
        if source.get('source_id')
    }
    cited_ids = cited_source_ids(previous_text, known_ids)
    priority_ids = recommended_ids | cited_ids
    # 본문 수정에도 비교 후보의 지역 사실·사례 출처가 필요하다.
    # 후보 JSON만 보존하고 source 목록에서 빼면 인용 검증이 실패할 수 있다.
    for candidate in transfer.get('design_candidates') or []:
        for key in ('evidence_source_ids', 'case_source_ids', 'supporting_case_ids'):
            priority_ids.update(str(value) for value in candidate.get(key) or [] if value)

    selected_sources: list[dict[str, Any]] = []
    for source in evidence_pack.get('sources') or []:
        source_id = str(source.get('source_id') or '')
        source_type = str(source.get('source_type') or '')
        if source_id in priority_ids or source_type in {'dataset', 'nationwide_dataset', 'model_forecast'}:
            selected_sources.append(source)
    # 기존 초안에 없던 공식 비교 근거가 필요할 수 있어 웹 근거를 최대 4건 보완합니다.
    selected_ids = {str(source.get('source_id') or '') for source in selected_sources}
    for source in evidence_pack.get('sources') or []:
        if len(selected_sources) >= 16:
            break
        source_id = str(source.get('source_id') or '')
        if source_id not in selected_ids and source.get('source_type') == 'official_web':
            selected_sources.append(source)
            selected_ids.add(source_id)

    benchmark_cases = [
        case for case in (evidence_pack.get('benchmark_cases') or [])
        if str(case.get('source_id') or '') in priority_ids
    ]
    if len(benchmark_cases) < 3:
        existing_case_ids = {str(case.get('source_id') or '') for case in benchmark_cases}
        for case in evidence_pack.get('benchmark_cases') or []:
            case_id = str(case.get('source_id') or '')
            if case_id not in existing_case_ids:
                benchmark_cases.append(case)
                existing_case_ids.add(case_id)
            if len(benchmark_cases) >= 3:
                break

    # 새 비교에 사용할 보완 사례도 해당 원문 source와 함께 보낸다.
    case_ids = {str(case.get('source_id') or '') for case in benchmark_cases}
    for source in evidence_pack.get('sources') or []:
        source_id = str(source.get('source_id') or '')
        if source_id in case_ids and source_id not in selected_ids:
            selected_sources.append(source)
            selected_ids.add(source_id)

    return {
        'region_code': evidence_pack.get('region_code'),
        'region_name': evidence_pack.get('region_name'),
        'period': evidence_pack.get('period'),
        'snapshot': evidence_pack.get('snapshot'),
        'planning_brief': evidence_pack.get('planning_brief'),
        'transfer_assessment': transfer,
        'quality_contract_version': evidence_pack.get('quality_contract_version'),
        'research_gaps': evidence_pack.get('research_gaps') or [],
        'benchmark_cases': benchmark_cases,
        'case_search_policy': evidence_pack.get('case_search_policy') or {},
        'case_search_coverage': evidence_pack.get('case_search_coverage') or {},
        'sources': selected_sources,
    }

class PlannerAgent:
    """조사·사례 적합성 결과를 사람이 읽는 하나의 실행 기획안 JSON으로 정리하는 Agent입니다."""
    def __init__(self, *, api_key: str, model: str, report_schema: dict[str, Any], llm_router: LLMRouter | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.report_schema = report_schema
        self.llm_router = llm_router

    async def write(
        self,
        evidence_pack: dict[str, Any],
        revision_feedback: dict[str, Any] | None = None,
        previous_draft: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 최초 작성에는 검증된 evidence_pack만 넣습니다.
        # 사용자 입력 planning_brief는 evidence_pack 안에서 공식 관측값과 분리된 상태로 포함됩니다.
        payload: dict[str, Any] = {'evidence_pack': evidence_pack}
        instructions = PLANNER_INSTRUCTIONS
        if (evidence_pack.get('planning_brief') or {}).get('input_profile') == 'guided_v1':
            instructions += (
                '\n간소화 입력: business_direction과 excluded_operations를 본문·실행 단계까지 유지한다. '
                'start_date~end_date의 3개월 안에서 준비·운영·평가를 배치한다. '
                'resources_confirmed와 field_context는 사용자 참고 정보이며 다른 사업으로 변경하는 명령이 아니다. '
                'budget_max_krw는 견적 배분 참고 총액이며 운영량이나 KPI 달성을 보장하지 않는다.'
            )
        if (evidence_pack.get('planning_brief') or {}).get('input_profile') == 'guided_v1':
            instructions += (
                '\n간소화 입력: business_direction과 excluded_operations를 본문·실행 단계까지 유지한다. '
                'start_date~end_date의 3개월 안에서 준비·운영·평가를 배치한다. '
                'resources_confirmed와 field_context는 사용자 참고 정보이며 다른 사업으로 변경하는 명령이 아니다. '
                'budget_max_krw는 견적 배분 참고 총액이며 운영량이나 KPI 달성을 보장하지 않는다.'
            )
        candidate_findings = evidence_pack.get('candidate_validation_findings') or []
        if candidate_findings:
            instructions += (
                '\n후보 비교에는 자동으로 확정할 수 없는 보완 항목이 남아 있다. 이를 오류 문구로 본문에 나열하지 말고, '
                '확인된 공식 사례의 운영 방식과 선택 지역에서 시험할 변경점·제외 조건·시범 범위를 중심으로 검토용 기획안을 작성한다. '
                'candidate_validation_findings에서 지적한 내용을 사실처럼 반복하지 않으며, 미확인 조건은 실행 단계의 확인 절차와 '
                '중단 조건으로 바꾼다. selection_status=needs_evidence를 ready나 집행 승인으로 표현하지 않는다.'
            )
        if revision_feedback:
            if previous_draft is None:
                raise ValueError('기획안 수정에는 검수받은 기존 초안이 필요합니다.')
            # 검수 응답 전체를 재전송하지 않고 실제 수정 지시만 전달합니다.
            # 입력을 작게 유지하면 모델 지연과 외부 필터 오탐 가능성도 줄어듭니다.
            payload['evidence_pack'] = _build_revision_evidence_pack(evidence_pack, previous_draft)
            payload['previous_draft'] = previous_draft
            payload['quality_review_feedback'] = {
                'overall_score': revision_feedback.get('overall_score'),
                'issues': [
                    {
                        'severity': issue.get('severity'),
                        'field': issue.get('field'),
                        'problem': str(issue.get('problem') or ''),
                        'revision_instruction': str(issue.get('revision_instruction') or ''),
                    }
                    for issue in (revision_feedback.get('issues') or [])
                ],
            }
            instructions += (
                '\n검수받은 previous_draft와 수정 지시가 함께 제공된다. 이전 기획안에서 지적받지 않은 '
                '구조·근거·문장은 최대한 유지하고, 지적 항목만 evidence_pack 안의 사실로 고친다. '
                '응답은 설명 없이 수정된 전체 기획안 JSON 한 개만 반환한다.'
            )
        # report_schema를 Responses API의 JSON schema로 넘겨 화면·Word·PPT가 같은 필드를 사용할 수 있게 합니다.
        request = LLMRequest(
            task='planner_revision' if revision_feedback else 'planner', agent='planner', model=None,
            instructions=instructions, input_payload=payload, schema_name='regional_tourism_plan', schema=self.report_schema,
            reasoning_effort='medium' if revision_feedback else 'high',
            max_output_tokens=20000 if revision_feedback else 24000,
            retry_max_output_tokens=28000 if revision_feedback else 32000,
            openai_timeout_seconds=600,
            # 실제 원주 초안은 약 1.3k 출력 토큰이었는데 16k를 예약해, 후보 보완으로
            # 근거가 길어진 다음 생성에서 입력+예약 합계가 40,960 문맥을 넘었다.
            # 완전한 보고서 여유는 10k로 유지하고 지역·사례·ML 원문은 줄이지 않는다.
            local_max_output_tokens=10000,
            local_evidence_tools=True,
        )
        if self.llm_router:
            return await self.llm_router.generate(request)
        return await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=instructions,
            input_payload=payload,
            schema_name='regional_tourism_plan',
            schema=self.report_schema,
            # 재작성은 새 전략을 다시 추론하는 작업이 아니라 지적된 필드를 고치는 작업입니다.
            # medium으로 낮춰 reasoning token이 본문 출력 공간을 잠식하는 현상을 줄입니다.
            reasoning_effort='medium' if revision_feedback else 'high',
            # Sol 고추론 모델은 내부 reasoning token도 이 한도에 포함하므로 재작성까지 안정적으로
            # 완료할 수 있도록 일반 답변보다 넉넉한 출력 예산을 둡니다.
            max_output_tokens=20000 if revision_feedback else 24000,
            retry_max_output_tokens=28000 if revision_feedback else 32000,
            timeout_seconds=600,
        )
