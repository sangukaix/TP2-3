"""Agent 1: 선택 지역의 데이터·Open API·RAG·공식 웹 근거를 수집합니다."""

from __future__ import annotations

import asyncio
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..openai_responses import OpenAIResponseError, create_structured_response
from ..llm.errors import LLMProviderError
from ..llm.models import LLMRequest
from ..llm.router import LLMRouter
from ..local_web_search import OfficialWebSearchClient
from ..case_scope import build_case_search_policy, nationwide_case_query
from ..rag_store import OfficialTourismRagStore
from ..evidence_sources import merge_evidence_sources
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

# Qwen은 검색 실행 권한이 아니라, 지역·기간·공식 도메인 제약 안의 질문만 만듭니다.
# Python 도구가 질문 개수·도메인·요약 길이를 다시 제한한 뒤 무료 검색 API를 호출합니다.
LOCAL_WEB_QUERY_PLAN_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'queries': {'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': {'type': 'string', 'maxLength': 240}},
        'focus': {'type': 'string', 'maxLength': 180},
    },
    'required': ['queries', 'focus'],
}

LOCAL_WEB_QUERY_PLANNER_INSTRUCTIONS = """
당신은 지역 관광정책 공식자료 검색 질문 설계자다. 사실을 조사하거나 답을 만들지 말고,
입력의 지역명·기간·조사 관점에 맞는 한국어 검색 질문 1~3개만 JSON으로 작성한다.
각 질문은 지자체·중앙정부·공공기관의 사업 구조, 예산·성과·운영조건 확인에 쓰여야 한다.
블로그·언론·광고·커뮤니티를 찾는 말, 특정 사업을 정답으로 전제하는 말, 명령문은 넣지 않는다.
검색 결과는 공식 도메인으로 서버가 별도 제한하며, 원문 검수 전에는 확인된 사실이 아니다.
첫 질문은 선택 지역·동일 시도의 현지 정책, 두 번째는 시도를 제한하지 않은 전국 유사 운영 사례를 찾는다.
전달된 peer는 관광 관측지표가 비슷한 지역이며 주민등록 인구가 비슷하다고 표현하지 않는다.
"""


