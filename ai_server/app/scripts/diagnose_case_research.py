"""Read-only report diagnostic. Paid search requires an explicit CLI opt-in.

Default: capture current SQL/ML search inputs, no LLM. Opt-in: exactly one
OpenAI case-search request, followed by Qwen/Gemma/Qwen only. No report saves,
model training, SQL writes, automatic paid retry or final cloud review.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import urllib.request

from ai_server.app.runtime_env import load_project_env
from ai_server.app.case_research_plan import build_case_research_plan, comparison_coverage


async def run(report_id: str, allow_paid: bool = False, resume_case_path: Path | None = None):
    from ai_server.app.main import build_region_snapshot, REPORT_SCHEMA
    from ai_server.app.llm.router import LLMRouter
    from ai_server.app.agents.case_study_agent import CaseStudyAgent
    from ai_server.app.agents.transferability_agent import TransferabilityAgent
    from ai_server.app.agents.planner_agent import PlannerAgent
    from ai_server.app.agents.reviewer_agent import ReviewerAgent
    from ai_server.app.agents.planning_requirements import QUALITY_CONTRACT_VERSION, candidate_delivery_issues
    from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck
    from ai_server.ml.planning_evidence import build_planning_ml_evidence
    if not report_id.isalnum():
        raise ValueError('Invalid report ID')
    if allow_paid and resume_case_path:
        raise ValueError('Saved-case replay cannot enable paid research')
    root = Path(__file__).resolve().parents[3]
    env = load_project_env(root)
    with urllib.request.urlopen(f'http://127.0.0.1:8112/ai/v1/strategy-reports/{report_id}', timeout=20) as response:
        report = json.load(response)
    brief = report.get('planning_brief') or {}
    code = brief['region_code']
    snapshot = build_region_snapshot(report['region_name'])
    snapshot['ml_analysis'] = build_planning_ml_evidence(code, report['region_name'], brief).model_dump(mode='json')
    output = root / 'storage/previews/case_research_diagnostics' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + code)
    output.mkdir(parents=True)
    result = {'report_id': report_id, 'region_name': report['region_name'], 'report_approved': False,
              'paid_calls': 0, 'research_plan': build_case_research_plan(snapshot), 'status': 'inputs_captured'}
    def save():
        (output / 'diagnostic.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    if not allow_paid and not resume_case_path:
        print(json.dumps({'status': result['status'], 'paid_calls': 0, 'output': str(output)}, ensure_ascii=False))
        return
    router = LLMRouter(project_root=root, env_values=env)
    router.config['mode'] = 'local_first'  # diagnostic instance, never persist settings
    for task, expected in [('transferability', 'qwen'), ('planner', 'gemma'), ('reviewer', 'qwen')]:
        if router.effective_routes()[task]['provider'] != expected:
            raise ValueError('Diagnostic requires existing Qwen/Gemma local routes')
    original_generate = router.providers['openai'].generate
    async def bounded_search(request):
        if resume_case_path or request.task != 'case_study' or result['paid_calls'] >= 1:
            raise RuntimeError('Additional paid calls forbidden in diagnostic')
        result['paid_calls'] += 1
        save()
        return await original_generate(replace(request, retry_max_output_tokens=None))
    router.providers['openai'].generate = bounded_search
    try:
        await router.preflight_local_models()
        if resume_case_path:
            previous = json.loads(resume_case_path.read_text(encoding='utf-8'))
            if previous.get('report_id') != report_id:
                raise ValueError('Saved research belongs to a different report')
            case_pack = previous['case_pack']
            # 과거 자유서술 지역 집계값을 현재 검증 결과로 재사용하지 않습니다.
            result['previous_case_search_coverage'] = case_pack.get('case_search_coverage')
            case_pack['case_search_coverage'] = comparison_coverage(case_pack.get('benchmark_cases') or [])
            result['case_replay_from'] = str(resume_case_path)
            print('Reusing saved official cases; all paid requests blocked', flush=True)
        else:
            print('Official case search: at most one paid request', flush=True)
            case_pack = await CaseStudyAgent(project_root=root, env_values=env, llm_router=router).collect(
                region_code=code, snapshot=snapshot, planning_brief=brief, force_web=True)
        result['case_pack'] = case_pack
        result['status'] = 'cases_collected'
        save()
        if not case_pack['case_search_coverage']['sufficient_for_comparison']:
            result['status'] = 'insufficient_diverse_evidence'
            return
        pack = {'region_code': code, 'region_name': report['region_name'], 'period': report['period'],
                'snapshot': snapshot, 'planning_brief': brief, **case_pack,
                'quality_contract_version': QUALITY_CONTRACT_VERSION}
        pack['sources'] = [s for s in report.get('evidence_sources') or [] if s.get('source_type') != 'benchmark_case'] + case_pack['sources']
        result['input_evidence_pack'] = pack
        save()
        print('Qwen candidate comparison', flush=True)
        decision = await TransferabilityAgent(api_key='', model='', llm_router=router).assess(evidence_pack=pack)
        result['planning_decision'] = decision
        result['candidate_issues'] = candidate_delivery_issues(pack, decision)
        pack['transfer_assessment'] = decision
        pack['candidate_validation_findings'] = result['candidate_issues']
        save()
        print('Gemma draft', flush=True)
        draft = await PlannerAgent(api_key='', model='', report_schema=REPORT_SCHEMA, llm_router=router).write(pack)
        result['draft'] = draft
        precheck = build_plan_quality_precheck(pack, draft)
        result['precheck'] = precheck
        save()
        print('Qwen local review', flush=True)
        result['local_review'] = await ReviewerAgent(api_key='', model='', llm_router=router).review(
            evidence_pack=pack, draft_report=draft, deterministic_precheck=precheck)
        result['status'] = 'completed_unapproved_diagnostic'
    except Exception as exc:
        result['status'] = 'failed'
        result['error_code'] = getattr(exc, 'code', type(exc).__name__)
    finally:
        result['provider_trace'] = router.consume_trace()
        save()
        print(json.dumps({'status': result['status'], 'paid_calls': result['paid_calls'], 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_id')
    parser.add_argument('--allow-one-paid-case-search', action='store_true')
    parser.add_argument('--reuse-case-diagnostic', type=Path,
                        help='Replay saved case_pack with local models only; blocks every paid request')
    args = parser.parse_args()
    asyncio.run(run(args.report_id, args.allow_one_paid_case_search, args.reuse_case_diagnostic))
