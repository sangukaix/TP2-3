"""One real local generation; no job/report persistence or paid provider calls."""
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).parent
from ai_server.app import main
from ai_server.app.agents import report_orchestrator as orchestration
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.planning_brief import PlanningBrief, resolve_new_planning_brief
from ai_server.app.generation_progress import track_progress

def emit(event, **data):
    print(json.dumps({'event': event, **data}, ensure_ascii=False), flush=True)

original_router = orchestration.LLMRouter
def diagnostic_router(**kwargs):
    router = original_router(**kwargs)
    router.config['mode'] = 'student_budget'
    async def forbid_paid(*args, **kwargs):
        emit('paid_call_blocked')
        raise LLMProviderError('DIAGNOSTIC_PAID_CALL_BLOCKED', 'Local-only diagnostic')
    router.providers['openai'].generate = forbid_paid
    for name in ('qwen', 'gemma'):
        original = router.providers[name].generate
        async def observed(request, _original=original, _name=name):
            started = perf_counter()
            emit('local_start', provider=_name, task=request.task)
            result = await _original(request)
            emit('local_complete', provider=_name, task=request.task, seconds=round(perf_counter()-started, 1))
            return result
        router.providers[name].generate = observed
    return router

def forbid_write(*args, **kwargs):
    raise RuntimeError('Report/job persistence forbidden in diagnostic')

async def run():
    report = json.loads((ROOT/'storage/previews/cheorwon_audit/cheorwon.json').read_text(encoding='utf-8'))
    snapshot = main.build_region_snapshot(report['region_name'])
    code = str(report['planning_brief']['region_code'])
    brief = resolve_new_planning_brief(PlanningBrief(region_code=code, input_profile='guided_v2'))
    emit('start', region=report['region_name'], code=code, brief=brief.model_dump(mode='json'))
    with patch.object(orchestration, 'LLMRouter', diagnostic_router), track_progress(lambda step, message: emit('progress', step=step, message=message)):
        result = await main.generate_orchestrated_report(code, main.ReportRequest(region_name=report['region_name'], planning_brief=brief), snapshot=snapshot)
    (OUT/'report.json').write_text(json.dumps(result.model_dump(mode='json'), ensure_ascii=False, indent=2), encoding='utf-8')
    emit('completed', output='report.json', approved=result.quality_review)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    from contextlib import ExitStack
    from ai_server.app import strategy_store
    with ExitStack() as stack:
        for name in ('save_strategy_job', 'update_strategy_job_state', 'save_strategy_report', 'save_strategy_measurement_baseline', 'save_strategy_measurement_followup'):
            stack.enter_context(patch.object(strategy_store, name, forbid_write))
            if hasattr(main, name):
                stack.enter_context(patch.object(main, name, forbid_write))
        try:
            asyncio.run(run())
        except Exception as exc:
            error = {'type': type(exc).__name__, 'code': getattr(exc, 'code', None), 'detail': str(getattr(exc, 'detail', str(exc)))}
            (OUT/'failure.json').write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding='utf-8')
            emit('failed', **error)
            raise
