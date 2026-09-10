"""One-call Gemma handoff diagnostic for a composed pilot; no Router/report writes."""
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
    'strategy_title': {'type': 'string', 'maxLength': 100},
    'case_comparison': {'type': 'string', 'maxLength': 900},
    'wonju_development_path': {'type': 'string', 'maxLength': 900},
    'execution_steps': {'type': 'array', 'minItems': 4, 'maxItems': 4,
                        'items': obj({'phase': STRING, 'action': STRING, 'deliverable': STRING})},
    'temporary_budget_note': {'type': 'string', 'maxLength': 500},
    'measurement_note': {'type': 'string', 'maxLength': 700},
    'source_ids': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': STRING},
    'limitations': {'type': 'array', 'minItems': 2, 'maxItems': 5, 'items': STRING},
})
INSTRUCTION = '''입력의 검수 사례 비교와 원주 시범 계약으로 공무원 검토용 본문 요약을 쓴다.
타지역 사례의 운영 장치가 무엇이고 원주 시범에 어떻게 적용되는지 구체적으로 연결한다.
입력의 장소·기관·성과를 새로 만들지 않는다. 타지역 결과를 원주 예상 성과로 복사하지 않는다.
시범 계약의 수량·예산·측정 목표는 서버가 별도 표시하므로 다시 계산하거나 변경하지 않는다.
temporary_budget_note에는 임시 추정 총액과 공식 견적이 아니라는 점만 설명한다.
measurement_note에는 이용완료100건이 관리 목표이고 지역 전체 방문·소비 증가 보장이 아님을 설명한다.
실행 단계는 사례 검토/운영 설계→모집·예약→10일 운영·확인→취소·중복 제거·평가 순서다.
확정 사업이나 승인 완료로 표현하지 않는다. 지정 JSON만 반환한다.'''


def build_request(composed, frozen, model):
    if not composed.get('deterministic_contract_applied') or composed.get('report_approved') is not False:
        raise ValueError('Requires an unapproved deterministic composed pilot')
    answer = composed['answer']
    selected = set(answer['compared_case_ids'])
    cards = [case for case in frozen['evidence_pack'].get('benchmark_cases', [])
             if str(case.get('source_id')) in selected]
    if len(cards) != 2:
        raise ValueError('Selected case cards are missing')
    payload = {'case_cards': cards, 'pilot_narrative': {
        key: answer[key] for key in ('title', 'case_comparison', 'wonju_pilot', 'operating_flow',
                                     'why_this_can_develop_wonju_tourism', 'limits')},
               'server_owned_contract': {'budget': answer['budget'],
                                         'development_potential': answer['development_potential']}}
    return {'model': model, 'messages': [{'role': 'system', 'content': INSTRUCTION},
                                        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'schema': SCHEMA, 'max_output_tokens': 3500}


async def run(frozen_path, composed_path, execute=False):
    root = Path(__file__).resolve().parents[3]
    if Path.cwd().resolve() != root:
        raise ValueError('Run from TP2-3 root')
    frozen_path, composed_path = frozen_path.resolve(), composed_path.resolve()
    if not frozen_path.is_relative_to(root) or not composed_path.is_relative_to(root):
        raise ValueError('Inputs must stay in TP2-3')
    frozen = json.loads(frozen_path.read_text(encoding='utf-8'))
    composed = json.loads(composed_path.read_text(encoding='utf-8'))
    env = load_project_env(root)
    model = str(env.get('OLLAMA_GEMMA_MODEL') or 'gemma4:26b')
    request = build_request(composed, frozen, model)
    provider = OllamaProvider(base_url=env.get('LOCAL_LLM_BASE_URL', ''), default_model=model,
                             timeout_seconds=float(env.get('LOCAL_LLM_TIMEOUT_SECONDS') or 1800),
                             context_length=int(env.get('LOCAL_LLM_CONTEXT_LENGTH') or 40960))
    provider._check_context(request['messages'], request['schema'], request['max_output_tokens'])
    output = root / 'storage' / f'candidate_pilot_planner_{uuid4().hex}.json'
    record = {'status': 'prepared', 'report_approved': False, 'request': request,
              'request_sha256': sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
              'source_composed_artifact': composed_path.relative_to(root).as_posix(),
              'server_owned_contract': {'budget': composed['answer']['budget'],
                                        'development_potential': composed['answer']['development_potential']}}
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
        selected = set(composed['answer']['compared_case_ids'])
        record.update(answer=answer, status='completed',
                      source_ids_valid=set(answer['source_ids']) == selected,
                      contract_preserved=True)
    except LLMProviderError as exc:
        record.update(status='failed', error_code=exc.code, usage=exc.usage)
    except (ValueError, ValidationError) as exc:
        record.update(status='failed', error_code=type(exc).__name__)
    finally:
        record['duration_ms'] = round((perf_counter() - started) * 1000)
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: record.get(key) for key in
                      ('status', 'duration_ms', 'source_ids_valid', 'contract_preserved')}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen', type=Path)
    parser.add_argument('composed', type=Path)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    asyncio.run(run(args.frozen, args.composed, args.run))
