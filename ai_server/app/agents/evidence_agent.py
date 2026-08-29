"""Agent 1: 선택 지역의 데이터·Open API·RAG·공식 웹 근거를 수집합니다."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..openai_responses import OpenAIResponseError, create_structured_response
from ..rag_store import OfficialTourismRagStore
from ..tourism_open_api import TourismOpenApiClient
from .prompts import EVIDENCE_RESEARCH_INSTRUCTIONS


WEB_RESEARCH_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'summary': {'type': 'string'},
        'findings': {
            'type': 'array',
            'maxItems': 8,
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'claim': {'type': 'string'},
                    'why_relevant': {'type': 'string'},
                    'source_title': {'type': 'string'},
                    'source_url': {'type': 'string'},
                    'published_or_updated_at': {'type': 'string'},
                },
                'required': ['claim', 'why_relevant', 'source_title', 'source_url', 'published_or_updated_at'],
            },
        },
        'gaps': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}},
    },
    'required': ['summary', 'findings', 'gaps'],
}


def allowed_domains(env_values: dict[str, Any]) -> list[str]:
    raw = str(env_values.get('TOURISM_ALLOWED_RESEARCH_DOMAINS') or '')
    configured = [domain.strip().lower() for domain in re.split(r'[,;\s]+', raw) if domain.strip()]
    return configured or [
        # 중앙부처·광역·기초지자체의 공식 성과평가·예산·결산 자료를 함께 찾습니다.
        'go.kr',
        'visitkorea.or.kr',
        'kto.visitkorea.or.kr',
        'data.go.kr',
        'mcst.go.kr',
        'seoul.go.kr',
        'gangnam.go.kr',
        'incheon.go.kr',
    ]


def _url_is_allowed(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == domain or host.endswith(f'.{domain}') for domain in domains)


class EvidenceAgent:
    """LLM이 수치를 계산하지 못하게 하고, 확인된 근거 묶음만 만듭니다."""

    def __init__(self, *, project_root: Path, env_values: dict[str, Any]) -> None:
        self.project_root = project_root
        self.env_values = env_values
        self.api_key = str(env_values.get('OPENAI_API_KEY') or '').strip()
        self.domains = allowed_domains(env_values)
        self.model = str(
            env_values.get('OPENAI_RESEARCH_MODEL')
            or env_values.get('OPENAI_REPORT_MODEL')
            or env_values.get('OPENAI_MODEL')
            or 'gpt-5.6'
        ).strip()

    async def collect(self, *, region_code: str, snapshot: dict[str, Any], planning_brief: dict[str, Any] | None = None) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        gaps: list[str] = []
        trace: list[dict[str, Any]] = []

        # 정확한 월간 수치는 기존 데이터랩 ZIP 계산 결과만 등록합니다.
        for index, observation in enumerate(snapshot.get('observations') or [], start=1):
            sources.append({
                'source_id': f'dataset:{region_code}:{index}',
                'source_type': 'dataset',
                'title': str(observation.get('source') or '한국관광 데이터랩 원자료'),
                'source_url': 'https://datalab.visitkorea.or.kr/',
                'summary': (
                    f"{observation.get('metric')}: {observation.get('value')} "
                    f"(관측 기준월: {observation.get('period') or snapshot.get('latest_month', '')})"
                ),
                'observation_period': observation.get('period') or snapshot.get('latest_month', ''),
                'published_or_updated_at': observation.get('period') or snapshot.get('latest_month', ''),
            })
        trace.append({'agent': 'evidence', 'stage': 'dataset', 'status': 'completed', 'items': len(sources)})
        # ML은 공식 관측값과 구분된 내부 계산 근거입니다. 수치표를 RAG에 저장하지 않습니다.
        ml = snapshot.get('ml_analysis') or {}
        if ml.get('status') == 'available':
            sources.append({
                'source_id': ml['source_id'], 'source_type': 'model_forecast',
                'title': '지역 관광수요 ML 전망 · 공식 관측값 아님',
                'source_url': '',
                'summary': f"학습 {ml['source_period']} · 모델 {ml['model_version']} · 자연 추세 예측",
                'model_version': ml['model_version'], 'data_fingerprint': ml['data_fingerprint'],
            })
        elif ml:
            gaps.append(f"ML 근거 미제공: {ml.get('reason_code') or ml.get('status')}")

        # 아래 세 작업은 서로의 결과를 입력으로 쓰지 않습니다. 동시에 실행하면 근거의 범위와
        # 모델 품질은 그대로 유지하면서 첫 보고서의 자료 조사 대기시간을 줄일 수 있습니다.
        async def collect_open_api() -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
            tour_key = str(
                self.env_values.get('TOUR_CONTENT_LAB_API_KEY')
                or self.env_values.get('TOUR_API_SERVICE_KEY')
                or self.env_values.get('DATA_GO_KR_SERVICE_KEY')
                or ''
            )
            tour_base_url = str(
                self.env_values.get('TOUR_INFO_API_BASE_URL')
                or 'https://apis.data.go.kr/B551011/KorService2'
            )
            try:
                items = await TourismOpenApiClient(api_key=tour_key, base_url=tour_base_url).collect_region_resources(
                    snapshot['region_name']
                )
                local_gaps = [] if items else ['선택 지역 관광자원 Open API 결과가 없거나 지역 코드가 일치하지 않음']
                return items, local_gaps, {
                    'agent': 'evidence', 'stage': 'open_api', 'status': 'completed', 'items': len(items),
                }
            except Exception as exc:  # 외부 API 실패가 원자료 기반 보고서까지 막지 않도록 격리합니다.
                return [], [f'관광 Open API 조회 실패: {type(exc).__name__}'], {
                    'agent': 'evidence', 'stage': 'open_api', 'status': 'failed', 'items': 0,
                }

        async def collect_rag() -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
            rag_path = Path(str(self.env_values.get('CHROMA_PERSIST_DIRECTORY') or 'data/chroma'))
            if not rag_path.is_absolute():
                rag_path = self.project_root / rag_path
            rag_store = OfficialTourismRagStore(
                persist_directory=rag_path,
                api_key=self.api_key,
                embedding_model=str(self.env_values.get('OPENAI_EMBEDDING_MODEL') or 'text-embedding-3-small'),
                allowed_domains=self.domains,
            )
            try:
                items = await rag_store.search(
                    query=f"{snapshot['region_name']} 관광 체류 소비 정책 " + ' '.join(ml.get('research_questions') or []),
                    region_code=region_code,
                    region_name=snapshot['region_name'],
                    top_k=5,
                )
                local_gaps = [] if items else ['선택 지역의 검증된 공식 RAG 문서가 아직 등록되지 않음']
                return items, local_gaps, {
                    'agent': 'evidence', 'stage': 'rag', 'status': 'completed', 'items': len(items),
                }
            except Exception as exc:
                return [], [f'RAG 검색 불가: {type(exc).__name__}'], {
                    'agent': 'evidence', 'stage': 'rag', 'status': 'failed', 'items': 0,
                }

        async def collect_official_web() -> tuple[list[dict[str, Any]], list[str], dict[str, Any], str]:
            if not self.api_key or str(self.env_values.get('ENABLE_OFFICIAL_WEB_RESEARCH') or 'true').lower() != 'true':
                return [], ['공식 웹 조사가 비활성화되었거나 OpenAI 키가 없음'], {
                    'agent': 'evidence', 'stage': 'official_web', 'status': 'skipped', 'items': 0,
                }, ''
            try:
                web_research = await create_structured_response(
                    api_key=self.api_key,
                    model=self.model,
                    reasoning_effort='low',
                    max_output_tokens=8000,
                    instructions=EVIDENCE_RESEARCH_INSTRUCTIONS,
                    input_payload={
                        'region_name': snapshot['region_name'],
                        'planning_brief': planning_brief,
                        'period': snapshot['period'],
                        'observations': snapshot.get('observations') or [],
                        'ml_analysis': ml,
                        'research_questions': [
                            *(ml.get('research_questions') or []),
                            '선택 지역의 공식 관광정책·사업·관광 인프라 현황',
                            '분석 기간과 날짜가 겹치는 공식 축제·행사·계절 관광사업과 시행 시점',
                            '현재 지역에서 바로 활용할 수 있는 제도·교통·숙박·상권 운영 조건',
                            '선택 지역 사업의 공식 예산·결산·성과평가 자료',
                        ],
                    },
                    schema_name='official_tourism_research',
                    schema=WEB_RESEARCH_SCHEMA,
                    tools=[{'type': 'web_search', 'filters': {'allowed_domains': self.domains}, 'search_context_size': 'medium'}],
                    include=['web_search_call.action.sources'],
                )
                items = []
                for index, finding in enumerate(web_research.get('findings') or [], start=1):
                    if not _url_is_allowed(str(finding.get('source_url') or ''), self.domains):
                        continue
                    items.append({
                        'source_id': f'web:{region_code}:{index}',
                        'source_type': 'official_web',
                        'title': finding['source_title'],
                        'source_url': finding['source_url'],
                        'published_or_updated_at': finding['published_or_updated_at'],
                        'summary': finding['claim'],
                        'why_relevant': finding['why_relevant'],
                    })
                return items, list(web_research.get('gaps') or []), {
                    'agent': 'evidence', 'stage': 'official_web', 'status': 'completed', 'items': len(items),
                }, str(web_research.get('summary') or '')
            except OpenAIResponseError as exc:
                return [], [f'공식 웹 조사 실패: {exc.code}'], {
                    'agent': 'evidence', 'stage': 'official_web', 'status': 'failed', 'items': 0,
                }, ''

        open_api_result, rag_result, web_result = await asyncio.gather(
            collect_open_api(),
            collect_rag(),
            collect_official_web(),
        )
        web_research_summary = web_result[3]
        for result in (open_api_result, rag_result, web_result[:3]):
            result_sources, result_gaps, result_trace = result
            sources.extend(result_sources)
            gaps.extend(result_gaps)
            trace.append(result_trace)

        # 동일 source_id 중복을 제거하고, 기획 Agent에 검증된 입력만 넘깁니다.
        unique_sources = {str(source['source_id']): source for source in sources if source.get('source_id')}
        return {
            'region_code': region_code,
            'region_name': snapshot['region_name'],
            'period': snapshot['period'],
            'snapshot': snapshot,
            'sources': list(unique_sources.values()),
            'research_summary': web_research_summary,
            'research_gaps': list(dict.fromkeys(gaps)),
            'trace': trace,
        }
