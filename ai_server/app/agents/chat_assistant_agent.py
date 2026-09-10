"""선택 지역의 분석 결과와 기획안을 대화로 설명·수정하는 AI 보조 Agent입니다."""

from __future__ import annotations

from typing import Any

from ..openai_responses import create_structured_response
from ..llm.models import LLMRequest
from ..llm.router import LLMRouter
from ..llm.chat_context import pack_report, revision_report, READING_RULE
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
현재 보고서가 있으면 근거가 연결된 design_candidates만 사업 선택 범위다. 범위 밖 신축·새 사업 요청에는 revise하지 않고 실제 후보 개수와 제목을 안내한다. 현재 사업의 소개·홍보·참여 범위·운영 단계만 보완한다. 숫자 목표와 견적 수정은 별도 서버 처리에서 반영하며 임의 변경하지 않는다.
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
web_search_allowed=false이면 새 웹 검색을 했다고 말하지 않는다. 전달된 보고서·지역 자료에 있는 근거만 설명한다.
현재 보고서에 첨부 원문이나 사례 세부사항이 없으면 기억으로 복원하지 말고 필요한 원문을 요청한다.
수정은 본문·제목·실행 단계에 한정한다. ML 수치, 목표 KPI, 예산, 일정 조건을 저장까지 변경했다고 주장하지 않는다.
reference_only_not_read는 이번 수정에 원문을 전달하지 않은 참고목록이다. 이 목록의 내용을 추측·인용하지 않는다.
새 사업 후보 선정이나 새 사례 검증이 필요하면 기존 본문 보완 범위를 벗어나므로 새 기획안 생성 또는 원문 확인이 필요하다고 안내한다.
이동통신·카드 기반 방문·소비 지표는 해당 표본·집계 정의의 관측 지표다. 지표가 방문·소비를 전혀 뜻하지 않는다고 부정하지 말고, 전수조사·정책 인과효과와 다름을 설명한다.
공식 부서명·업체·협약이 확인되지 않았다면 담당 역할(제안)으로 적는다. 기존 일정이 사업기간을 벗어나면 조용히 유지하거나 확정하지 말고 충돌을 answer에서 알린다.
"""


def supplied_urls(value):
    """로컬 설명에서 새 URL을 만들어 출처처럼 표시하지 않습니다."""
    if isinstance(value, dict):
        return set().union(*(supplied_urls(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(supplied_urls(item) for item in value))
    return {value.strip()} if isinstance(value, str) and value.strip().startswith(('https://', 'http://')) else set()


class TourismChatAssistantAgent:
    """원자료 조회와 공식 웹 조사 결과를 구조화된 대화 응답으로 반환합니다."""

    def __init__(self, *, env_values: dict[str, Any], llm_router: LLMRouter | None = None) -> None:
        self.api_key = str(env_values.get('OPENAI_API_KEY') or '').strip()
        self.model = str(
            env_values.get('OPENAI_CHAT_MODEL')
            or env_values.get('OPENAI_REPORT_MODEL')
            or env_values.get('OPENAI_MODEL')
            or 'gpt-5.5'
        ).strip()
        self.domains = allowed_domains(env_values)
        self.llm_router = llm_router

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
        if current_report:
            from ..idea_proposal import bounded_chat_reply
            direct = bounded_chat_reply(current_report, question)
            if direct:
                return direct
            enable_web_search = False
        tools = None
        include = None
        if enable_web_search:
            tools = [{
                'type': 'web_search',
                'filters': {'allowed_domains': self.domains},
                'search_context_size': 'medium',
            }]
            include = ['web_search_call.action.sources']

        lowered_question = question.lower()
        # 검색 허용 체크박스는 모든 질문을 유료 검색 작업으로 바꾸는 스위치가 아니다.
        revise = any(word in lowered_question for word in ('수정', '고쳐', '바꿔', '추가', '구체적', '다듬', '보완'))
        research = any(word in lowered_question for word in ('검색', '찾아', '최신', '조사'))
        use_search = enable_web_search and research
        task = 'chat_research' if use_search else ('chat_revise' if revise else 'chat_explain')
        if not use_search:
            tools = include = None
        editing_report = revision_report(current_report) if revise and current_report and not use_search else current_report
        report_context = pack_report(editing_report) if editing_report else None
        # 저장 보고서 수정에 최신 snapshot 전체를 섞으면 기간과 근거가 중복·충돌한다.
        snapshot_context = ({'region_name': snapshot['region_name'], 'period': current_report.get('period'),
                             'basis': 'current_report: saved observations and evidence'}
                            if revise and current_report and not use_search else snapshot)
        request = LLMRequest(
            task=task, agent='tourism_chat', model=None,
            instructions=ASSISTANT_INSTRUCTIONS + PLANNING_CONTEXT_RULES + READING_RULE,
            input_payload={
                'selected_region': snapshot['region_name'], 'analysis_period': snapshot_context['period'],
                'snapshot': snapshot_context, 'planning_brief': planning_brief, 'current_report': report_context,
                'recent_conversation': history[-8:], 'user_request': question, 'web_search_allowed': use_search,
            }, schema_name='tourism_analysis_assistant', schema=ASSISTANT_CHAT_SCHEMA,
            reasoning_effort='medium', max_output_tokens=6000, tools=tools, include=include,
            requires_web_search=use_search,
        )
        result = await self.llm_router.generate(request) if self.llm_router else await create_structured_response(
            api_key=self.api_key,
            model=self.model,
            instructions=ASSISTANT_INSTRUCTIONS + PLANNING_CONTEXT_RULES + READING_RULE,
            input_payload={
                'selected_region': snapshot['region_name'],
                'analysis_period': snapshot_context['period'],
                'snapshot': snapshot_context,
                'planning_brief': planning_brief,
                'current_report': report_context,
                'recent_conversation': history[-8:],
                'user_request': question,
                'web_search_allowed': use_search,
            },
            schema_name='tourism_analysis_assistant',
            schema=ASSISTANT_CHAT_SCHEMA,
            reasoning_effort='medium',
            max_output_tokens=6000,
            tools=tools,
            include=include,
        )
        # 모델이 URL을 반환해도 서버에서 한 번 더 허용 도메인을 검사합니다.
        known_urls = supplied_urls(snapshot) | supplied_urls({key: value for key, value in (editing_report or {}).items() if key != 'reference_only_not_read'})
        result['sources'] = [
            source for source in (result.get('sources') or [])
            if _url_is_allowed(str(source.get('url') or ''), self.domains)
            and (use_search or str(source.get('url') or '') in known_urls)
        ]
        if not current_report or result.get('mode') != 'revise':
            result['report_patch'] = None
        trace = getattr(self.llm_router, 'trace', [])
        last = trace[-1] if trace else {}
        result['execution'] = {key: last.get(key) for key in (
            'provider', 'model', 'web_search_used', 'fallback', 'usage'
        ) if key in last}
        result['generation_mode'] = 'local' if last.get('provider') in {'qwen', 'gemma', 'ollama'} else 'openai'
        return result
