"""Agent별 Provider 선택·능력 잠금·로컬 실패 폴백을 담당합니다."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any

from ..local_web_search import OfficialWebSearchClient
from .errors import LLMProviderError
from .models import LLMRequest, LLMResult
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .trace_store import record_trace


# OpenAI Web Search가 필요한 단계입니다. 로컬 모델은 이 작업을 직접 호출하지 않으며,
# 학생 절약 모드에서는 별도의 무료 공식 검색 API 도구가 Qwen의 질문만 제한적으로 실행합니다.
WEB_SEARCH_TASKS = {'evidence', 'case_study', 'chat_research'}
REVIEW_TASKS = {'reviewer', 'final_reviewer'}
MODES = {'openai_only', 'hybrid', 'local_only', 'local_first', 'student_budget'}
LOCAL_FIRST_CLOUD_TASKS = {'evidence', 'case_study', 'final_reviewer', 'chat_research'}
STUDENT_BUDGET_CLOUD_TASKS = {'final_reviewer'}
DEFAULT_ROUTES = {
    'evidence': {'provider': 'openai', 'model_env': 'OPENAI_RESEARCH_MODEL', 'fallback': 'none'},
    'case_study': {'provider': 'openai', 'model_env': 'OPENAI_CASE_RESEARCH_MODEL', 'fallback': 'none'},
    # 검색 자체가 아닌 질문 설계 단계입니다. 서버가 이 JSON 질문을 검증한 뒤 허용 도메인만 조회합니다.
    'local_web_query_planner': {'provider': 'qwen', 'model_env': 'OLLAMA_QWEN_MODEL', 'fallback': 'none'},
    'transferability': {'provider': 'qwen', 'model_env': 'OLLAMA_QWEN_MODEL', 'fallback': 'openai'},
    'planner': {'provider': 'gemma', 'model_env': 'OLLAMA_GEMMA_MODEL', 'fallback': 'openai'},
    'planner_revision': {'provider': 'gemma', 'model_env': 'OLLAMA_GEMMA_MODEL', 'fallback': 'openai'},
    'reviewer': {'provider': 'openai', 'model_env': 'OPENAI_REVIEW_MODEL', 'fallback': 'none'},
    'final_reviewer': {'provider': 'openai', 'model_env': 'OPENAI_REVIEW_MODEL', 'fallback': 'none'},
    'chat_explain': {'provider': 'qwen', 'model_env': 'OLLAMA_QWEN_MODEL', 'fallback': 'openai'},
    'chat_research': {'provider': 'openai', 'model_env': 'OPENAI_CHAT_MODEL', 'fallback': 'none'},
    'chat_revise': {'provider': 'gemma', 'model_env': 'OLLAMA_GEMMA_MODEL', 'fallback': 'openai'},
}
ROUTE_ENV_PREFIX = {
    'evidence': 'LLM_EVIDENCE', 'case_study': 'LLM_CASE_STUDY', 'local_web_query_planner': 'LLM_LOCAL_WEB_QUERY_PLANNER', 'transferability': 'LLM_TRANSFER',
    'planner': 'LLM_PLANNER', 'planner_revision': 'LLM_PLANNER_REVISION', 'reviewer': 'LLM_REVIEWER',
    'final_reviewer': 'LLM_FINAL_REVIEWER', 'chat_explain': 'LLM_CHAT_EXPLAIN',
    'chat_research': 'LLM_CHAT_RESEARCH', 'chat_revise': 'LLM_CHAT_REVISE',
}


class LLMRouter:
    """라우팅 설정을 한 곳에 두어 Agent 내부의 Provider 분기를 제거합니다."""

    def __init__(self, *, project_root: Path, env_values: dict[str, Any]) -> None:
        self.project_root = project_root
        self.env_values = env_values
        self.config_path = project_root / 'storage' / 'llm_runtime_config.json'
        self.config = self._load_config()
        openai_model = str(env_values.get('OPENAI_MODEL') or 'gpt-5.6').strip()
        self.providers = {
            'openai': OpenAIProvider(api_key=str(env_values.get('OPENAI_API_KEY') or ''), default_model=openai_model),
            'qwen': OllamaProvider(
                base_url=str(env_values.get('LOCAL_LLM_BASE_URL') or ''),
                default_model=str(env_values.get('OLLAMA_QWEN_MODEL') or ''),
                # 26B 모델의 첫 로드와 구조화 초안 생성은 3분을 넘길 수 있습니다. 환경변수로
                # 더 짧게 정한 팀 설정은 존중하되, 미설정 기본값은 실제 완료를 기다립니다.
                timeout_seconds=float(env_values.get('LOCAL_LLM_TIMEOUT_SECONDS') or 420),
                # 현재 팀의 Qwen3:14b가 제공하는 40,960 토큰 문맥을 기본으로 씁니다.
                # 이전 32,768 기본값은 여러 공식 사례·ML·비교표를 함께 검토하는
                # 적용성 단계에서 실제 모델 한도보다 먼저 안전 차단되는 문제가 있었습니다.
                context_length=int(env_values.get('LOCAL_LLM_CONTEXT_LENGTH') or 40960),
            ),
            'gemma': OllamaProvider(
                base_url=str(env_values.get('LOCAL_LLM_BASE_URL') or ''),
                default_model=str(env_values.get('OLLAMA_GEMMA_MODEL') or ''),
                timeout_seconds=float(env_values.get('LOCAL_LLM_TIMEOUT_SECONDS') or 420),
                # Qwen과 같은 공통 문맥 예산을 적용해 Agent 단계별 동작을 예측 가능하게
                # 유지합니다. Gemma는 더 긴 문맥을 지원하지만 요청마다 임의로 달라지지 않습니다.
                context_length=int(env_values.get('LOCAL_LLM_CONTEXT_LENGTH') or 40960),
            ),
        }
        self.trace: list[dict[str, Any]] = []
        self.cloud_calls = 0

    @property
    def local_first(self) -> bool:
        """Qwen·Gemma 선행 실행과 유료 폴백 차단을 공유하는 두 모드입니다."""
        return self.config['mode'] in {'local_first', 'student_budget'}

    @property
    def student_budget(self) -> bool:
        """저장된 근거만 재사용하고 OpenAI 독립 최종 검수 1회만 허용하는 학생용 모드입니다."""
        return self.config['mode'] == 'student_budget'

    @property
    def max_cloud_calls_per_generation(self) -> int | None:
        """한 기획 생성에서 허용하는 OpenAI Responses 요청 수입니다."""
        if self.student_budget:
            return 1
        return 3 if self.local_first else None

    async def preflight_local_models(self) -> None:
        """로컬 우선 기획은 두 모델 연결을 먼저 확인해, 연결 실패 전에 유료 조사를 시작하지 않습니다."""
        if not self.local_first:
            return
        import asyncio
        states = await asyncio.gather(*(self.providers[name].health() for name in ('qwen', 'gemma')))
        available = dict(zip(('qwen', 'gemma'), states))
        routes = self.effective_routes()
        model_missing = any(routes[task]['model'] not in available[routes[task]['provider']].models
                            for task in ('transferability', 'planner', 'reviewer'))
        if any(state.status != 'active' for state in states) or model_missing:
            raise LLMProviderError('LOCAL_FIRST_MODELS_UNAVAILABLE',
                                   '개인 노트북의 Qwen·Gemma 연결을 먼저 확인해주세요. OpenAI 유료 조사는 시작하지 않았습니다.', status_code=503)

    def _default_config(self) -> dict[str, Any]:
        mode = str(self.env_values.get('LLM_MODE') or 'hybrid').lower()
        routes = deepcopy(DEFAULT_ROUTES)
        # .env는 최초 권장값을 정하고, 관리자 변경값은 별도 runtime 설정 파일에만 저장합니다.
        for task, prefix in ROUTE_ENV_PREFIX.items():
            provider = str(self.env_values.get(f'{prefix}_PROVIDER') or '').lower()
            model = str(self.env_values.get(f'{prefix}_MODEL') or '').strip()
            if provider == 'ollama':
                provider = model.lower() if model.lower() in {'qwen', 'gemma'} else routes[task]['provider']
            if provider in {'openai', 'qwen', 'gemma'}:
                routes[task]['provider'] = provider
            if model and model.lower() not in {'qwen', 'gemma'}:
                routes[task]['model'] = model
        return {'mode': mode if mode in MODES else 'hybrid', 'routes': routes}

    def _load_config(self) -> dict[str, Any]:
        defaults = self._default_config()
        try:
            saved = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return defaults
        if not isinstance(saved, dict):
            return defaults
        routes = deepcopy(defaults['routes'])
        for task, value in (saved.get('routes') or {}).items():
            if task in routes and isinstance(value, dict):
                routes[task].update({key: value[key] for key in ('provider', 'model', 'fallback') if key in value})
        mode = saved.get('mode') if saved.get('mode') in MODES else defaults['mode']
        return {'mode': mode, 'routes': routes}

    def public_config(self) -> dict[str, Any]:
        return deepcopy(self.config)

    def effective_routes(self) -> dict[str, Any]:
        """저장한 희망 설정과 실제 비용·능력 잠금이 적용된 실행 경로를 구분합니다."""
        routes = {}
        for task in DEFAULT_ROUTES:
            # 학생 절약 모드의 조사 단계는 OpenAI Web Search가 아닌 MySQL·공식 Open API·검수 RAG와,
            # 설정된 경우 Qwen 질문 → 무료 API → 공식 도메인 요약의 제한 경로를 사용합니다.
            if self.student_budget and task in WEB_SEARCH_TASKS:
                routes[task] = {
                    'provider': 'local_sources', 'model': None, 'fallback': 'none',
                    'locked_reason': '학생 절약 모드: OpenAI 웹 조사는 실행하지 않음. 무료 검색 API 키가 있으면 Qwen 질문으로 공식 도메인 요약 후보만 추가',
                }
                continue
            request = LLMRequest(task=task, instructions='', input_payload={}, schema_name='', schema={})
            try:
                route = self._route(request)
                routes[task] = {**route, 'model': self._model_for(route['provider'], route, request)}
            except LLMProviderError as exc:
                routes[task] = {'provider': 'unavailable', 'fallback': 'none', 'locked_reason': exc.message}
        return routes

    def update_config(self, value: dict[str, Any]) -> dict[str, Any]:
        """관리자가 검증된 라우팅만 저장합니다. 키·주소는 브라우저에서 수정하지 않습니다."""
        next_config = self._default_config()
        mode = value.get('mode')
        if mode in MODES:
            next_config['mode'] = mode
        for task, incoming in (value.get('routes') or {}).items():
            if task not in next_config['routes'] or not isinstance(incoming, dict):
                continue
            provider = incoming.get('provider')
            fallback = incoming.get('fallback')
            model = incoming.get('model')
            if task not in WEB_SEARCH_TASKS and provider in self.providers:
                next_config['routes'][task]['provider'] = provider
            if fallback in {'none', 'openai'}:
                next_config['routes'][task]['fallback'] = fallback
            if isinstance(model, str) and model.strip():
                next_config['routes'][task]['model'] = model.strip()
        self.config = next_config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(next_config, ensure_ascii=False, indent=2), encoding='utf-8')
        return self.public_config()

    def reset_config(self) -> dict[str, Any]:
        return self.update_config(self._default_config())

    def _route(self, request: LLMRequest) -> dict[str, Any]:
        route = deepcopy(self.config['routes'].get(request.task) or DEFAULT_ROUTES['planner'])
        configured_provider = route['provider']
        if request.requires_web_search or request.task in WEB_SEARCH_TASKS:
            if self.student_budget:
                raise LLMProviderError(
                    'STUDENT_BUDGET_WEB_SEARCH_DISABLED',
                    '학생 절약 모드에서는 실시간 OpenAI Web Search를 자동 실행하지 않습니다. 무료 공식 검색 API는 Evidence Agent의 제한 도구 경로에서만 실행됩니다.',
                    status_code=503,
                )
            if self.config['mode'] == 'local_only':
                raise LLMProviderError('LOCAL_MODE_WEB_SEARCH_UNAVAILABLE', 'local_only 모드에서는 Web Search가 필요한 작업을 실행할 수 없습니다.', status_code=503)
            route.update({'provider': 'openai', 'fallback': 'none', 'locked_reason': 'Web Search 필수 작업'})
        elif self.config['mode'] == 'openai_only' or (request.task in REVIEW_TASKS and self.config['mode'] == 'hybrid'):
            route['provider'] = 'openai'
            route['fallback'] = 'none'
        elif self.config['mode'] == 'local_only':
            # Web Search가 아닌 Reviewer 같은 생성·검수 작업은 실험 모드에서 Qwen으로 실행합니다.
            if route['provider'] == 'openai':
                route['provider'] = 'qwen'
            route['fallback'] = 'none'
            route['local_only_reason'] = 'local_only 실험 모드'
        elif self.local_first:
            # 저장된 과거 Hybrid 폴백 설정도 이 모드에서는 유료 대체를 허용하지 않습니다.
            provider = 'openai' if request.task == 'final_reviewer' else (
                'gemma' if request.task in {'planner', 'planner_revision', 'chat_revise'} else 'qwen')
            route.update({'provider': provider, 'fallback': 'none', 'locked_reason': '로컬 우선 비용 정책'})
        if route['provider'] != configured_provider:
            # 강제 Provider 전환 때 다른 회사/로컬 모델명을 그대로 보내지 않습니다.
            route.pop('model', None)
        return route

    def _model_for(self, provider_name: str, route: dict[str, Any], request: LLMRequest) -> str | None:
        if request.model:
            return request.model
        # 로컬 route의 사용자 모델명(qwen3:14b 등)은 OpenAI 폴백에 전달하지 않습니다.
        if route.get('model') and provider_name == route.get('provider'):
            return str(route['model'])
        env_name = str(route.get('model_env') or '')
        if provider_name == 'openai':
            selected = self.env_values.get(env_name) if env_name.startswith('OPENAI_') else None
            return str(selected or self.env_values.get('OPENAI_REPORT_MODEL') or self.env_values.get('OPENAI_MODEL') or 'gpt-5.6')
        local_env = 'OLLAMA_QWEN_MODEL' if provider_name == 'qwen' else 'OLLAMA_GEMMA_MODEL'
        return str(self.env_values.get(local_env) or self.providers[provider_name].default_model)

    async def generate(self, request: LLMRequest) -> dict[str, Any]:
        """Agent가 사용하던 dict 반환을 유지하면서 trace에 Provider 결과를 남깁니다."""
        route = self._route(request)
        provider_name = str(route['provider'])
        try:
            return await self._generate_tracked(request, route, provider_name, provider_name)
        except LLMProviderError as exc:
            # Web Search 실패는 로컬 모델로 숨기지 않습니다. 조사 실패를 호출자에게 그대로 알립니다.
            if provider_name in {'qwen', 'gemma'} and route.get('fallback') == 'openai' and not request.requires_web_search:
                fallback_request = LLMRequest(**{**request.__dict__, 'model': None})
                return await self._generate_tracked(
                    fallback_request, route, 'openai', provider_name, fallback_reason=exc.code,
                )
            raise

    async def _generate_tracked(self, request: LLMRequest, route: dict[str, Any],
                                provider_name: str, requested_provider: str, *, fallback_reason: str = '') -> dict[str, Any]:
        """최초 호출과 OpenAI 폴백 모두 실패·재시도 사용량을 남기는 동일한 경로로 실행합니다."""
        output_limit = request.max_output_tokens
        if provider_name in {'qwen', 'gemma'} and request.local_max_output_tokens is not None:
            output_limit = request.local_max_output_tokens
        provider_request = LLMRequest(**{**request.__dict__,
                                        'model': self._model_for(provider_name, route, request),
                                        'max_output_tokens': output_limit})
        paid_reason = ''
        if self.local_first and provider_name == 'openai':
            allowed_cloud_tasks = STUDENT_BUDGET_CLOUD_TASKS if self.student_budget else LOCAL_FIRST_CLOUD_TASKS
            cloud_limit = self.max_cloud_calls_per_generation or 0
            if request.task not in allowed_cloud_tasks or self.cloud_calls >= cloud_limit:
                event = {'agent': request.agent or request.task, 'stage': request.task, 'status': 'blocked',
                         'provider': 'openai', 'error_code': 'CLOUD_CALL_BUDGET_EXCEEDED', 'usage': {},
                         'paid_reason': f'허용 단계 또는 생성 1건당 최대 {cloud_limit}회 제한', 'provider_called': False}
                self.trace.append(event)
                record_trace(event)
                raise LLMProviderError('CLOUD_CALL_BUDGET_EXCEEDED', '유료 호출 제한에 도달했습니다. 자동 추가 결제 호출은 하지 않습니다.')
            self.cloud_calls += 1  # await 전에 예약하므로 병렬 조사도 상한을 넘지 않습니다.
            provider_request = replace(provider_request, retry_max_output_tokens=None)
            paid_reason = ('독립 최종 품질 검수 (학생 절약 모드)' if self.student_budget and request.task == 'final_reviewer'
                           else '독립 최종 품질 검수' if request.task == 'final_reviewer'
                           else '부족한 공식 근거의 웹 조사')
        started = perf_counter()
        try:
            result = await self.providers[provider_name].generate(provider_request)
        except LLMProviderError as exc:
            event = {
                'agent': request.agent or request.task, 'stage': request.task, 'status': 'failed',
                'provider': provider_name, 'requested_provider': requested_provider, 'model': provider_request.model,
                'duration_ms': round((perf_counter() - started) * 1000), 'usage': exc.usage,
                'fallback': bool(fallback_reason), 'fallback_reason': fallback_reason or exc.code,
                'error_code': exc.code, 'web_search_used': False, 'attempts': exc.attempts,
                'tool_trace': getattr(exc, 'tool_trace', []),
                'max_output_tokens': output_limit,
                'paid_reason': paid_reason,
                'retry_count': (sum(item.get('phase') == 'json_repair' for item in exc.attempts)
                                if provider_name in {'qwen', 'gemma'} else max(0, len(exc.attempts) - 1)),
            }
            self.trace.append(event)
            record_trace(event)
            raise
        event = {
            'agent': request.agent or request.task, 'stage': request.task, 'status': 'completed',
            'provider': provider_name, 'requested_provider': requested_provider,
            'model': result.model, 'duration_ms': round((perf_counter() - started) * 1000), 'usage': result.usage,
            'fallback': bool(fallback_reason), 'fallback_reason': fallback_reason,
            'web_search_used': result.web_search_used, 'attempts': result.attempts,
            'tool_trace': result.tool_trace, 'input_preparation': result.input_preparation,
            'max_output_tokens': output_limit,
            'paid_reason': paid_reason,
            'retry_count': (sum(item.get('phase') == 'json_repair' for item in result.attempts)
                            if provider_name in {'qwen', 'gemma'} else max(0, len(result.attempts) - 1)),
        }
        self.trace.append(event)
        record_trace(event)
        return result.payload

    def consume_trace(self) -> list[dict[str, Any]]:
        trace, self.trace = self.trace, []
        return trace

    async def status(self) -> dict[str, Any]:
        openai, qwen, gemma = await __import__('asyncio').gather(
            self.providers['openai'].health(), self.providers['qwen'].health(), self.providers['gemma'].health(),
        )
        # Qwen·Gemma는 같은 Ollama 서버를 사용하므로 health.provider 값만으로는
        # 관리자 화면에서 서로 구분할 수 없습니다. Router 역할(role)을 별도로 제공합니다.
        provider_rows = []
        for role, health in (('openai', openai), ('qwen', qwen), ('gemma', gemma)):
            row = health.as_dict()
            row['role'] = role
            row['backend'] = health.provider
            if role == 'qwen':
                # 실행 권한이 아니라 제한된 질문 설계 역할임을 관리자에게 구분해 보여 줍니다.
                row['capabilities'] = [*row['capabilities'], 'constrained_official_web_query_planning']
            provider_rows.append(row)
        domains = [item.strip().lower() for item in re.split(r'[,;\s]+', str(
            self.env_values.get('TOURISM_ALLOWED_RESEARCH_DOMAINS') or ''
        )) if item.strip()]
        local_web_search = OfficialWebSearchClient(
            env_values=self.env_values,
            allowed_domains=domains or ['go.kr', 'visitkorea.or.kr', 'data.go.kr'],
        ).provider_status()
        return {
            'mode': self.config['mode'], 'providers': provider_rows,
            'cost_policy': {
                'local_first': self.local_first,
                'student_budget': self.student_budget,
                'max_cloud_calls_per_generation': self.max_cloud_calls_per_generation,
                'automatic_paid_fallback': not self.local_first and self.config['mode'] != 'local_only',
                'automatic_web_research': not self.student_budget and self.config['mode'] != 'local_only',
                'free_official_web_search': local_web_search,
            },
            'routes': self.public_config()['routes'], 'effective_routes': self.effective_routes(),
            'capability_locks': {
                **({task: '학생 절약 모드: OpenAI Web Search는 실행하지 않음. 설정된 무료 API는 Qwen 검색 질문으로 공식 도메인 요약 후보만 수집'
                    for task in WEB_SEARCH_TASKS} if self.student_budget else
                   {task: 'Web Search 필수: OpenAI 고정' for task in WEB_SEARCH_TASKS}),
                **({task: '독립 품질 검수: Hybrid에서는 OpenAI 고정' for task in REVIEW_TASKS}
                   if self.config['mode'] == 'hybrid' else {}),
                **({task: ('학생 절약 모드: 로컬 통과본의 독립 최종 검수 1회만 OpenAI'
                            if task == 'final_reviewer' else '학생 절약 모드: Qwen·Gemma 실행 · 유료 대체 없음')
                    for task in DEFAULT_ROUTES if task not in WEB_SEARCH_TASKS} if self.student_budget else
                   {task: ('최종 검수만 OpenAI' if task == 'final_reviewer' else '로컬 우선 · 유료 대체 없음')
                    for task in DEFAULT_ROUTES if task not in WEB_SEARCH_TASKS} if self.local_first else {}),
            },
        }
