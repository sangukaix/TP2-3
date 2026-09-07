"""개인 Ollama의 함수 선택·근거 조회·JSON 응답을 합성 자료로 점검합니다.

실제 추론을 수행하므로 개인 GPU/CPU를 사용합니다. OpenAI Provider는 생성하지 않으며
유료 API·실제 기획 저장을 호출하지 않습니다. 기획 품질/인과효과 검증을 대신하지 않습니다.
실행: python -m ai_server.app.scripts.check_local_agent_smoke
"""

import asyncio
import json
from pathlib import Path

from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.models import LLMRequest
from ai_server.app.llm.ollama_provider import OllamaProvider
from ai_server.app.runtime_env import load_project_env


def synthetic_evidence() -> dict:
    """실제 지역 통계나 개인정보가 아닌, 방향/출처 확인용 테스트 자료만 전달합니다."""
    return {'evidence_pack': {
        'region_code': 'TEST', 'region_name': '테스트 지역 (실제 지자체 아님)', 'period': '2026-07',
        'snapshot': {
            'observations': [{'metric': 'test_visitors', 'value': 100, 'unit': '테스트 단위'}],
            'nationwide_comparison': {'available': True, 'period': '2026-07',
                'peer_regions': [{'region_name': '비교 테스트 지역', 'overnight_ratio_gap_pct_point': 1.0}]},
            'ml_analysis': {'status': 'available', 'source_id': 'test:ml',
                'horizon_policy': {'decision_windows': [{'start_month': '2026-09', 'end_month': '2026-11'}]},
                'forecasts': [{'month': '2026-09', 'visitors': 110, 'unit': '테스트 단위'},
                              {'month': '2026-10', 'visitors': 120, 'unit': '테스트 단위'},
                              {'month': '2026-11', 'visitors': 130, 'unit': '테스트 단위'}],
                'cautions': ['합성 테스트 자료다. 자연추세는 정책 효과가 아니다.']},
        },
        'benchmark_cases': [{'source_id': 'test:case', 'source_title': '테스트용 사례',
            'case_region': '테스트 지역', 'operating_model': '이용 완료 기록을 확인하는 테스트',
            'observed_result': '성과 수치 미확인', 'source_url': 'https://example.invalid/test'}],
        'sources': [{'source_id': 'test:case', 'title': '실제 사례 아님', 'source_type': 'benchmark_case'}],
    }}


SMOKE_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'description': '합성 근거 조회 검사다. 사업 제안 대신 요청한 값만 필드로 반환한다.',
    'properties': {
        'observed_value': {'type': 'number', 'description': 'test_visitors의 관측값'},
        'forecast_month': {'type': 'string', 'description': '월별 표에서 가장 마지막으로 제공된 예측월'},
        'forecast_value': {'type': 'number', 'description': '그 마지막 예측월 visitors 값'},
        'forecast_unit': {'type': 'string', 'description': '해당 예측표에 명시된 단위 그대로'},
        'comparison_direction': {'type': 'string', 'enum': ['higher', 'equal', 'lower'],
                                 'description': '선택 지역 숙박비율이 비교 지역보다 높은지 같은지 낮은지'},
        'policy_effect_proven': {'type': 'boolean', 'description': '제공된 ML 전망이 사업 인과효과를 증명하는가'},
        'case_source_id': {'type': 'string', 'description': '실제로 원문을 읽은 사례 출처 ID'},
    },
    'required': ['observed_value', 'forecast_month', 'forecast_value', 'forecast_unit',
                 'comparison_direction', 'policy_effect_proven', 'case_source_id']}


def semantic_errors(payload: dict) -> list[str]:
    expected = {'observed_value': 100, 'forecast_month': '2026-11', 'forecast_value': 130,
                'forecast_unit': '테스트 단위', 'comparison_direction': 'higher',
                'policy_effect_proven': False, 'case_source_id': 'test:case'}
    return [key for key, value in expected.items() if payload.get(key) != value]


async def main() -> int:
    project_root = Path(__file__).resolve().parents[3]
    env = load_project_env(project_root)
    failed = False
    for role, task, model_key in [('qwen', 'transferability', 'OLLAMA_QWEN_MODEL'), ('gemma', 'planner', 'OLLAMA_GEMMA_MODEL')]:
        model = str(env.get(model_key) or '')
        provider = OllamaProvider(base_url=str(env.get('LOCAL_LLM_BASE_URL') or ''), default_model=model,
            timeout_seconds=180, context_length=int(env.get('LOCAL_LLM_CONTEXT_LENGTH') or 32768))
        native_chat = provider._chat
        async def inspect_synthetic_calls(**kwargs):
            message, usage = await native_chat(**kwargs)
            # 합성 자료 점검에서만 호출 이름/인자 형식을 출력합니다. 실제 기획 trace에는 인자를 남기지 않습니다.
            print(json.dumps({'synthetic_tool_calls': message.get('tool_calls', [])}, ensure_ascii=False), flush=True)
            return message, usage
        provider._chat = inspect_synthetic_calls
        request = LLMRequest(task=task, instructions='합성 자료 도구 점검', input_payload=synthetic_evidence(),
            schema_name='local_agent_smoke', schema=SMOKE_SCHEMA, max_output_tokens=1600, local_evidence_tools=True)
        print(json.dumps({'role': role, 'model': model, 'status': 'starting'}, ensure_ascii=False), flush=True)
        try:
            result = await provider.generate(request)
        except LLMProviderError as exc:
            failed = True
            row = {'role': role, 'model': model, 'status': 'failed', 'code': exc.code,
                   'tool_trace': getattr(exc, 'tool_trace', []), 'usage': exc.usage, 'attempts': exc.attempts}
        else:
            errors = semantic_errors(result.payload)
            failed = failed or bool(errors)
            row = {'role': role, 'model': result.model, 'status': 'semantic_failed' if errors else 'completed', 'payload': result.payload,
                   'tool_trace': result.tool_trace, 'usage': result.usage, 'duration_ms': result.duration_ms,
                   'semantic_errors': errors, 'validation_scope': 'synthetic_facts_tools_json_not_full_proposal_quality'}
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
