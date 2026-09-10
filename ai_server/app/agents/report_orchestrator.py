"""다섯 Agent를 고정 순서로 실행하고 품질 미달 시 한 번만 재작성합니다."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import asyncio
import json
import logging
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any

from .case_study_agent import CaseStudyAgent
from .evidence_agent import EvidenceAgent
from .plan_quality_gate import build_plan_quality_precheck, merge_quality_precheck
from .planning_requirements import (
    QUALITY_CONTRACT_VERSION, build_completion_checklist, candidate_delivery_issues,
    stabilize_candidate_decision,
)
from ..openai_responses import OpenAIResponseError
from ..evidence_sources import merge_evidence_sources
from ..llm.errors import LLMProviderError
from ..llm.router import LLMRouter
from .planner_agent import PlannerAgent
from .reviewer_agent import ReviewerAgent
from .transferability_agent import TransferabilityAgent
from .decision_facts import build_decision_facts
from ...ml.planning_evidence import build_planning_ml_evidence


# 같은 원자료·같은 조사 설정으로 다시 생성할 때 외부 자료조사를 반복하지 않습니다.
# 기획 작성과 품질 검수는 매번 새로 실행하므로 보고서 품질 검증 과정은 생략되지 않습니다.
_EVIDENCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CASE_STUDY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
# 지역 맞춤 사례 조사 관점·후보 다양성 계약을 바꾸면 같은 서버 안의 기존 조사 캐시도 재사용하지 않습니다.
RESEARCH_CONTRACT_VERSION = '2026-09-07-nationwide-execution-evidence-v3'
LOGGER = logging.getLogger(__name__)


def _rag_registry_hash(agent: Any, filename: str) -> str:
    """검수 RAG 레지스트리가 바뀌면 짧은 조사 캐시도 즉시 무효화합니다."""
    if not hasattr(agent, 'project_root'):
        return ''
    path = agent.project_root / 'data' / 'rag' / filename
    return sha256(path.read_bytes()).hexdigest() if path.exists() else ''


async def _run_openai_stage(stage_code: str, stage_label: str, awaitable: Any) -> Any:
    """실패 메시지에 Agent 단계를 붙여 재시도 전에 병목을 찾을 수 있게 합니다."""
    started = perf_counter()
    LOGGER.info('Strategy Agent stage started: %s', stage_code)
    try:
        result = await awaitable
    except (OpenAIResponseError, LLMProviderError) as exc:
        LOGGER.warning(
            'Strategy Agent stage failed: %s code=%s duration_ms=%s',
            stage_code, exc.code, round((perf_counter() - started) * 1000),
        )
        raise OpenAIResponseError(
            f'{stage_code.upper()}_{exc.code}',
            f'{stage_label} 단계에서 처리하지 못했습니다: {exc.message}',
            status_code=exc.status_code,
        ) from exc
    LOGGER.info(
        'Strategy Agent stage completed: %s duration_ms=%s',
        stage_code, round((perf_counter() - started) * 1000),
    )
    return result


def _evidence_cache_key(
    *,
    agent: EvidenceAgent,
    env_values: dict[str, Any],
    region_code: str,
    snapshot: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> str:
    relevant_settings = {
        'contract_version': RESEARCH_CONTRACT_VERSION,
        'routing': getattr(agent, 'llm_router', None).public_config() if getattr(agent, 'llm_router', None) else None,
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
        'case_registry_hash': _rag_registry_hash(agent, 'official_case_studies.jsonl'),
        # 정책·지표 해석 PDF를 새로 등록하면 이전 1시간 근거 캐시를 재사용하지 않습니다.
        'reference_registry_hash': _rag_registry_hash(agent, 'official_reference_documents.jsonl'),
        # 원문 페이지 청크도 실제 RAG 입력이므로 재생성·보완하면 근거 캐시를 즉시 비웁니다.
        'reference_chunk_registry_hash': _rag_registry_hash(agent, 'official_reference_chunks.jsonl'),
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
    if ttl_seconds and not any(row.get('status') == 'failed' for row in evidence_pack.get('trace') or []):
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
        'contract_version': RESEARCH_CONTRACT_VERSION,
        'routing': getattr(agent, 'llm_router', None).public_config() if getattr(agent, 'llm_router', None) else None,
        'region_code': region_code,
        'snapshot': snapshot,
        'planning_brief': planning_brief,
        'case_research_model': env_values.get('OPENAI_CASE_RESEARCH_MODEL'),
        'case_registry_hash': _rag_registry_hash(agent, 'official_case_studies.jsonl'),
        # Case Scout도 같은 RAG 참고문서를 받아 적용 조건을 판별하므로 별도 캐시를 무효화합니다.
        'reference_registry_hash': _rag_registry_hash(agent, 'official_reference_documents.jsonl'),
        'reference_chunk_registry_hash': _rag_registry_hash(agent, 'official_reference_chunks.jsonl'),
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
    # 한 번의 통신 오류를 6시간 캐시해 다음 기획에도 자료가 빠지는 일을 막습니다.
    if ttl_seconds and not any(row.get('status') == 'failed' for row in case_pack.get('trace') or []):
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
    # Agent는 Provider를 고르지 않고 Router에 요청만 전달합니다. 실행 당시 설정은 trace에 고정합니다.
    llm_router = LLMRouter(project_root=project_root, env_values=env_values)
    trace.append({'agent': 'llm_router', 'stage': 'routing_snapshot', 'status': 'completed',
                  'routing': llm_router.public_config(), 'effective_routes': llm_router.effective_routes()})
    from ..generation_progress import notify_progress
    notify_progress(0, '생성 준비: Qwen·Gemma 연결을 확인하고 있습니다.')
    await _run_openai_stage('local_preflight', '로컬 모델 연결 확인', llm_router.preflight_local_models())

    # OpenAI가 개입하기 전에 저장 모델로 숫자를 계산합니다. 원본 snapshot·사용자 조건은 변경하지 않습니다.
    snapshot = deepcopy(snapshot)
    notify_progress(0, '지역 원자료와 저장된 머신러닝 모델의 관광지표 전망을 확인하고 있습니다.')
    ml_evidence = await asyncio.to_thread(
        build_planning_ml_evidence, region_code, snapshot['region_name'], planning_brief,
    )
    snapshot['ml_analysis'] = ml_evidence.model_dump(mode='json')
    if (planning_brief or {}).get('input_profile') == 'guided_v1' and not snapshot['ml_analysis'].get('horizon_policy', {}).get('coverage_complete'):
        raise OpenAIResponseError('PLANNING_PERIOD_UNSUPPORTED', '선택한 3개월 전체의 ML 전망을 제공할 수 없습니다. 시작 월을 앞당기거나 최신 데이터를 반영해 주세요.', status_code=422)
    snapshot['decision_facts'] = build_decision_facts(snapshot)
    trace.append({'agent': 'ml', 'stage': 'forecast_evidence', 'status': ml_evidence.status,
                  'reason_code': ml_evidence.reason_code,
                  'forecast_horizon_months': ml_evidence.horizon_policy.get('forecast_horizon_months'),
                  'selection_basis': ml_evidence.horizon_policy.get('selection_basis')})

    evidence_agent = EvidenceAgent(project_root=project_root, env_values=env_values, llm_router=llm_router)
    case_study_agent = CaseStudyAgent(project_root=project_root, env_values=env_values, llm_router=llm_router)
    started = perf_counter()
    notify_progress(1, '지역의 공식 근거와 타지역 관광사업 사례를 확인하고 있습니다.')
    evidence_result, case_result = await asyncio.gather(
        _run_openai_stage('evidence', '지역 근거 조사', _collect_evidence(
            agent=evidence_agent,
            env_values=env_values,
            region_code=region_code,
            snapshot=snapshot,
            planning_brief=planning_brief,
        )),
        _run_openai_stage('case_scout', '공식 사례 조사', _collect_case_studies(
            agent=case_study_agent,
            env_values=env_values,
            region_code=region_code,
            snapshot=snapshot,
            planning_brief=planning_brief,
        )),
    )
    evidence_pack, evidence_cache_hit = evidence_result
    # 사용자가 입력한 여건을 snapshot(공식 관측값)에 섞지 않습니다.
    evidence_pack['planning_brief'] = deepcopy(planning_brief)
    # 테스트 대역·다른 근거 수집기에서도 동일한 검증 snapshot이 후속 3개 Agent에 전달됩니다.
    evidence_pack['snapshot'] = snapshot
    case_pack, case_cache_hit = case_result
    trace.extend(evidence_pack.pop('trace', []))
    trace.extend(case_pack.pop('trace', []))
    trace.extend(llm_router.consume_trace())
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
    evidence_pack['case_search_policy'] = case_pack.get('case_search_policy') or {}
    evidence_pack['case_search_coverage'] = case_pack.get('case_search_coverage') or {}
    evidence_pack['research_gaps'] = list(dict.fromkeys([
        *(evidence_pack.get('research_gaps') or []),
        *(case_pack.get('research_gaps') or []),
    ]))
    evidence_pack['sources'] = merge_evidence_sources(
        evidence_pack.get('sources') or [], case_pack.get('sources') or [],
    )

    transfer_model = str(
        env_values.get('OPENAI_TRANSFER_MODEL')
        or env_values.get('OPENAI_REPORT_MODEL')
        or env_values.get('OPENAI_MODEL')
        or 'gpt-5.6'
    ).strip()
    evidence_pack['quality_contract_version'] = QUALITY_CONTRACT_VERSION
    started = perf_counter()
    notify_progress(2, 'Qwen이 공식 사례를 비교하고 지역에 적용할 사업 후보를 설계하고 있습니다.')
    transfer_assessment = await _run_openai_stage(
        'transferability',
        '지역 적용 가능성 검토',
        TransferabilityAgent(api_key=api_key, model=transfer_model, llm_router=llm_router).assess(evidence_pack=evidence_pack),
    )
    trace.extend(llm_router.consume_trace())
    # 저장된 사례가 실제 지역 문제에 부족하다고 Qwen이 판단한 경우에만 공식 웹 보강 1회를 허용합니다.
    if (llm_router.local_first and not llm_router.student_budget
            and transfer_assessment.get('selection_status') == 'needs_evidence' and not case_pack.get('web_research_attempted')):
        augmented = await _run_openai_stage('case_scout_supplement', '부족한 공식 사례 보강', case_study_agent.collect(
            region_code=region_code, snapshot=snapshot, planning_brief=planning_brief, force_web=True,
        ))
        trace.extend(augmented.pop('trace', []))
        trace.extend(llm_router.consume_trace())
        previous_cases = {row['source_id']: row for row in evidence_pack['benchmark_cases']}
        previous_cases.update({row['source_id']: row for row in augmented.get('benchmark_cases') or []})
        evidence_pack['benchmark_cases'] = list(previous_cases.values())
        evidence_pack['case_search_policy'] = augmented.get('case_search_policy') or evidence_pack.get('case_search_policy', {})
        evidence_pack['case_search_coverage'] = augmented.get('case_search_coverage') or evidence_pack.get('case_search_coverage', {})
        evidence_pack['sources'] = merge_evidence_sources(
            evidence_pack['sources'], augmented.get('sources') or [],
        )
        evidence_pack['research_gaps'] = list(dict.fromkeys(evidence_pack['research_gaps'] + augmented.get('research_gaps', [])))
        if augmented.get('web_research_attempted') and augmented.get('benchmark_cases'):
            transfer_assessment = await _run_openai_stage('transferability_recheck', '보강 사례 적용성 재검토',
                TransferabilityAgent(api_key=api_key, model=transfer_model, llm_router=llm_router).assess(evidence_pack=evidence_pack))
    evidence_pack['transfer_assessment'] = transfer_assessment
    # 본문 작성자는 후보 선정 JSON을 고칠 수 없다. 작성 가능한 누락이 있을 때만 Qwen에게
    # 보유 근거로 1회 보완시킨다. 새 검색/유료 폴백/무제한 재시도는 하지 않는다.
    candidate_issues = candidate_delivery_issues(evidence_pack, transfer_assessment)
    if llm_router.local_first and candidate_issues and len(evidence_pack.get('benchmark_cases') or []) >= 2:
        try:
            repaired = await TransferabilityAgent(api_key=api_key, model=transfer_model, llm_router=llm_router).assess(
                evidence_pack=evidence_pack, revision_feedback=candidate_issues,
            )
        except (OpenAIResponseError, LLMProviderError) as exc:
            trace.append({'agent': 'transferability', 'stage': 'candidate_repair', 'status': 'failed', 'error_code': exc.code})
        else:
            transfer_assessment = repaired
            evidence_pack['transfer_assessment'] = repaired
            trace.append({'agent': 'transferability', 'stage': 'candidate_repair', 'status': 'completed',
                          'remaining_issues': len(candidate_delivery_issues(evidence_pack, repaired)),
                          'selection_status': repaired.get('selection_status')})
        trace.extend(llm_router.consume_trace())
    trace.append({
        'agent': 'transferability',
        'stage': 'assessment',
        'status': 'completed',
        'recommended_cases': len(transfer_assessment.get('recommended_case_ids') or []),
        'duration_ms': round((perf_counter() - started) * 1000),
    })
    trace.extend(llm_router.consume_trace())

    remaining = candidate_delivery_issues(evidence_pack, transfer_assessment)
    if 'selection_status' in transfer_assessment:
        # 출처 ID, 타지역 범위, 확정처럼 보이는 예산과 측정 분모처럼 규칙으로 안전하게
        # 고칠 수 있는 값은 서버 계약으로 한 번 보정한다. 원래 LLM 판단은 correction
        # 기록에 남기며, 보정됐다는 이유로 ready/승인으로 바꾸지 않는다.
        transfer_assessment, corrections = stabilize_candidate_decision(evidence_pack, transfer_assessment)
        if (planning_brief or {}).get('input_profile') == 'guided_v1':
            from ..case_recommendation import constrain_decision
            transfer_assessment = constrain_decision(transfer_assessment, evidence_pack.get('benchmark_cases') or [], planning_brief)
        evidence_pack['transfer_assessment'] = transfer_assessment
        trace.append({
            'agent': 'transferability', 'stage': 'candidate_stabilization',
            'status': 'completed' if corrections else 'skipped',
            'corrections': len(corrections),
        })
        remaining = candidate_delivery_issues(evidence_pack, transfer_assessment)

    critical_remaining = [row for row in remaining if row.get('severity') == 'critical']
    if critical_remaining:
        # 근거 조작처럼 기계적으로 안전하게 복구하지 못한 항목만 본문 작성을 막는다.
        raise OpenAIResponseError(
            'TRANSFERABILITY_CANDIDATE_VALIDATION_FAILED',
            '지역 적용 가능성 검토에서 안전하게 복구할 수 없는 후보 오류가 남았습니다. '
            '본문 작성과 후속 유료 검수는 시작하지 않았습니다. '
            + ' / '.join(dict.fromkeys(row['problem'] for row in critical_remaining)),
            status_code=422, attempts=trace,
        )
    if remaining:
        # 지역 적합성·후보 차별성처럼 의미 판단이 필요한 보완은 Planner에게 명시하고
        # 검토용 본문을 보존한다. 최종 quality gate의 major 판정과 승인 기준은 유지한다.
        evidence_pack['candidate_validation_findings'] = remaining
        transfer_assessment['selection_status'] = 'needs_evidence'
        trace.append({
            'agent': 'transferability', 'stage': 'candidate_quality_handoff',
            'status': 'needs_review', 'remaining_issues': len(remaining),
        })

    planner = PlannerAgent(api_key=api_key, model=report_model, report_schema=report_schema, llm_router=llm_router)
    reviewer = ReviewerAgent(api_key=api_key, model=review_model, llm_router=llm_router)

    started = perf_counter()
    notify_progress(2, 'Gemma가 선정한 사업과 근거를 바탕으로 기획서 초안을 작성하고 있습니다.')
    draft = await _run_openai_stage('planner_draft', '기획안 초안 작성', planner.write(evidence_pack))
    notify_progress(3, '초안의 수치·출처·실행 계획을 코드와 검수 모델로 확인하고 있습니다.')
    trace.append({'agent': 'planner', 'stage': 'draft', 'status': 'completed', 'duration_ms': round((perf_counter() - started) * 1000)})
    trace.extend(llm_router.consume_trace())

    started = perf_counter()
    precheck = build_plan_quality_precheck(evidence_pack, draft)
    review_failed = False
    try:
        review = await reviewer.review(evidence_pack=evidence_pack, draft_report=draft, deterministic_precheck=precheck)
    except (OpenAIResponseError, LLMProviderError) as exc:
        # 작성 이후 연결이 끊겨도 초안을 버리지 않습니다. 검수 실패를 점수나 승인으로 위장하지 않습니다.
        review_failed = True
        review = {'approved': False, 'overall_score': 0, 'dimension_scores': {}, 'strengths': [], 'issues': [],
                  'review_error_code': exc.code, 'summary': '1차 검수를 완료하지 못했습니다. 초안은 보존했으며 품질 점수는 미평가입니다.'}
        trace.append({'agent': 'reviewer', 'stage': 'first_review', 'status': 'failed', 'error_code': exc.code})
    else:
        review = merge_quality_precheck(review, precheck)
        trace.append({'agent': 'reviewer', 'stage': 'first_review', 'status': 'completed', 'score': review['overall_score'], 'duration_ms': round((perf_counter() - started) * 1000)})
    trace.extend(llm_router.consume_trace())

    revised = False
    if not review['approved'] and not review_failed:
        revised = True
        original_draft = draft
        started = perf_counter()
        notify_progress(3, '품질검토에서 찾은 보완 사항을 Gemma가 초안에 반영하고 있습니다.')
        revision_checks = build_plan_quality_precheck(evidence_pack, original_draft, limit=None)
        revision_feedback = merge_quality_precheck(review, revision_checks, limit=None)
        try:
            draft = await planner.write(
                evidence_pack,
                revision_feedback=revision_feedback,
                previous_draft=original_draft,
            )
        except (OpenAIResponseError, LLMProviderError) as exc:
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
            trace.extend(llm_router.consume_trace())

            started = perf_counter()
            try:
                precheck = build_plan_quality_precheck(evidence_pack, draft)
                notify_progress(3, '수정된 기획안의 근거와 내용을 다시 검토하고 있습니다.')
                review = await reviewer.review(
                    evidence_pack=evidence_pack, draft_report=draft, deterministic_precheck=precheck,
                    final_pass=not llm_router.local_first,
                )
                review = merge_quality_precheck(review, precheck)
            except (OpenAIResponseError, LLMProviderError) as exc:
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
                trace.append({'agent': 'reviewer', 'stage': 'local_recheck' if llm_router.local_first else 'final_review', 'status': 'completed', 'score': review['overall_score'], 'duration_ms': round((perf_counter() - started) * 1000)})
                trace.extend(llm_router.consume_trace())

    if llm_router.local_first:
        review['final_audit_completed'] = False
        if review.get('approved'):
            started = perf_counter()
            notify_progress(3, '로컬 검토를 마친 기획안을 최종 검수하고 있습니다.')
            local_review = deepcopy(review)
            try:
                precheck = build_plan_quality_precheck(evidence_pack, draft)
                audit_pack = {**evidence_pack, 'local_review_findings': local_review}
                review = await reviewer.review(evidence_pack=audit_pack, draft_report=draft,
                                               deterministic_precheck=precheck, final_pass=True)
                review = merge_quality_precheck(review, precheck)
                review['final_audit_completed'] = True
                trace.append({'agent': 'reviewer', 'stage': 'cloud_final_audit', 'status': 'completed',
                              'score': review['overall_score'], 'duration_ms': round((perf_counter() - started) * 1000)})
            except (OpenAIResponseError, LLMProviderError) as exc:
                review = local_review
                review.update({'approved': False, 'final_audit_completed': False, 'final_review_error_code': exc.code,
                               'summary': '로컬 사전 검수 후 독립 최종 검수를 완료하지 못했습니다. 집행 승인 상태가 아닙니다.'})
        else:
            trace.append({'agent': 'reviewer', 'stage': 'cloud_final_audit', 'status': 'skipped',
                          'reason': 'local_quality_gate_not_passed'})

    review['revised_once'] = revised
    # LLM에는 상위 8개만 보내지만 화면에는 코드 점검 전체와 구체적인 보완 목록을 남긴다.
    all_checks = build_plan_quality_precheck(evidence_pack, draft, limit=None)
    review = merge_quality_precheck(review, all_checks, limit=None)
    review['validation_findings'] = all_checks['issues']
    review['quality_contract_version'] = QUALITY_CONTRACT_VERSION
    review['completion_checklist'] = build_completion_checklist(
        {**review, 'issues': [*(review.get('issues') or []), *all_checks['issues']]}, evidence_pack, draft,
    )
    # 실패한 폴백도 마지막까지 남기되 첨부 본문은 저장하지 않습니다.
    trace.extend(llm_router.consume_trace())
    return {
        'planning_decision': transfer_assessment,
        'ml_analysis': snapshot['ml_analysis'],
        'report': draft,
        'quality_review': review,
        'evidence_sources': evidence_pack['sources'],
        'research_gaps': evidence_pack['research_gaps'],
        'agent_trace': trace,
    }
