"""Agent 2: 공식 관광사업의 실행 방식·성과·적용 조건을 사례 카드로 수집합니다."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..openai_responses import OpenAIResponseError, create_structured_response
from ..rag_store import OfficialTourismRagStore
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
    for line in registry_path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        source_url = str(record.get('source_url') or '')
        if not _url_is_allowed(source_url, domains):
            continue
        cards.append({
            'source_id': str(record.get('source_id') or _case_source_id(source_url)),
            'case_region': str(record.get('case_region') or record.get('region_name') or '전국 공통'),
            'intervention': str(record.get('intervention') or record.get('title') or ''),
            'problem_addressed': str(record.get('problem_addressed') or ''),
            'target_group': str(record.get('target_group') or ''),
            'operating_model': str(record.get('operating_model') or record.get('content') or '')[:1400],
            'duration': str(record.get('duration') or '공식 자료에서 확인되지 않음'),
            'public_budget': str(record.get('public_budget') or '공식 자료에서 확인되지 않음'),
            'observed_result': str(record.get('observed_result') or '공식 자료에서 확인되지 않음'),
            'measurement_period': str(record.get('measurement_period') or '공식 자료에서 확인되지 않음'),
            'evidence_strength': str(record.get('evidence_strength') or 'low'),
            'transfer_conditions': list(record.get('transfer_conditions') or []),
            'risks': list(record.get('risks') or []),
            'source_title': str(record.get('title') or '공식 관광사업 사례'),
            'source_url': source_url,
            'published_or_updated_at': str(record.get('published_or_updated_at') or ''),
        })
    return cards


class CaseStudyAgent:
    """일반 아이디어가 아니라 공식 자료에서 확인된 사업 사례만 반환합니다."""

    def __init__(self, *, project_root: Path, env_values: dict[str, Any]) -> None:
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

    async def collect(self, *, region_code: str, snapshot: dict[str, Any], planning_brief: dict[str, Any] | None = None) -> dict[str, Any]:
        # 1) 팀이 먼저 검수한 JSONL 사례, 2) 영속 RAG, 3) 허용 도메인 웹 검색 순서로 근거를 모읍니다.
        # 어느 단계가 실패했는지는 trace·research_gaps에 남겨 Planner와 Reviewer가 알 수 있게 합니다.
        curated_cards = _load_curated_case_cards(self.project_root, self.domains)
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
            ).search(
                query=(
                    f"{snapshot['region_name']} 방문 소비 체류 개선 할인 환급 쿠폰 숙박 야간관광 "
                    '지역상권 결제 성과평가 예산 집행 사례 '
                    + ' '.join((snapshot.get('ml_analysis') or {}).get('research_questions') or [])
                ),
                region_code=region_code,
                region_name=snapshot['region_name'],
                top_k=8,
            )
            trace.append({'agent': 'case_scout', 'stage': 'case_rag', 'status': 'completed', 'items': len(rag_candidates)})
            if not rag_candidates:
                gaps.append('성과·운영 방식이 정리된 공식 사례 RAG 문서가 아직 충분하지 않음')
        except Exception as exc:
            gaps.append(f'공식 사례 RAG 검색 불가: {type(exc).__name__}')
            trace.append({'agent': 'case_scout', 'stage': 'case_rag', 'status': 'failed', 'items': 0})

        # 라이브 웹 검색은 선택 기능입니다. 꺼져 있거나 API 키가 없으면 검수된 카드만 사용합니다.
        web_enabled = str(self.env_values.get('ENABLE_CASE_STUDY_WEB_RESEARCH') or 'true').lower() == 'true'
        if not self.api_key or not web_enabled:
            gaps.append('공식 성공사례 웹 조사가 비활성화되었거나 OpenAI 키가 없음')
            cases = curated_cards
            trace.append({'agent': 'case_scout', 'stage': 'official_case_web', 'status': 'skipped', 'items': 0})
        else:
            try:
                result = await create_structured_response(
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
                        'curated_case_cards': curated_cards,
                        'case_rag_candidates': rag_candidates,
                        'required_case_types': [
                            '할인·환급·지역쿠폰으로 소비를 유도한 사업',
                            '숙박·야간관광으로 체류를 늘린 사업',
                            '교통·관광·지역업체 혜택을 결합한 사업',
                            '행사 또는 재방문 프로그램을 성과 측정한 사업',
                        ],
                    },
                    schema_name='official_tourism_case_studies',
                    schema=CASE_STUDY_SCHEMA,
                    reasoning_effort='medium',
                    max_output_tokens=10000,
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
            except OpenAIResponseError as exc:
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
        sources = [{
            'source_id': case['source_id'],
            'source_type': 'benchmark_case',
            'title': case['source_title'],
            'source_url': case['source_url'],
            'published_or_updated_at': case['published_or_updated_at'],
            'summary': f"{case['case_region']} · {case['intervention']} · {case['observed_result']}",
            'evidence_strength': case['evidence_strength'],
        } for case in cases]
        return {
            'benchmark_cases': cases,
            'sources': sources,
            'research_gaps': list(dict.fromkeys(gaps)),
            'trace': trace,
        }
