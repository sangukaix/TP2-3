"""Agent 2: 공식 관광사업의 실행 방식·성과·적용 조건을 사례 카드로 수집합니다."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any

from ..openai_responses import OpenAIResponseError, create_structured_response
from ..llm.errors import LLMProviderError
from ..llm.models import LLMRequest
from ..llm.router import LLMRouter
from ..rag_store import OfficialTourismRagStore
from ..case_registry import load_curated_case_registry
from ..case_scope import build_case_search_policy, case_relation, select_case_cards
from .evidence_agent import _url_is_allowed, allowed_domains
from .prompts import CASE_STUDY_RESEARCH_INSTRUCTIONS


# 공식 사례마다 운영 방식·예산·결과·제약 조건을 같은 필드로 보관하기 위한 구조화 응답 계약입니다.
CASE_STUDY_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'summary': {'type': 'string'},
        'cases': {
            'type': 'array',
            'maxItems': 8,
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'case_region': {'type': 'string'},
                    'intervention': {'type': 'string'},
                    'problem_addressed': {'type': 'string'},
                    'target_group': {'type': 'string'},
                    'operating_model': {'type': 'string'},
                    'duration': {'type': 'string'},
                    'public_budget': {'type': 'string'},
                    'observed_result': {'type': 'string'},
                    'measurement_period': {'type': 'string'},
                    'evidence_strength': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                    'transfer_conditions': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
                    'risks': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
                    'source_title': {'type': 'string'},
                    'source_url': {'type': 'string'},
                    'published_or_updated_at': {'type': 'string'},
                },
                'required': [
                    'case_region', 'intervention', 'problem_addressed', 'target_group', 'operating_model',
                    'duration', 'public_budget', 'observed_result', 'measurement_period', 'evidence_strength',
                    'transfer_conditions', 'risks', 'source_title', 'source_url', 'published_or_updated_at',
                ],
            },
        },
        'gaps': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}},
    },
    'required': ['summary', 'cases', 'gaps'],
}


def _case_source_id(url: str) -> str:
    # URL의 해시 앞부분을 안정적인 내부 ID로 써, 같은 공식 페이지가 여러 번 검색돼도 하나로 합칠 수 있게 합니다.
    return f"case:{sha256(url.encode('utf-8')).hexdigest()[:14]}"


def _load_curated_case_cards(project_root: Path, domains: list[str]) -> list[dict[str, Any]]:
    """팀이 출처를 검수한 사례 카드는 웹 검색 전에도 입력 후보로 사용합니다."""
    registry_path = project_root / 'data' / 'rag' / 'official_case_studies.jsonl'
    if not registry_path.exists():
        return []
    cards: list[dict[str, Any]] = []
    for record in load_curated_case_registry(registry_path):
        source_url = str(record.get('source_url') or '')
        if not _url_is_allowed(source_url, domains):
            continue
        cards.append({
            'source_id': str(record.get('source_id') or _case_source_id(source_url)),
            'region_code': str(record.get('region_code') or 'ALL'),
            'region_name': str(record.get('region_name') or ''),
            'case_region': str(record.get('case_region') or record.get('region_name') or '전국 공통'),
            'intervention': str(record.get('intervention') or record.get('title') or ''),
            'problem_addressed': str(record.get('problem_addressed') or ''),
            'target_group': str(record.get('target_group') or ''),
            'operating_model': str(record.get('operating_model') or record.get('content') or ''),
            'duration': str(record.get('duration') or '공식 자료에서 확인되지 않음'),
            'public_budget': str(record.get('public_budget') or '공식 자료에서 확인되지 않음'),
            'observed_result': str(record.get('observed_result') or '공식 자료에서 확인되지 않음'),
            'measurement_period': str(record.get('measurement_period') or '공식 자료에서 확인되지 않음'),
            'evidence_strength': str(record.get('evidence_strength') or 'low'),
            'quantitative_result_approved': record.get('quantitative_result_approved'),
            'transfer_conditions': list(record.get('transfer_conditions') or []),
            'risks': list(record.get('risks') or []),
            'source_title': str(record.get('title') or '공식 관광사업 사례'),
            'source_url': source_url,
            'published_or_updated_at': str(record.get('published_or_updated_at') or ''),
        })
    return cards


def _case_mechanism_family(case: dict[str, Any]) -> str:
    """검수 카드가 실제로 서로 다른 해법을 담았는지 판별하는 비공개 보조 분류입니다."""
    text = json.dumps(case, ensure_ascii=False).lower()
    if any(word in text for word in ('숙박', '체크인', '숙소')):
        return 'stay_conversion'
    if any(word in text for word in ('야간', '밤', '저녁')):
        return 'night_time_experience'
    if any(word in text for word in ('교통', 'ktx', '항공', '시티투어', '이동')):
        return 'access_and_mobility'
    if any(word in text for word in ('예약', '재고', '시간대', '입장')):
        return 'reservation_conversion'
    if any(word in text for word in ('환급', '할인', '쿠폰', '상품권', '결제')):
        return 'spend_conversion'
    if any(word in text for word in ('재방문', '관광주민증', '회원', '반복')):
        return 'return_visit'
    return 'other_operation'


def _case_research_lenses(snapshot: dict[str, Any]) -> list[str]:
    """지역 데이터가 암시하는 병목에서 출발해 사례 조사 관점을 만듭니다.

    기존처럼 모든 지역을 숙박·야간관광 검색어로 시작하면 해당 사례가 많은 지역만
    선택되는 편향이 생깁니다. 월간 지표는 원인을 증명하지 않으므로, 이 값은 검색·비교
    관점일 뿐 특정 사업을 미리 결정하는 명령이 아닙니다.
    """
    raw = json.dumps({
        'observations': snapshot.get('observations') or [],
        'ml_analysis': snapshot.get('ml_analysis') or {},
        'nationwide_comparison': snapshot.get('nationwide_comparison') or {},
        'consumption_by_category': snapshot.get('consumption_by_category') or [],
    }, ensure_ascii=False).lower()
    lenses = [
        '방문 이후 지역 상권 결제·체험 이용으로 이어지는 전환 운영과 측정 사례',
        '기존 공공·민간 콘텐츠를 활용해 준비기간과 고정비를 줄이는 예약·운영 사례',
        '참여자 기록과 비교집단을 이용해 실제 이용·소비 변화를 검증한 관광사업 사례',
    ]
    if any(word in raw for word in ('숙박', '체류')):
        lenses.append('비숙박 방문의 체류 또는 숙박 전환을 검증한 사례와 필요한 협약 조건')
    if any(word in raw for word in ('검색', 'sns', '내비', '네비', '관심')):
        lenses.append('검색·관심을 예약·현장 이용으로 연결하고 전환을 측정한 사례')
    if any(word in raw for word in ('교통', '이동', '접근')):
        lenses.append('교통·보행·관광 콘텐츠를 결합해 접근 장벽을 줄인 사례')
    if any(word in raw for word in ('행사', '축제', '계절')):
        lenses.append('계절·행사 수요를 반복 방문 또는 비혼잡일 이용으로 전환한 사례')
    # 같은 내용이 중복돼도 조사 질문을 부풀리지 않고 최대 5개만 보냅니다.
    return list(dict.fromkeys(lenses))[:5]


def _needs_targeted_case_research(curated_cards: list[dict[str, Any]], snapshot: dict[str, Any]) -> bool:
    """공통 사례만으로 지역 맞춤 선택을 해도 되는지 보수적으로 확인합니다.

    전국 공통 카드가 여러 장이라는 사실은 선택 지역과 유사한 도시·수요 조건을 검토했다는
    뜻이 아닙니다. 선택 지역 또는 검증된 peer와 맞닿은 공식 카드가 없으면, local_first라도
    OpenAI Web Search의 한정된 사례 조사 1회를 사용합니다.
    """
    target_related = any(
        (relation := case_relation(card, snapshot))['scope'] == 'selected_region'
        or relation['peer_region_code'] is not None
        for card in curated_cards
    )
    reusable = [card for card in curated_cards if card.get('operating_model')
                and re.search(r'\b20\d{2}', str(card.get('measurement_period') or ''))
                and card.get('evidence_strength') in {'high', 'medium'}]
    families = {_case_mechanism_family(card) for card in reusable}
    return not target_related or len(families) < 3


class CaseStudyAgent:
    """일반 아이디어가 아니라 공식 자료에서 확인된 사업 사례만 반환합니다."""

    def __init__(self, *, project_root: Path, env_values: dict[str, Any], llm_router: LLMRouter | None = None) -> None:
        # 환경변수에서만 API 키·모델·허용 도메인을 읽어, 프런트엔드나 코드에 비밀값을 남기지 않습니다.
        self.project_root = project_root
        self.env_values = env_values
        self.api_key = str(env_values.get('OPENAI_API_KEY') or '').strip()
        self.domains = allowed_domains(env_values)
        self.model = str(
            env_values.get('OPENAI_CASE_RESEARCH_MODEL')
            or env_values.get('OPENAI_RESEARCH_MODEL')
            or env_values.get('OPENAI_REPORT_MODEL')
            or env_values.get('OPENAI_MODEL')
            or 'gpt-5.6'
        ).strip()
        self.llm_router = llm_router

    async def collect(self, *, region_code: str, snapshot: dict[str, Any], planning_brief: dict[str, Any] | None = None,
                       force_web: bool = False) -> dict[str, Any]:
        # 1) 팀이 먼저 검수한 JSONL 사례, 2) 영속 RAG, 3) 허용 도메인 웹 검색 순서로 근거를 모읍니다.
        # 어느 단계가 실패했는지는 trace·research_gaps에 남겨 Planner와 Reviewer가 알 수 있게 합니다.
        curated_cards = _load_curated_case_cards(self.project_root, self.domains)
        case_search_policy = build_case_search_policy(snapshot)
        curated_cards, registry_coverage = select_case_cards(curated_cards, snapshot, mechanism_key=_case_mechanism_family)
        gaps: list[str] = []
        trace: list[dict[str, Any]] = [{
            'agent': 'case_scout', 'stage': 'curated_registry', 'status': 'completed', 'items': len(curated_cards),
        }]

        # 영속 ChromaDB에는 이미 검수한 문서의 의미 검색 결과가 들어 있습니다.
        # 월별 숫자 표는 RAG에 넣지 않고 snapshot의 원자료 수치로만 다룹니다.
        rag_candidates: list[dict[str, Any]] = []
        rag_path = Path(str(self.env_values.get('CHROMA_PERSIST_DIRECTORY') or 'data/chroma'))
        if not rag_path.is_absolute():
            rag_path = self.project_root / rag_path
        try:
            rag_candidates = await OfficialTourismRagStore(
                persist_directory=rag_path,
                api_key=self.api_key,
                embedding_model=str(self.env_values.get('OPENAI_EMBEDDING_MODEL') or 'text-embedding-3-small'),
                allowed_domains=self.domains,
                # 절대 Chroma 경로를 쓰는 배포 환경에서도 프로젝트 RAG 레지스트리를 함께 검색합니다.
                local_reference_path=self.project_root / 'data' / 'rag' / 'official_reference_documents.jsonl',
            ).search(
                query=(
                    f"{snapshot['region_name']} "
                    + ' '.join(_case_research_lenses(snapshot))
                    + ' ' + ' '.join((snapshot.get('ml_analysis') or {}).get('research_questions') or [])
                ),
                region_code=region_code,
                region_name=snapshot['region_name'],
                top_k=8,
                local_only=bool(self.llm_router and self.llm_router.local_first),
                nationwide_cases=True,
            )
            trace.append({'agent': 'case_scout', 'stage': 'case_rag', 'status': 'completed', 'items': len(rag_candidates)})
            if not rag_candidates:
                gaps.append('성과·운영 방식이 정리된 공식 사례 RAG 문서가 아직 충분하지 않음')
        except Exception as exc:
            gaps.append(f'공식 사례 RAG 검색 불가: {type(exc).__name__}')
            trace.append({'agent': 'case_scout', 'stage': 'case_rag', 'status': 'failed', 'items': 0})

        # 라이브 웹 검색은 선택 기능입니다. 꺼져 있거나 API 키가 없으면 검수된 카드만 사용합니다.
        web_enabled = str(self.env_values.get('ENABLE_CASE_STUDY_WEB_RESEARCH') or 'true').lower() == 'true'
        # 공통 사례는 비용을 아끼는 출발점이지만, 선택 지역 또는 peer와 맞닿는 카드가 없다면
        # 그대로 복사하지 않기 위해 한 번의 최신 공식 사례 조사를 실행합니다.
        reusable = [row for row in curated_cards if row.get('operating_model')
                    and re.search(r'\b20\d{2}', str(row.get('measurement_period') or ''))
                    and row.get('evidence_strength') in {'high', 'medium'}]
        case_lenses = _case_research_lenses(snapshot)
        targeted_research_needed = _needs_targeted_case_research(curated_cards, snapshot)
        if self.llm_router and self.llm_router.student_budget:
            # 비용을 이유로 사례를 지어내거나 웹 검색 결과처럼 바꾸지 않습니다. 이미 팀이 검수한
            # 카드만 비교에 쓰며, 지역·peer 연결이 약하면 Qwen과 품질 게이트가 미승인으로 남깁니다.
            cases = curated_cards
            if targeted_research_needed or len(reusable) < 2:
                gaps.append('학생 절약 모드: 선택 지역 또는 검증 peer에 맞닿는 공식 사례가 충분하지 않습니다. OpenAI 웹 조사를 자동 실행하지 않았으므로 집행 전 지역 맞춤 사례를 추가 검증하세요.')
            trace.append({'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'skipped',
                          'reason': 'student_budget_uses_curated_cases_only', 'items': 0})
        elif self.llm_router and self.llm_router.local_first and not force_web and not targeted_research_needed and len(reusable) >= 2:
            cases = curated_cards
            trace.append({'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'skipped',
                          'reason': 'curated_cases_cover_target_condition', 'items': 0})
        elif not self.api_key or not web_enabled:
            gaps.append('공식 성공사례 웹 조사가 비활성화되었거나 OpenAI 키가 없음')
            cases = curated_cards
            trace.append({'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'skipped', 'items': 0})
        else:
            try:
                request = LLMRequest(
                    task='case_study', agent='case_scout', model=None,
                    instructions=CASE_STUDY_RESEARCH_INSTRUCTIONS,
                    input_payload={
                        'selected_region': snapshot['region_name'], 'planning_brief': planning_brief,
                        'analysis_period': snapshot['period'], 'observations': snapshot.get('observations') or [],
                        'ml_analysis': snapshot.get('ml_analysis') or {},
                        'regional_comparison': snapshot.get('regional_comparison') or {},
                        'nationwide_comparison': snapshot.get('nationwide_comparison') or {},
                        'curated_case_cards': curated_cards, 'case_rag_candidates': rag_candidates,
                        'case_research_lenses': case_lenses,
                        'case_search_policy': case_search_policy,
                    },
                    schema_name='official_tourism_case_studies', schema=CASE_STUDY_SCHEMA,
                    # 공식 사례의 운영·예산·성과·조건을 완성할 공간을 확보하되 무한 재시도하지 않습니다.
                    reasoning_effort='medium', max_output_tokens=16000,
                    retry_max_output_tokens=24000, openai_timeout_seconds=600,
                    tools=[{'type': 'web_search', 'filters': {'allowed_domains': self.domains}, 'search_context_size': 'high'}],
                    include=['web_search_call.action.sources'], requires_web_search=True,
                )
                result = await self.llm_router.generate(request) if self.llm_router else await create_structured_response(
                    api_key=self.api_key,
                    model=self.model,
                    instructions=CASE_STUDY_RESEARCH_INSTRUCTIONS,
                    input_payload={
                        'selected_region': snapshot['region_name'],
                        'planning_brief': planning_brief,
                        'analysis_period': snapshot['period'],
                        'observations': snapshot.get('observations') or [],
                        # 예측된 문제·기회에 맞는 사례를 찾되, 예측 자체를 사업 성과로 사용하지 않습니다.
                        'ml_analysis': snapshot.get('ml_analysis') or {},
                        'forecast_research_questions': (snapshot.get('ml_analysis') or {}).get('research_questions') or [],
                        'consumption_by_category': snapshot.get('consumption_by_category') or [],
                        'regional_comparison': snapshot.get('regional_comparison') or {},
                        # peer 비교는 사례를 그대로 복사하지 않고 적용 조건을 좁히는 참고 근거입니다.
                        'nationwide_comparison': snapshot.get('nationwide_comparison') or {},
                        'curated_case_cards': curated_cards,
                        'case_rag_candidates': rag_candidates,
                        'case_research_lenses': case_lenses,
                        'case_search_policy': case_search_policy,
                    },
                    schema_name='official_tourism_case_studies',
                    require_web_search=True,
                    schema=CASE_STUDY_SCHEMA,
                    reasoning_effort='medium',
                    max_output_tokens=16000, retry_max_output_tokens=24000, timeout_seconds=600,
                    tools=[{
                        'type': 'web_search',
                        'filters': {'allowed_domains': self.domains},
                        'search_context_size': 'high',
                    }],
                    include=['web_search_call.action.sources'],
                )
                # 팀이 이미 검수한 카드는 항상 유지하고, 라이브 검색으로 최신 사례만 보강합니다.
                cases = list(curated_cards)
                for case in result.get('cases') or []:
                    source_url = str(case.get('source_url') or '')
                    if not _url_is_allowed(source_url, self.domains):
                        continue
                    cases.append({'source_id': _case_source_id(source_url), **case})
                gaps.extend(result.get('gaps') or [])
                trace.append({
                    'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'completed', 'items': len(cases),
                })
            except (OpenAIResponseError, LLMProviderError) as exc:
                cases = curated_cards
                gaps.append(f'공식 성공사례 웹 조사 실패: {exc.code}')
                trace.append({
                    'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'failed', 'items': 0,
                    'error_code': exc.code,
                })

        # 같은 URL은 하나의 사례로만 유지하고 Planner가 인용할 수 있도록 source 레코드도 만듭니다.
        unique_cases: dict[str, dict[str, Any]] = {}
        for case in cases:
            if case.get('source_url'):
                unique_cases.setdefault(str(case['source_url']), case)
        cases = list(unique_cases.values())
        cases, case_coverage = select_case_cards(cases, snapshot, mechanism_key=_case_mechanism_family)
        case_coverage['registry_candidates'] = registry_coverage['catalog_candidates']
        case_coverage['registry_excluded'] = registry_coverage['excluded_candidates']
        if not any(row['retrieval_context']['scope'] == 'same_province' for row in cases):
            gaps.append('같은 시도의 타 시군구 공식 사례 카드는 현재 후보에 없습니다. 전국 사례를 비교하되 인근 사업이 없다고 단정하지 않습니다.')
        if not any(row['retrieval_context']['scope'] in {'cross_province_peer', 'cross_province'} for row in cases):
            gaps.append('타 시도 소재지가 확인된 사례가 현재 후보에 없습니다. 전국 탐색 범위와 실제 근거 확보는 다르므로 보완 검수가 필요합니다.')
        trace.append({'agent': 'case_scout', 'stage': 'national_case_selection', 'status': 'completed',
                      'items': len(cases), **case_coverage})
        sources = [{
            'source_id': case['source_id'],
            'source_type': 'benchmark_case',
            'title': case['source_title'],
            'source_url': case['source_url'],
            'published_or_updated_at': case['published_or_updated_at'],
            'summary': f"{case['case_region']} · {case['intervention']} · {case['observed_result']}",
            'evidence_strength': case['evidence_strength'],
            'quantitative_result_approved': case.get('quantitative_result_approved'),
        } for case in cases]
        # 최신 검수 카드와 같은 출처의 오래된 Chroma 요약이 교정 내용을 덮어쓰지 않게 한다.
        current_ids = {row['source_id'] for row in sources}
        current_urls = {row['source_url'] for row in sources}
        rag_candidates = [row for row in rag_candidates if row.get('source_id') not in current_ids
                          and row.get('source_url') not in current_urls]
        return {
            'benchmark_cases': cases,
            'web_research_attempted': any(row.get('stage') == 'official_case_web' and row.get('status') != 'skipped' for row in trace),
            # RAG 후보도 실제 검수 문맥으로 전달하되 정형 사례 카드로 자동 승격하지 않는다.
            'sources': [*sources, *rag_candidates],
            'case_search_policy': case_search_policy,
            'case_search_coverage': case_coverage,
            'research_gaps': list(dict.fromkeys(gaps)),
            'trace': trace,
        }
