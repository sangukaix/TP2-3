"""One-call Qwen review of the isolated Gemma pilot handoff; no production writes."""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError
from ..runtime_env import load_project_env
from ..llm.ollama_provider import OllamaProvider
from ..llm.errors import LLMProviderError


def obj(properties):
    return {'type': 'object', 'additionalProperties': False,
            'properties': properties, 'required': list(properties)}


STRING = {'type': 'string'}
SCHEMA = obj({
    'approved': {'type': 'boolean'},
    'strengths': {'type': 'array', 'maxItems': 5, 'items': STRING},
    'blocking_issues': {'type': 'array', 'maxItems': 8,
                        'items': obj({'field': STRING, 'issue': STRING, 'required_correction': STRING})},
    'contract_checks': obj({'case_ids_preserved': {'type': 'boolean'},
                            'temporary_budget_preserved': {'type': 'boolean'},
                            'pilot_target_preserved': {'type': 'boolean'},
                            'no_unsupported_effect_claim': {'type': 'boolean'}}),
    'next_action': STRING,
})
INSTRUCTION = '''타지역 사례 기반 원주 시범 기획의 독립 검토자다.
서버 계약과 Gemma 본문을 비교한다. 타지역 성과를 원주 효과로 복사하거나 확인되지 않은 장소·기관·협약·시스템을 확정하면 승인하지 않는다.
예산은 평가용 임시 추정이어도 허용하며 정확한 공식 견적을 요구하지 않는다. 다만 총액·가정 상태가 사라지거나 확정 예산으로 바뀌면 지적한다.
발전 가능성은 유효 이용완료100건과 결제액 원장 등 시범 관리 목표로 평가한다. 지역 전체 방문·소비 증가 보장을 요구하지 않는다.
실제 예약·결제 시스템 구축이 확인되지 않았으므로 원장/간단 접수 절차 제안과 시스템 구축 완료를 구분한다.
형식 통과보다 실제 문장과 실행 가능성을 검토한다. blocking issue가 하나라도 있으면 approved=false다. 지정 JSON만 반환한다.'''


def deterministic_issues(planner):
    answer = planner['answer']
    text = json.dumps(answer, ensure_ascii=False)
    issues = []
    budget_note = str(answer.get('temporary_budget_note') or '')
    if not any(value in budget_note.replace(',', '') for value in ('17500000', '1750만원')):
        issues.append('temporary_budget_total_missing_from_text')
    if '실시간' in text:
        issues.append('unsupported_realtime_operation')
    if '시스템 구축' in text:
        issues.append('unsupported_system_build')
    if '100건' not in str(answer.get('measurement_note') or ''):
        issues.append('pilot_target_missing_from_text')
    contract_ids = set(planner['server_owned_contract'].get('development_potential', [])[0]
                       .get('data_record_fields', []))
    if not {'예약ID', '결제ID', '취소 상태', '중복 판정'}.issubset(contract_ids):
        issues.append('server_measurement_contract_incomplete')
    return issues


def build_request(planner, model):
    if planner.get('status') != 'completed' or not planner.get('contract_preserved'):
        raise ValueError('Requires completed planner artifact with preserved contract')
    payload = {'gemma_draft': planner['answer'], 'server_owned_contract': planner['server_owned_contract']}
    return {'model': model, 'messages': [{'role': 'system', 'content': INSTRUCTION},
                                        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'schema': SCHEMA, 'max_output_tokens': 2600}


async def run(path, execute=False, audit_reviewer=None):
    root = Path(__file__).resolve().parents[3]
    path = path.resolve()
    if Path.cwd().resolve() != root or not path.is_relative_to(root):
        raise ValueError('Run in TP2-3 with an in-project artifact')
    planner = json.loads(path.read_text(encoding='utf-8'))
    if audit_reviewer:
        audit_reviewer = audit_reviewer.resolve()
        if not audit_reviewer.is_relative_to(root):
            raise ValueError('Reviewer artifact must stay in TP2-3')
        reviewer = json.loads(audit_reviewer.read_text(encoding='utf-8'))
        issues = deterministic_issues(planner)
        output = root / 'storage' / f'candidate_pilot_final_audit_{uuid4().hex}.json'
        record = {'status': 'completed', 'llm_called': False,
                  'planner_artifact': path.relative_to(root).as_posix(),
                  'reviewer_artifact': audit_reviewer.relative_to(root).as_posix(),
                  'qwen_approved': bool(reviewer.get('report_approved')),
                  'deterministic_issues': issues,
                  'report_approved': bool(reviewer.get('report_approved') and not issues)}
        with output.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
        print(output.relative_to(root).as_posix(), flush=True)
        return
    env = load_project_env(root)
    model = str(env.get('OLLAMA_QWEN_MODEL') or 'qwen3:14b')
    request = build_request(planner, model)
    provider = OllamaProvider(base_url=env.get('LOCAL_LLM_BASE_URL', ''), default_model=model,
                             timeout_seconds=float(env.get('LOCAL_LLM_TIMEOUT_SECONDS') or 1800),
                             context_length=int(env.get('LOCAL_LLM_CONTEXT_LENGTH') or 40960))
    provider._check_context(request['messages'], request['schema'], request['max_output_tokens'])
    output = root / 'storage' / f'candidate_pilot_reviewer_{uuid4().hex}.json'
    record = {'status': 'prepared', 'report_approved': False, 'request': request,
              'request_sha256': sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
              'source_planner_artifact': path.relative_to(root).as_posix()}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(output.relative_to(root).as_posix(), flush=True)
    if not execute:
        return
    started = perf_counter()
    try:
        message, usage = await provider._chat(**request, think=False)
        record.update(content=str(message.get('content') or ''), usage=usage)
        answer = json.loads(record['content'])
        Draft202012Validator(SCHEMA).validate(answer)
        consistent = answer['approved'] is (len(answer['blocking_issues']) == 0)
        issues = deterministic_issues(planner)
        record.update(answer=answer, status='completed', approval_consistent=consistent,
                      deterministic_issues=issues,
                      report_approved=bool(answer['approved'] and consistent and not issues))
    except LLMProviderError as exc:
        record.update(status='failed', error_code=exc.code, usage=exc.usage)
    except (ValueError, ValidationError) as exc:
        record.update(status='failed', error_code=type(exc).__name__)
    finally:
        record['duration_ms'] = round((perf_counter() - started) * 1000)
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: record.get(key) for key in
                      ('status', 'duration_ms', 'report_approved', 'approval_consistent')}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('planner_artifact', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--audit-reviewer', type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.planner_artifact, args.run, args.audit_reviewer))