def _reusable_policy_sources(sources: list[dict], region_code: str, *, today: date | None = None) -> list[dict]:
    """같은 문서의 여러 청크를 두 건으로 세지 않고, 해당 지역의 올해 공식 문서만 재사용합니다."""
    today = today or date.today()
    documents = {}
    for row in sources:
        if row.get('document_type') not in {'policy', 'case_study_budget'} or str(row.get('region_code')) != region_code:
            continue
        try:
            published = date.fromisoformat(str(row.get('published_or_updated_at') or '')[:10])
        except ValueError:
            continue
        url = str(row.get('source_url') or '')
        if url.startswith('https://') and published.year == today.year and published <= today:
            documents[url] = row
    return list(documents.values())


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

    def __init__(self, *, project_root: Path, env_values: dict[str, Any], llm_router: LLMRouter | None = None) -> None:
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
        self.llm_router = llm_router

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
        # 전국 비교는 MySQL에서 검증한 12개월 요약일 때만 별도 출처로 추가합니다.
        # 관측 수치와 peer 비교의 원본 ID를 분리해 Planner가 출처 없는 순위·평균을 만들지 못하게 합니다.
        nationwide = snapshot.get('nationwide_comparison') or {}
        if nationwide.get('available'):
            for record in nationwide.get('source_records') or []:
                source_id = str(record.get('source_id') or '')
                if not source_id:
                    continue
                sources.append({
                    'source_id': source_id,
                    'source_type': 'nationwide_dataset',
                    'title': str(record.get('title') or '한국관광 데이터랩 전국 비교 원자료'),
                    'source_url': str(record.get('source_url') or 'https://datalab.visitkorea.or.kr/'),
                    'summary': f"전국 비교 기준 기간: {nationwide.get('period') or ''}",
                    'observation_period': nationwide.get('period') or '',
                    'published_or_updated_at': nationwide.get('comparison_period') or '',
                })
            trace.append({'agent': 'evidence', 'stage': 'nationwide_comparison', 'status': 'completed', 'items': len(nationwide.get('source_records') or [])})
        elif nationwide:
            trace.append({'agent': 'evidence', 'stage': 'nationwide_comparison', 'status': 'skipped', 'items': 0})
        # 팀 공유 원본의 기간합계/전국 월별 표도 출처 ID를 등록한다. 다만 검토 상태가
        # 완전하지 않은 보조 신호이므로 Planner가 강한 인과·peer 근거로 바꾸지 못하게
        # source_type과 요약에 집계 수준을 명시한다.
        nationwide_bigdata = snapshot.get('nationwide_bigdata_context') or {}
        if nationwide_bigdata.get('available'):
            for record in nationwide_bigdata.get('source_records') or []:
                source_id = str(record.get('source_id') or '')
                if not source_id:
                    continue
                sources.append({
                    'source_id': source_id,
                    'source_type': 'nationwide_bigdata_dataset',
                    'title': str(record.get('title') or '한국관광 데이터랩 전국 빅데이터 다운로드'),
                    'source_url': str(record.get('source_url') or 'https://datalab.visitkorea.or.kr/'),
                    'summary': '시군구 기간합계·비중 또는 전국 월별 추이. 지역 월별 ML·정책 효과가 아닌 보조 근거.',
                    'observation_period': str((nationwide_bigdata.get('municipal_period_metrics') or [{}])[0].get('period') or ''),
                    'published_or_updated_at': '',
                    'source_review_status': str(record.get('review_status') or 'needs_exact_download_url'),
                })
            trace.append({'agent': 'evidence', 'stage': 'nationwide_bigdata_context', 'status': 'completed',
                          'items': len(nationwide_bigdata.get('source_records') or [])})
        elif nationwide_bigdata:
            trace.append({'agent': 'evidence', 'stage': 'nationwide_bigdata_context', 'status': 'skipped', 'items': 0})
        # 유입·유출/인기 장소/집중률은 월별 ML과 다른 보조 관측 근거입니다. 원본 source_id를
        # 따로 등록해 Agent가 순위·비율을 출처 없이 지역 사실처럼 단정하지 못하게 합니다.
        tourism_status = snapshot.get('regional_tourism_status') or {}
        if tourism_status.get('available'):
            for record in tourism_status.get('source_records') or []:
                source_id = str(record.get('source_id') or '')
                if not source_id:
                    continue
                sources.append({
                    'source_id': source_id,
                    'source_type': 'regional_tourism_status',
                    'title': str(record.get('source_name') or '한국관광 데이터랩 지역별 관광 현황'),
                    'source_url': str(record.get('source_page_url') or 'https://datalab.visitkorea.or.kr/'),
                    'summary': f"관측 기간: {tourism_status.get('latest_historical_period') or ''}. 유입·유출·인기장소 또는 30일 집중 운영 신호.",
                    'observation_period': tourism_status.get('latest_historical_period') or '',
                    'published_or_updated_at': '',
                })
            trace.append({'agent': 'evidence', 'stage': 'regional_tourism_status', 'status': 'completed',
                          'items': len(tourism_status.get('source_records') or [])})
        elif tourism_status:
            trace.append({'agent': 'evidence', 'stage': 'regional_tourism_status', 'status': 'skipped', 'items': 0})
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
                # Chroma 저장 위치가 절대경로여도 프로젝트의 검수 PDF 레지스트리를 안정적으로 찾습니다.
                local_reference_path=self.project_root / 'data' / 'rag' / 'official_reference_documents.jsonl',
            )
            try:
                items = await rag_store.search(
                    query=f"{snapshot['region_name']} 관광 체류 소비 정책 " + ' '.join(ml.get('research_questions') or []),
                    region_code=region_code,
                    region_name=snapshot['region_name'],
                    top_k=5,
                    local_only=bool(self.llm_router and self.llm_router.local_first),
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
                request = LLMRequest(
                    task='evidence', agent='evidence',
                    # Router 실행 시에는 환경변수 기반 모델 선택을 우선합니다. 아래 legacy 호출만 self.model을 씁니다.
                    model=None,
                    # 출력 상한은 내부 추론 포함입니다. 토큰 부족일 때만 같은 조사를 한 번 재시도합니다.
                    reasoning_effort='low', max_output_tokens=10000,
                    retry_max_output_tokens=16000, openai_timeout_seconds=600,
                    instructions=EVIDENCE_RESEARCH_INSTRUCTIONS,
                    input_payload={
                        'region_name': snapshot['region_name'],
                        'planning_brief': planning_brief,
                        'period': snapshot['period'],
                        'observations': snapshot.get('observations') or [],
                        'nationwide_comparison': snapshot.get('nationwide_comparison') or {},
                        'regional_tourism_status': tourism_status,
                        'ml_analysis': ml,
                        'research_questions': [
                            *(ml.get('research_questions') or []),
                            '선택 지역의 공식 관광정책·사업·관광 인프라 현황',
                            '분석 기간과 날짜가 겹치는 공식 축제·행사·계절 관광사업과 시행 시점',
                            '현재 지역에서 바로 활용할 수 있는 제도·교통·숙박·상권 운영 조건',
                            '선택 지역 사업의 공식 예산·결산·성과평가 자료',
                        ],
                    },
                    schema_name='official_tourism_research', schema=WEB_RESEARCH_SCHEMA,
                    tools=[{'type': 'web_search', 'filters': {'allowed_domains': self.domains}, 'search_context_size': 'medium'}],
                    include=['web_search_call.action.sources'], requires_web_search=True,
                )
                web_research = await self.llm_router.generate(request) if self.llm_router else await create_structured_response(
                    api_key=self.api_key,
                    model=self.model,
                    reasoning_effort='low',
                    max_output_tokens=10000, retry_max_output_tokens=16000, timeout_seconds=600,
                    instructions=EVIDENCE_RESEARCH_INSTRUCTIONS,
                    input_payload={
                        'region_name': snapshot['region_name'],
                        'planning_brief': planning_brief,
                        'period': snapshot['period'],
                        'observations': snapshot.get('observations') or [],
                        # 전국 peer 비교는 MySQL 검증 완료 상태일 때만 조사 질문의 맥락으로 사용합니다.
                        'nationwide_comparison': snapshot.get('nationwide_comparison') or {},
                        'regional_tourism_status': tourism_status,
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
                    require_web_search=True,
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
            except (OpenAIResponseError, LLMProviderError) as exc:
                return [], [f'공식 웹 조사 실패: {exc.code}'], {
                    'agent': 'evidence', 'stage': 'official_web', 'status': 'failed', 'items': 0,
                }, ''

        async def collect_free_official_web() -> tuple[list[dict[str, Any]], list[str], dict[str, Any], str]:
            """학생 절약 모드에서만 Qwen 질문 + 무료 검색 API 경로를 제한적으로 실행합니다."""
            search_client = OfficialWebSearchClient(env_values=self.env_values, allowed_domains=self.domains)
            search_status = search_client.provider_status()
            if not search_status['available']:
                return [], [
                    '무료 공식 웹 검색 API 키가 설정되지 않았습니다. 저장된 공식 문서와 Open API만 사용합니다.'
                ], {
                    'agent': 'evidence', 'stage': 'free_official_web', 'status': 'skipped',
                    'reason': 'no_free_search_api_key_configured', 'items': 0,
                }, ''

            research_lenses = [
                *(ml.get('research_questions') or []),
                '선택 지역의 공식 관광정책·사업과 운영 조건',
                '선택 지역 관광사업의 공개 예산·결산·성과평가 자료',
                '선택 지역 또는 유사 지역의 체류·소비 전환 사업 공식 사례',
            ]
            fallback_queries = [
                f"{snapshot['region_name']} 관광 정책 사업 예산 성과 공식",
                nationwide_case_query(snapshot),
            ]
            query_plan_trace: dict[str, Any] = {
                'agent': 'local_web_query_planner', 'stage': 'query_plan', 'status': 'skipped', 'items': 0,
            }
            queries = fallback_queries
            try:
                # Qwen의 작은 JSON 출력만 사용합니다. 모델이 네트워크·SQL·파일에 직접 접근하는 권한은 없습니다.
                query_plan = await self.llm_router.generate(LLMRequest(
                    task='local_web_query_planner', agent='local_web_query_planner', model=None,
                    instructions=LOCAL_WEB_QUERY_PLANNER_INSTRUCTIONS,
                    input_payload={
                        'region_name': snapshot['region_name'], 'analysis_period': snapshot.get('period'),
                        'research_lenses': research_lenses[:6],
                        'available_official_domains': self.domains,
                        'case_search_policy': build_case_search_policy(snapshot),
                    },
                    schema_name='local_official_web_query_plan', schema=LOCAL_WEB_QUERY_PLAN_SCHEMA,
                    reasoning_effort='low', max_output_tokens=700, local_max_output_tokens=450,
                ))
                planned = [str(item).strip() for item in (query_plan.get('queries') or []) if str(item).strip()]
                if planned:
                    # 두 번의 무료 조회 안에서 현지 정책과 전국 사례를 모두 탐색한다.
                    # 전국 슬롯은 지역명을 반복하는 모델 실수에도 유지한다.
                    queries = [planned[0], nationwide_case_query(snapshot)]
                query_plan_trace = {
                    'agent': 'local_web_query_planner', 'stage': 'query_plan', 'status': 'completed',
                    'provider': 'qwen', 'items': len(queries),
                }
            except LLMProviderError as exc:
                # 검색 질문 설계 실패가 원자료·저장 RAG 기반 기획 전체를 막지 않도록 안전한 고정 질문으로 한 번만 진행합니다.
                query_plan_trace = {
                    'agent': 'local_web_query_planner', 'stage': 'query_plan', 'status': 'fallback',
                    'provider': 'qwen', 'error_code': exc.code, 'items': len(queries),
                }

            items, search_trace = await search_client.search_many(queries)
            if not items:
                return [], [
                    '무료 공식 웹 검색에서 허용 도메인 결과를 찾지 못했습니다. API 할당량·키·공식 원문 URL을 확인하세요.'
                ], {
                    'agent': 'evidence', 'stage': 'free_official_web', 'status': 'completed',
                    'providers': search_status['configured_providers'], 'items': 0, 'subtrace': [query_plan_trace, *search_trace],
                }, ''
            # 검색 요약은 후보 탐색 전용입니다. Planner의 확정 인용 대상에서 제외되고, RAG 영구 저장도 사람 검수 후에만 가능합니다.
            return items, [
                '무료 검색 API의 제목·요약은 공식 원문 확인 전 후보입니다. 보고서 확정 근거·RAG 등록에는 원문 검수가 필요합니다.'
            ], {
                'agent': 'evidence', 'stage': 'free_official_web', 'status': 'completed',
                'providers': search_status['configured_providers'], 'items': len(items),
                'subtrace': [query_plan_trace, *search_trace],
            }, 'Qwen이 설계한 질문으로 무료 검색 API에서 공식 도메인 원문 후보를 찾았습니다. 원문 검수 전에는 확정 사실로 사용하지 않습니다.'

        if self.llm_router and self.llm_router.student_budget:
            open_api_result, rag_result = await asyncio.gather(collect_open_api(), collect_rag())
            # OpenAI Web Search는 호출하지 않습니다. 키가 설정된 무료 API만 Qwen 질문으로 제한 호출합니다.
            web_result = await collect_free_official_web()
        elif self.llm_router and self.llm_router.local_first:
            open_api_result, rag_result = await asyncio.gather(collect_open_api(), collect_rag())
            # 관광지 목록만으로 정책 근거가 충분하다고 판단하지 않습니다. 최근 공식 정책 문서가 있어야 재사용합니다.
            policy_sources = _reusable_policy_sources(rag_result[0], region_code)
            if len(policy_sources) >= 2:
                web_result = ([], [], {'agent': 'evidence', 'stage': 'official_web', 'status': 'skipped',
                                      'reason': 'current_official_policy_documents_reused', 'items': 0}, '')
            else:
                web_result = await collect_official_web()
        else:
            open_api_result, rag_result, web_result = await asyncio.gather(
                collect_open_api(), collect_rag(), collect_official_web(),
            )
        web_research_summary = web_result[3]
        for result in (open_api_result, rag_result, web_result[:3]):
            result_sources, result_gaps, result_trace = result
            sources.extend(result_sources)
            gaps.extend(result_gaps)
            trace.append(result_trace)

        # 동일한 문서 요약은 한 번만 넘기되, 서로 다른 PDF 페이지 청크는 각각 별도
        # 근거입니다. ``chunk_id``를 우선 키로 써 페이지 문맥·인용 쪽수가 사라지지 않게 합니다.
        unique_sources = merge_evidence_sources(sources)
        return {
            'region_code': region_code,
            'region_name': snapshot['region_name'],
            'period': snapshot['period'],
            'snapshot': snapshot,
            'sources': unique_sources,
            'research_summary': web_research_summary,
            'research_gaps': list(dict.fromkeys(gaps)),
            'trace': trace,
        }
