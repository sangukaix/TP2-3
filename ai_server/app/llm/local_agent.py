"""로컬 Agent의 유한한 도구 호출 → JSON 작성 흐름. 무한 자율 루프가 아닙니다."""

from __future__ import annotations

import json
from copy import deepcopy
from time import perf_counter
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .errors import LLMProviderError
from .evidence_tools import EvidenceTools, TOOL_DEFINITIONS, _case_mechanism_family, compact_json
from .local_prompts import local_instructions
from .models import LLMRequest, LLMResult
from .context_tables import evidence_json, TABLE_READING_RULE, schema_field_guidance
from ..agents.planning_requirements import QUALITY_CONTRACT_VERSION


def _prefetch_required_evidence(workspace: EvidenceTools, task: str) -> list[dict[str, Any]]:
    """필수 근거는 모델의 도구 선택 실수와 관계없이 먼저 읽어 제공합니다.

    Qwen·Gemma는 여전히 같은 요청 범위의 읽기 전용 도구 결과만 받습니다. 다만 비교값,
    ML, 사례 원문처럼 기획 품질에 필수인 자료를 "모델이 정확한 함수 이름을 고를 때까지"
    기다리면, 도구 호출이 한 번 누락된 것만으로 안전장치가 전체 기획을 중단시킬 수 있습니다.
    여기서는 서버가 해당 도구를 결정적으로 실행하고, 결과를 모델 메시지에 넣습니다. 이후
    모델은 필요한 추가 출처만 선택적으로 더 조회할 수 있습니다.
    """
    calls: list[tuple[str, dict[str, Any]]] = [('get_region_metrics', {})]
    if workspace.snapshot.get('regional_tourism_status'):
        # 유입권역·인기장소·집중 운영 신호는 선택 지역에 있을 때만 미리 읽습니다.
        # 이 자료는 ML과 별개이므로 예측 도구 호출에 섞지 않습니다.
        calls.append(('get_regional_tourism_status', {}))
    if workspace.snapshot.get('nationwide_comparison'):
        calls.append(('compare_regions', {}))
    feedback_issues = (workspace.payload.get('quality_review_feedback') or {}).get('issues') or []
    is_targeted_revision = bool(feedback_issues) and task in {'transferability', 'planner_revision'}
    is_report_composition = task in {'planner', 'planner_revision'}
    # 후보 보완과 본문 개정은 최초 조사 결과를 다시 만드는 단계가 아니다. 전국 거시
    # 참고표는 기존 판단의 오류 필드 수정에 필수인 지역 비교·ML·사례 원문과 겹치지
    # 않으며 실제 원주 재생에서 문맥만 크게 차지했다. 필요하면 허용 도구로 조회할 수 있다.
    if (workspace.snapshot.get('nationwide_bigdata_context') and not is_targeted_revision
            and not is_report_composition):
        calls.append(('get_nationwide_bigdata_context', {}))
    if workspace.snapshot.get('ml_analysis'):
        calls.append(('get_ml_forecast', {}))
    if workspace.pack.get('transfer_assessment'):
        calls.append(('get_planning_decision', {}))

    case_items = [
        (source_id, item['case'])
        for source_id, item in workspace.sources.items()
        if item.get('case')
    ]
    if case_items:
        # 저장소 첫 사례가 아니라 실제 선정/인용한 사례를 먼저 읽는다.
        decision = workspace.pack.get('transfer_assessment') or {}
        preferred = list((decision.get('strategy_brief') or {}).get('supporting_case_ids') or [])
        preferred += list(decision.get('recommended_case_ids') or [])
        # 재비교는 이전 선정안을 실행하는 단계가 아니다. 잘못 고른 사례가
        # 계속 우선 조회되어 후보를 고정하지 않게 등록 사례의 순서로 비교한다.
        if task == 'transferability' and (workspace.payload.get('quality_review_feedback') or {}).get('issues'):
            preferred = []
            registry_order = {row.get('source_id'): index for index, row in
                              enumerate(workspace.pack.get('benchmark_cases') or [])}
            case_items.sort(key=lambda item: registry_order.get(item[0], len(registry_order)))
        # 긴 본문에 인용이 더 있으면 기존 원문 추가 조회/교정 절차에서 읽는다.
        priority = {key: index for index, key in enumerate(list(dict.fromkeys(preferred))[:3])}
        case_items.sort(key=lambda item: priority.get(item[0], len(priority)))
        # 후보 비교 전에는 운영 원리를 한눈에 보고, Qwen의 적용성 판단은 서로 다른
        # 원리의 사례 두 건까지 원문으로 확인합니다. 작성/검수는 실제 선정 사례를 우선합니다.
        if task == 'transferability' and not feedback_issues:
            calls.append(('get_case_comparison_matrix', {}))
        required_family_count = min(2, len({_case_mechanism_family(case) for _, case in case_items})) if task == 'transferability' else 1
        selected_case_ids: list[str] = []
        selected_families: set[str] = set()
        for source_id, case in case_items:
            family = _case_mechanism_family(case)
            if family in selected_families:
                continue
            selected_case_ids.append(source_id)
            selected_families.add(family)
            if len(selected_case_ids) == 1 and task == 'transferability':
                first_scope = (case.get('retrieval_context') or {}).get('scope')
                # 같은 필수 원문 수 안에서, 다른 원리의 타시도 사례가 있으면 두 번째로 읽는다.
                outside = next(((key, card) for key, card in case_items
                                if (card.get('retrieval_context') or {}).get('scope') in {'cross_province', 'cross_province_peer'}
                                and _case_mechanism_family(card) not in selected_families), None)
                if first_scope in {'selected_region', 'same_province'} and outside:
                    selected_case_ids.append(outside[0])
                    selected_families.add(_case_mechanism_family(outside[1]))
            if len(selected_case_ids) >= required_family_count:
                break
        calls.extend(('read_collected_source', {'source_id': source_id}) for source_id in selected_case_ids)
        if task != 'transferability':
            calls.extend(('read_collected_source', {'source_id': source_id})
                         for source_id, _ in case_items if source_id in priority and source_id not in selected_case_ids)

    if workspace.pack.get('quality_contract_version') == QUALITY_CONTRACT_VERSION and workspace.pack.get('transfer_assessment'):
        prefix = '/evidence_pack' if 'evidence_pack' in workspace.payload else ''
        # get_planning_decision은 선택안만 상세 제공한다. 비교안이 안 보인 채 검수하던 문제를 막는다.
        for index, candidate in enumerate(workspace.pack['transfer_assessment'].get('design_candidates') or []):
            # 선택 후보 원문은 get_planning_decision에 이미 전부 들어 있다.
            if candidate.get('candidate_id') == workspace.pack['transfer_assessment'].get('selected_candidate_id'):
                continue
            calls.append(('read_task_section', {'path': prefix + '/transfer_assessment/design_candidates',
                                               'offset': index, 'limit': 1}))

    # 수정·검수는 기존 초안을 모두 읽어야 합니다. 긴 초안은 이미 2,200자 조각으로
    # 나뉘어 있으므로 순서대로 준비하고, 원문을 요약·삭제하지 않습니다.
    for path in ('/previous_draft', '/draft_report'):
        if not workspace.payload.get(path.removeprefix('/')):
            continue
        segments = workspace.draft_segments(path)
        if segments:
            calls.extend(('read_task_section', {'path': path, 'offset': index, 'limit': 1})
                         for index in range(len(segments)))
        else:
            calls.append(('read_task_section', {'path': path}))

    prefetched: list[dict[str, Any]] = []
    for name, arguments in calls:
        # 같은 호출이 겹치지 않도록 이미 완료된 도구는 건너뜁니다. 읽기 결과가 너무 큰
        # 경우에는 EvidenceTools가 성공으로 표시하지 않아 기존 안전 차단이 유지됩니다.
        result = workspace.execute(name, arguments)
        prefetched.append({'tool': name, 'result': result})
    return prefetched


