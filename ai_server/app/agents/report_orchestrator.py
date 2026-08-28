"""다섯 Agent를 고정 순서로 실행하고 품질 미달 시 한 번만 재작성합니다."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import asyncio
import json
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any

from .case_study_agent import CaseStudyAgent
from .evidence_agent import EvidenceAgent
from ..openai_responses import OpenAIResponseError
from .planner_agent import PlannerAgent
from .reviewer_agent import ReviewerAgent
from .transferability_agent import TransferabilityAgent


# 같은 원자료·같은 조사 설정으로 다시 생성할 때 외부 자료조사를 반복하지 않습니다.
# 기획 작성과 품질 검수는 매번 새로 실행하므로 보고서 품질 검증 과정은 생략되지 않습니다.
_EVIDENCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CASE_STUDY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _evidence_cache_key(
    *,
    agent: EvidenceAgent,
    env_values: dict[str, Any],
    region_code: str,
    snapshot: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> str:
    relevant_settings = {
        'region_code': region_code,
        'snapshot': snapshot,
        'planning_brief': planning_brief,
        'research_model': env_values.get('OPENAI_RESEARCH_MODEL'),
        'web_enabled': env_values.get('ENABLE_OFFICIAL_WEB_RESEARCH'),
        'allowed_domains': env_values.get('TOURISM_ALLOWED_RESEARCH_DOMAINS'),
        'tour_base_url': env_values.get('TOUR_INFO_API_BASE_URL'),
        'embedding_model': env_values.get('OPENAI_EMBEDDING_MODEL'),
        'chroma_directory': env_values.get('CHROMA_PERSIST_DIRECTORY'),
        # 테스트 대역과 실제 Agent가 같은 캐시를 공유하지 않게 합니다.
        'agent_type': f'{type(agent).__module__}.{type(agent).__qualname__}',
    }
    serialized = json.dumps(relevant_settings, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(serialized.encode('utf-8')).hexdigest()


async def _collect_evidence(
    *,
    agent: EvidenceAgent,
    env_values: dict[str, Any],
    region_code: str,
    snapshot: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    ttl_seconds = max(0, int(float(env_values.get('EVIDENCE_CACHE_TTL_SECONDS') or 3600)))
    cache_key = _evidence_cache_key(
        agent=agent,
        env_values=env_values,
        region_code=region_code,
        snapshot=snapshot,
        planning_brief=planning_brief,
    )
    now = monotonic()
    cached = _EVIDENCE_CACHE.get(cache_key)
    if ttl_seconds and cached and now - cached[0] < ttl_seconds:
        return deepcopy(cached[1]), True

    evidence_pack = await agent.collect(region_code=region_code, snapshot=snapshot, planning_brief=planning_brief)
    if ttl_seconds:
        # 오래된 항목을 함께 정리해 개발 서버에서 캐시가 계속 커지지 않게 합니다.
        expired_keys = [key for key, (created_at, _) in _EVIDENCE_CACHE.items() if now - created_at >= ttl_seconds]
        for key in expired_keys:
            _EVIDENCE_CACHE.pop(key, None)
        _EVIDENCE_CACHE[cache_key] = (now, deepcopy(evidence_pack))
    return evidence_pack, False


def _case_study_cache_key(
    *,
    agent: CaseStudyAgent,
    env_values: dict[str, Any],
    region_code: str,
    snapshot: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> str:
    relevant_settings = {
        'region_code': region_code,
        'snapshot': snapshot,
        'planning_brief': planning_brief,
        'case_research_model': env_values.get('OPENAI_CASE_RESEARCH_MODEL'),
        'research_model': env_values.get('OPENAI_RESEARCH_MODEL'),
        'web_enabled': env_values.get('ENABLE_CASE_STUDY_WEB_RESEARCH'),
        'allowed_domains': env_values.get('TOURISM_ALLOWED_RESEARCH_DOMAINS'),
        'embedding_model': env_values.get('OPENAI_EMBEDDING_MODEL'),
        'chroma_directory': env_values.get('CHROMA_PERSIST_DIRECTORY'),
        'agent_type': f'{type(agent).__module__}.{type(agent).__qualname__}',
    }
    serialized = json.dumps(relevant_settings, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(serialized.encode('utf-8')).hexdigest()


async def _collect_case_studies(
    *,
    agent: CaseStudyAgent,
    env_values: dict[str, Any],
    region_code: str,
    snapshot: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    ttl_seconds = max(0, int(float(env_values.get('CASE_STUDY_CACHE_TTL_SECONDS') or 21600)))
    cache_key = _case_study_cache_key(
        agent=agent,
        env_values=env_values,
        region_code=region_code,
        snapshot=snapshot,
        planning_brief=planning_brief,
    )
    now = monotonic()
    cached = _CASE_STUDY_CACHE.get(cache_key)
    if ttl_seconds and cached and now - cached[0] < ttl_seconds:
        return deepcopy(cached[1]), True

    case_pack = await agent.collect(region_code=region_code, snapshot=snapshot, planning_brief=planning_brief)
    if ttl_seconds:
        expired_keys = [key for key, (created_at, _) in _CASE_STUDY_CACHE.items() if now - created_at >= ttl_seconds]
        for key in expired_keys:
            _CASE_STUDY_CACHE.pop(key, None)
        _CASE_STUDY_CACHE[cache_key] = (now, deepcopy(case_pack))
    return case_pack, False


async def orchestrate_strategy_report(
    *,
    project_root: Path,
    env_values: dict[str, Any],
    region_code: str,
    snapshot: dict[str, Any],
    report_schema: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = str(env_values.get('OPENAI_API_KEY') or '').strip()
    report_model = str(
        env_values.get('OPENAI_REPORT_MODEL')
        or env_values.get('OPENAI_MODEL')
        or 'gpt-5.6'
    ).strip()
    review_model = str(env_values.get('OPENAI_REVIEW_MODEL') or report_model).strip()
    trace: list[dict[str, Any]] = []

    evidence_agent = EvidenceAgent(project_root=project_root, env_values=env_values)
    case_study_agent = CaseStudyAgent(project_root=project_root, env_values=env_values)
    started = perf_counter()
    evidence_result, case_result = await asyncio.gather(
        _collect_evidence(
            agent=evidence_agent,
            env_values=env_values,
            region_code=region_code,
            snapshot=snapshot,
            planning_brief=planning_brief,
        ),
        _collect_case_studies(
            agent=case_study_agent,
            env_values=env_values,
            region_code=region_code,
            snapshot=snapshot,
            planning_brief=planning_brief,
        ),
    )
    evidence_pack, evidence_cache_hit = evidence_result
    # 사용자가 입력한 여건을 snapshot(공식 관측값)에 섞지 않습니다.
    evidence_pack['planning_brief'] = deepcopy(planning_brief)
    case_pack, case_cache_hit = case_result
    trace.extend(evidence_pack.pop('trace', []))
    trace.extend(case_pack.pop('trace', []))
    trace.append({
        'agent': 'evidence',
        'stage': 'cache' if evidence_cache_hit else 'complete',
        'status': 'hit' if evidence_cache_hit else 'completed',
        'duration_ms': round((perf_counter() - started) * 1000),
    })
    trace.append({
        'agent': 'case_scout',
        'stage': 'cache' if case_cache_hit else 'complete',
        'status': 'hit' if case_cache_hit else 'completed',
        'duration_ms': round((perf_counter() - started) * 1000),
    })

    evidence_pack['benchmark_cases'] = case_pack.get('benchmark_cases') or []
    evidence_pack['research_gaps'] = list(dict.fromkeys([
        *(evidence_pack.get('research_gaps') or []),
        *(case_pack.get('research_gaps') or []),
    ]))
    sources = [*(evidence_pack.get('sources') or []), *(case_pack.get('sources') or [])]
    evidence_pack['sources'] = list({
        str(source['source_id']): source for source in sources if source.get('source_id')
    }.values())

    transfer_model = str(
        env_values.get('OPENAI_TRANSFER_MODEL')
        or env_values.get('OPENAI_REPORT_MODEL')
        or env_values.get('OPENAI_MODEL')
        or 'gpt-5.6'
    ).strip()
    started = perf_counter()
    transfer_assessment = await TransferabilityAgent(api_key=api_key, model=transfer_model).assess(
        evidence_pack=evidence_pack,
    )
    evidence_pack['transfer_assessment'] = transfer_assessment
    trace.append({
        'agent': 'transferability',
        'stage': 'assessment',
        'status': 'completed',
        'recommended_cases': len(transfer_assessment.get('recommended_case_ids') or []),
        'duration_ms': round((perf_counter() - started) * 1000),
    })

    planner = PlannerAgent(api_key=api_key, model=report_model, report_schema=report_schema)
    reviewer = ReviewerAgent(api_key=api_key, model=review_model)

    started = perf_counter()
    draft = await planner.write(evidence_pack)
    trace.append({'agent': 'planner', 'stage': 'draft', 'status': 'completed', 'duration_ms': round((perf_counter() - started) * 1000)})

    started = perf_counter()
    review = await reviewer.review(evidence_pack=evidence_pack, draft_report=draft)
    trace.append({'agent': 'reviewer', 'stage': 'first_review', 'status': 'completed', 'score': review['overall_score'], 'duration_ms': round((perf_counter() - started) * 1000)})

    revised = False
    if not review['approved']:
        revised = True
        original_draft = draft
        started = perf_counter()
        try:
            draft = await planner.write(evidence_pack, revision_feedback=review)
        except OpenAIResponseError as exc:
            # 외부 모델이 수정 요청을 거절하거나 지연되어도 검수되지 않은 결과를 승인하거나
            # API 전체를 실패시키지 않고, 기존 초안과 실패한 검수 상태를 그대로 반환합니다.
            draft = original_draft
            review['approved'] = False
            review['revision_error_code'] = exc.code
            trace.append({
                'agent': 'planner',
                'stage': 'revision',
                'status': 'failed',
                'error_code': exc.code,
                'duration_ms': round((perf_counter() - started) * 1000),
            })
        else:
            trace.append({'agent': 'planner', 'stage': 'revision', 'status': 'completed', 'duration_ms': round((perf_counter() - started) * 1000)})

            started = perf_counter()
            try:
                review = await reviewer.review(evidence_pack=evidence_pack, draft_report=draft)
            except OpenAIResponseError as exc:
                review['approved'] = False
                review['final_review_error_code'] = exc.code
                trace.append({
                    'agent': 'reviewer',
                    'stage': 'final_review',
                    'status': 'failed',
                    'error_code': exc.code,
                    'duration_ms': round((perf_counter() - started) * 1000),
                })
            else:
                trace.append({'agent': 'reviewer', 'stage': 'final_review', 'status': 'completed', 'score': review['overall_score'], 'duration_ms': round((perf_counter() - started) * 1000)})

    review['revised_once'] = revised
    return {
        'report': draft,
        'quality_review': review,
        'evidence_sources': evidence_pack['sources'],
        'research_gaps': evidence_pack['research_gaps'],
        'agent_trace': trace,
    }
