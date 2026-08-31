"""선택 지역의 분석 결과와 기획안을 대화로 설명·수정하는 AI 보조 Agent입니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from .evidence_agent import _url_is_allowed, allowed_domains
from .prompts import PLANNING_CONTEXT_RULES


ASSISTANT_CHAT_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'answer': {'type': 'string'},
        'mode': {'type': 'string', 'enum': ['explain', 'research', 'revise']},
        'key_points': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
        'sources': {
            'type': 'array',
            'maxItems': 6,
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'title': {'type': 'string'},
                    'url': {'type': 'string'},
                    'published_or_updated_at': {'type': 'string'},
                },
                'required': ['title', 'url', 'published_or_updated_at'],
            },
        },
        'report_patch': {
            'anyOf': [
                {'type': 'null'},
                {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'summary': {'type': 'string'},
                        'strategy_title': {'type': 'string'},
                        'problem_to_solve': {'type': 'string'},
                        'comparison_analysis': {'type': 'string'},
                        'solution': {'type': 'string'},
                        'expected_effect': {'type': 'string'},
                        'implementation_steps': {
                            'type': 'array',
                            'maxItems': 5,
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'properties': {
                                    'step': {'type': 'integer'},
                                    'schedule': {'type': 'string'},
                                    'task': {'type': 'string'},
                                    'deliverable': {'type': 'string'},
                                },
                                'required': ['step', 'schedule', 'task', 'deliverable'],
                            },
                        },
                    },
                    'required': [
                        'summary', 'strategy_title', 'problem_to_solve', 'comparison_analysis',
                        'solution', 'expected_effect', 'implementation_steps',
                    ],
                },
            ],
        },
    },
    'required': ['answer', 'mode', 'key_points', 'sources', 'report_patch'],
}


ASSISTANT_INSTRUCTIONS = """
대한민국 지자체 관광 담당자의 데이터 분석과 사업 기획을 돕는 AI 보조자다.
말은 쉽고 짧게 하되 판단은 깊게 한다. 입력 snapshot의 수치는 실제 관측값으로 사용하고,
current_report는 현재 화면에서 검토 중인 기획안으로만 사용한다. 관측 사실, 해석, 제안을 분리한다.
입력에 없는 관광지·업체·예산·방문자·매출·성과 수치는 만들지 않는다.

질문이 지표 설명이면 explain, 다른 지역 공식 사례나 최신 정책 조사가 필요하면 research,
현재 기획안의 방향·문장·실행 단계를 바꾸는 요청이면 revise를 선택한다.
웹 검색을 사용할 때는 허용된 정부·지자체·공공기관 공식 도메인만 사용하고 source URL을 반환한다.
행사와 지표 상승이 같은 시기에 관측됐다는 이유만으로 인과관계라고 단정하지 않는다.

answer는 4문장 이내, key_points는 회의에서 바로 읽을 수 있는 짧은 문장으로 작성한다.
revise일 때만 report_patch를 만들고, current_report에서 바꿀 필요가 없는 필드는 기존 문구를 그대로 복사한다.
implementation_steps는 실제 행동·기간·확인 가능한 결과물을 포함한 3~5단계로 작성한다.
사용자 확인 없이 저장하거나 확정했다고 말하지 않는다. explain 또는 research면 report_patch는 null이다.
"""


class TourismChatAssistantAgent:
    """원자료 조회와 공식 웹 조사 결과를 구조화된 대화 응답으로 반환합니다."""

    def __init__(self, *, env_values: dict[str, Any]) -> None:
        self.api_key = str(env_values.get('OPENAI_API_KEY') or '').strip()
        self.model = str(
            env_values.get('OPENAI_CHAT_MODEL')
            or env_values.get('OPENAI_REPORT_MODEL')
            or env_values.get('OPENAI_MODEL')
            or 'gpt-5.5'
        ).strip()
        self.domains = allowed_domains(env_values)

    async def answer(
        self,
        *,
        snapshot: dict[str, Any],
        question: str,
        history: list[dict[str, str]],
        current_report: dict[str, Any] | None,
        enable_web_search: bool,
        planning_brief: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tools = None
        include = None
        if enable_web_search:
            tools = [{
                'type': 'web_search',
                'filters': {'allowed_domains': self.domains},
                'search_context_size': 'medium',
            }]
            include = ['web_search_call.action.sources']

        result = await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=ASSISTANT_INSTRUCTIONS + PLANNING_CONTEXT_RULES,
            input_payload={
                'selected_region': snapshot['region_name'],
                'analysis_period': snapshot['period'],
                'snapshot': snapshot,
                'planning_brief': planning_brief,
                'current_report': current_report,
                'recent_conversation': history[-8:],
                'user_request': question,
                'web_search_allowed': enable_web_search,
            },
            schema_name='tourism_analysis_assistant',
            schema=ASSISTANT_CHAT_SCHEMA,
            reasoning_effort='medium',
            max_output_tokens=6000,
            tools=tools,
            include=include,
        )
        # 모델이 URL을 반환해도 서버에서 한 번 더 허용 도메인을 검사합니다.
        result['sources'] = [
            source for source in (result.get('sources') or [])
            if _url_is_allowed(str(source.get('url') or ''), self.domains)
        ]
        return result