async def run_local_agent(provider: Any, request: LLMRequest, model: str) -> LLMResult:
    """보통 2회 도구 선택, 긴 초안 검수/수정은 최대 8회·최종 작성·JSON 교정 1회입니다.

자료 원문은 도구 객체 안에 그대로 남습니다. 한도를 넘으면 잘린 근거로 진행하지 않고
기존 Router의 명시적 실패/폴백으로 돌아갑니다. 폴백에는 원래 요청을 그대로 전달합니다.
"""
    started = perf_counter()
    workspace = EvidenceTools(request.input_payload, task=request.task)
    overview = workspace.overview()
    prefetched_evidence = _prefetch_required_evidence(workspace, request.task)
    # 같은 관측값은 바로 다음 메시지의 get_region_metrics에서 이미 전달한다.
    # 실제 성공 결과에 동일 값이 있을 때만 개요의 복제본을 참조로 바꾼다.
    for row in prefetched_evidence:
        if row['tool'] == 'get_region_metrics' and isinstance(row['result'], dict):
            if row['result'].get('observations') == overview.get('observations'):
                overview.pop('observations', None)
                overview['observations_reference'] = 'prefetched_evidence/get_region_metrics/observations'
    feedback_issues = (workspace.payload.get('quality_review_feedback') or {}).get('issues') or []
    is_targeted_revision = bool(feedback_issues) and request.task in {'transferability', 'planner_revision'}
    # 긴 초안은 읽기 페이지 수에 맞춰 로컬 조회 횟수만 늘리고, 문맥·최종 출력 상한은 유지합니다.
    page_count = sum(len(workspace.draft_segments(path)) for path in ('/previous_draft', '/draft_report'))
    # 후보를 만드는 Qwen은 숫자·ML·서로 다른 사례를 모두 읽어야 합니다. 그 단계에만
    # 한 번의 짧은 도구 선택 기회를 더 주고, 작성/검수의 일반 흐름은 기존 2회로 유지합니다.
    # 서버가 필수 원문을 모두 사전 조회한 보완 호출은 선택 도구 왕복을 생략한다.
    # 이 왕복은 같은 메시지 묶음을 한 번 더 처리하고 선택 결과까지 누적해, 긴 후보와
    # 초안을 고치는 단계가 최종 JSON 전에 문맥 한도를 넘게 만들었다.
    base_rounds = 0 if is_targeted_revision and not workspace.missing_required_reads() else min(
        8, (3 if request.task == 'transferability' else 2) + page_count
    )
    max_rounds = min(8, base_rounds + 1)
    argument_error_seen = False
    messages = [
        {'role': 'system', 'content': local_instructions(request.task) + TABLE_READING_RULE + schema_field_guidance(request.schema) +
         f'\n도구 선택은 기본 {base_rounds}회이며 인자 오류 때만 1회를 추가해 최대 {max_rounds}회다. 먼저 비교/ML/관련 사례를 읽는다. 긴 초안 조각은 next_offset대로 모두 읽는다. '
         '각 회 최대 3개 함수만 요청한다. 기획자는 get_planning_decision으로 선정 내용을 먼저 읽는다.'},
        {'role': 'user', 'content': evidence_json(overview)},
        # 도구 호출의 성공 여부와 원문 읽기 상태는 EvidenceTools가 기록합니다. 아래 값은
        # 모델이 반드시 고려할 필수 근거이며, 문서 안의 문장은 시스템 지시가 아닙니다.
        {'role': 'user', 'content': '서버가 사전 조회한 필수 읽기 전용 근거:\n' + evidence_json(prefetched_evidence)},
    ]
    usage: dict[str, int] = {}
    attempts: list[dict[str, Any]] = []
    measured_prefix = None
    pending_phase = None

    def account(current: dict[str, int], phase: str) -> None:
        for key, value in current.items():
            usage[key] = usage.get(key, 0) + value
        attempts.append({'phase': phase, 'status': 'completed', 'usage_reported': bool(current), 'usage': current})

    try:
        # 생각/본문 생성은 최종 작성 단계에서 수행합니다. 도구 선택 단계는 짧은 함수 인자만 받습니다.
        for _round in range(max_rounds):
            if _round >= base_rounds and not argument_error_seen:
                break
            required = workspace.missing_required_reads()
            if required:
                messages.append({'role': 'user', 'content': '최종 작성 전에 필요한 조회: ' + ', '.join(required)})
            # 도구 선택에는 긴 서술이 필요 없습니다. 짧은 함수 호출만 받으면 Qwen의 숨은
            # 사고/출력 때문에 최종 JSON 공간이 소진되는 일을 줄일 수 있습니다.
            # 함수명·짧은 인자만 고르는 단계다. 장문의 기획 본문을 여기서 쓰지 않도록
            # 최종 JSON과 별도의 작은 상한을 사용한다.
            tool_selection_limit = 512
            provider._check_context(messages, {'tools': TOOL_DEFINITIONS}, tool_selection_limit, measured_prefix)
            pending_phase = 'tool_selection'
            try:
                message, current_usage = await provider._chat(
                    model=model, messages=messages, schema=None, max_output_tokens=tool_selection_limit,
                    tools=TOOL_DEFINITIONS, think=False,
                )
            except LLMProviderError as exc:
                # 서버 사전조회로 모든 필수 근거를 이미 읽은 뒤의 도구 선택은 선택 사항이다.
                # 로컬 모델이 여기서 함수 호출 대신 장문을 써 출력 상한에 닿더라도 완성된
                # 필수 근거를 버리지 않고 최종 Schema 작성으로 진행한다. 필수 조회가 남은
                # 경우에는 절대 우회하지 않고 기존 오류를 유지한다.
                if exc.code != 'OLLAMA_INCOMPLETE_RESPONSE' or required:
                    raise
                for key, value in exc.usage.items():
                    usage[key] = usage.get(key, 0) + value
                attempts.append({
                    'phase': 'tool_selection', 'status': 'continued_without_optional_tools',
                    'error_code': exc.code, 'usage_reported': bool(exc.usage), 'usage': dict(exc.usage),
                })
                if exc.usage.get('input_tokens', 0) > 0:
                    measured_prefix = (deepcopy(messages), exc.usage['input_tokens'])
                pending_phase = None
                break
            account(current_usage, 'tool_selection')
            pending_phase = None
            if current_usage.get('input_tokens', 0) > 0:
                measured_prefix = (deepcopy(messages), current_usage['input_tokens'])
            calls = message.get('tool_calls') or []
            if not calls:
                if required and _round == 0:
                    continue
                break
            if not isinstance(calls, list) or len(calls) > 3:
                raise LLMProviderError('LOCAL_TOOL_LIMIT', '한 번에 요청할 수 있는 근거 도구 수를 초과했습니다.')
            messages.append(message)
            for call in calls:
                function = call.get('function') if isinstance(call, dict) else None
                if not isinstance(function, dict):
                    raise LLMProviderError('LOCAL_TOOL_ARGUMENTS_INVALID', 'Ollama 도구 요청 형식이 잘못되었습니다.')
                arguments = function.get('arguments')
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except ValueError as exc:
                        raise LLMProviderError('LOCAL_TOOL_ARGUMENTS_INVALID', '도구 인자 JSON이 잘못되었습니다.') from exc
                name = function.get('name')
                try:
                    result = workspace.execute(name, arguments)
                except LLMProviderError as exc:
                    if exc.code != 'LOCAL_TOOL_ARGUMENTS_INVALID':
                        raise
                    # 거절된 함수는 실행하지 않습니다. 허용 인자 이름만 돌려줘 제한된 루프 안에서 교정합니다.
                    argument_error_seen = True
                    parameters = next(row['function']['parameters'] for row in TOOL_DEFINITIONS if row['function']['name'] == name)
                    result = {'error': exc.code, 'message': '이 함수는 실행하지 않았습니다. 허용 인자만 사용하고, 인자가 없는 함수에는 {}를 보내세요.',
                              'allowed_argument_schema': parameters}
                    workspace.events.append({'tool': name, 'status': 'invalid_arguments'})
                messages.append({'role': 'tool', 'tool_name': name, 'content': compact_json(result)})

        missing_required = workspace.missing_required_reads()
        if missing_required:
            raise LLMProviderError('LOCAL_REQUIRED_EVIDENCE_MISSING',
                                   '필수 비교·ML·사례·기존 초안 조회가 완료되지 않아 결과를 채택하지 않습니다: '
                                   + ', '.join(missing_required[:6]))
        read_case_ids = workspace.read_case_source_ids()
        feedback = request.input_payload.get('quality_review_feedback') or {}
        if feedback.get('issues'):
            messages.append({'role': 'user', 'content':
                             '이번 요청은 기존 결과의 보완이다. 아래 오류 목록의 필드를 실제로 수정하라. '
                             '이전 선택안은 승인된 정답이 아니다. 수정할 근거가 없으면 한계를 명시하고, '
                             '잘못된 원문을 그대로 복사하여 ready로 제출하지 마라. '
                             '연관된 strategy_brief와 후보를 일치시켜라.\n'
                             + evidence_json(feedback)})
        messages.append({'role': 'user', 'content':
                         '도구 단계가 끝났다. 확보한 근거만 사용해 지정 Schema의 최종 JSON을 작성하라. '
                         '추가 검색을 했다고 주장하지 말고, 읽지 못한 근거로 확정 판단하지 마라. '
                         '원문을 읽어 최종 인용 가능한 공식 사례 source_id는 ' + compact_json(read_case_ids) +
                         ' 이다. 이 목록 밖의 사례 ID는 최종 JSON에 넣지 마라.'})
        validator = Draft202012Validator(request.schema)
        schema_repairs = 0
        citation_repairs = 0
        incomplete_repairs = 0
        phase = 'final_json'
        # 최초 작성 뒤 출력 미완료 재생성·Schema 교정·미조회 사례 원문 보강을 각각
        # 1회만 허용합니다. 여러 교정이 연달아 필요한 경우에도 무한 재시도하지 않습니다.
        for _attempt in range(5):
            provider._check_context(messages, request.schema, request.max_output_tokens, measured_prefix)
            pending_phase = phase
            try:
                content, current_usage = await provider._call(
                    model=model, messages=messages, schema=request.schema, max_output_tokens=request.max_output_tokens,
                )
            except LLMProviderError as exc:
                if exc.code != 'OLLAMA_INCOMPLETE_RESPONSE' or incomplete_repairs >= 1:
                    raise
                # 잘린 JSON을 이어 붙이거나 채택하지 않습니다. 동일한 원문·Schema·출력
                # 상한으로 한 번만 처음부터 다시 받아 반복·장문 출력의 일시 오류를 복구합니다.
                for key, value in exc.usage.items():
                    usage[key] = usage.get(key, 0) + value
                attempts.append({
                    'phase': phase, 'status': 'retrying_after_output_limit',
                    'error_code': exc.code, 'usage_reported': bool(exc.usage), 'usage': dict(exc.usage),
                })
                if exc.usage.get('input_tokens', 0) > 0:
                    measured_prefix = (deepcopy(messages), exc.usage['input_tokens'])
                messages.append({'role': 'user', 'content':
                                 '직전 결과는 출력 한도 안에 끝나지 않아 폐기했다. 중복 설명을 줄이되 '
                                 '필수 필드·수치·기간·산식·출처를 생략하지 말고 지정 Schema의 완전한 JSON 객체를 처음부터 다시 작성하라.'})
                incomplete_repairs += 1
                phase = 'incomplete_retry'
                pending_phase = None
                continue
            account(current_usage, phase)
            pending_phase = None
            if current_usage.get('input_tokens', 0) > 0:
                measured_prefix = (deepcopy(messages), current_usage['input_tokens'])
            try:
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError('object required')
                validator.validate(parsed)
            except (ValueError, ValidationError) as exc:
                if schema_repairs >= 1:
                    raise LLMProviderError('OLLAMA_SCHEMA_VALIDATION_FAILED', '로컬 결과가 JSON 계약을 충족하지 않습니다.') from exc
                messages.extend([
                    {'role': 'assistant', 'content': content},
                    {'role': 'user', 'content': '근거를 바꾸지 말고 지정 Schema에 맞는 JSON 객체 하나로 교정하라.'},
                ])
                schema_repairs += 1
                phase = 'json_repair'
                continue

            unread_case_ids = workspace.unread_cited_case_ids(parsed)
            if unread_case_ids:
                if citation_repairs >= 1:
                    workspace.verify_citations(parsed)
                added_evidence: list[dict[str, Any]] = []
                for source_id in unread_case_ids:
                    result = workspace.execute('read_collected_source', {'source_id': source_id})
                    added_evidence.append({'tool': 'read_collected_source', 'result': result})
                    if 'error' in result:
                        # 원문 전체를 안전하게 전달할 수 없는 사례는 기존 정책대로 채택하지 않습니다.
                        workspace.verify_citations(parsed)
                messages.extend([
                    {'role': 'assistant', 'content': content},
                    {'role': 'user', 'content':
                     '최종 JSON에서 인용한 추가 공식 사례 원문을 서버가 확인했다:\n' +
                     compact_json(added_evidence) +
                     '\n원문의 수치·기간·한계를 바꾸지 말고 지정 Schema로 최종 JSON을 한 번 다시 작성하라. '
                     '현재 원문을 읽은 공식 사례 source_id만 인용하고, 다른 사례 ID가 필요하면 삭제하라.'},
                ])
                citation_repairs += 1
                phase = 'citation_repair'
                continue
            workspace.verify_citations(parsed)
            return LLMResult(
                payload=parsed, provider=provider.name, model=model,
                duration_ms=round((perf_counter() - started) * 1000), usage=usage, attempts=attempts,
                tool_trace=workspace.events,
                input_preparation={'mode': 'request_scoped_evidence_tools',
                                   'original_bytes': len(compact_json(request.input_payload).encode('utf-8')),
                                   'overview_bytes': len(compact_json(overview).encode('utf-8')),
                                   'sources_available': len(workspace.sources),
                                   'sources_read': len(workspace.read_source_ids)},
            )
        raise LLMProviderError('OLLAMA_SCHEMA_VALIDATION_FAILED', '제한된 교정 횟수 안에 안전한 로컬 JSON 결과를 만들지 못했습니다.')
    except LLMProviderError as exc:
        # 폴백으로 넘어가도 앞선 로컬 모델 호출·사용량을 지우지 않습니다. 본문/사고 과정은 기록하지 않습니다.
        if pending_phase:
            attempts.append({'phase': pending_phase, 'status': 'failed', 'error_code': exc.code,
                             'usage_reported': bool(exc.usage), 'usage': dict(exc.usage)})
        for key, value in exc.usage.items():
            usage[key] = usage.get(key, 0) + value
        exc.usage = usage
        exc.attempts = attempts + exc.attempts
        exc.tool_trace = workspace.events
        raise
    raise LLMProviderError('OLLAMA_OUTPUT_MISSING', '로컬 기획 결과가 없습니다.')
