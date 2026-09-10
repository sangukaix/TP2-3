"""Explicit, local-only candidate diagnostic. Does not save or approve a report.

Run from repository root:
python -m ai_server.app.scripts.replay_candidate_repair REPORT_ID
Uses current local snapshot/curated cards, not a byte-identical historical replay.
"""
import asyncio
import argparse
import json
from pathlib import Path
import sys
import urllib.request
from contextlib import nullcontext
from unittest.mock import AsyncMock

from .candidate_thinking_comparison import ComparisonComplete, compare_final_requests

from ..runtime_env import load_project_env
from ..llm.router import LLMRouter
from ..agents.case_study_agent import _load_curated_case_cards
from ..agents.evidence_agent import allowed_domains
from ..agents.transferability_agent import TransferabilityAgent
from ..agents.planning_requirements import (
    QUALITY_CONTRACT_VERSION,
    candidate_delivery_issues,
    stabilize_candidate_decision,
)


async def run(report_id: str, *, fresh: bool = False, compare_thinking: bool = False,
              capture_only: bool = False) -> None:
    root = Path.cwd()
    env = load_project_env(root)
    if not report_id.isalnum():
        raise ValueError('Invalid report ID')
    with urllib.request.urlopen(f'http://127.0.0.1:8112/ai/v1/strategy-reports/{report_id}', timeout=15) as response:
        report = json.load(response)
    from ..main import build_region_snapshot
    snapshot = build_region_snapshot(report['region_name'])
    snapshot['ml_analysis'] = report.get('ml_analysis') or {}
    cases = _load_curated_case_cards(root, allowed_domains(env))
    pack = {'region_code': str((report.get('planning_brief') or {}).get('region_code') or snapshot.get('region_code') or ''),
            'region_name': report['region_name'], 'period': report['period'], 'snapshot': snapshot,
            'planning_brief': report.get('planning_brief'), 'benchmark_cases': cases,
            'sources': report.get('evidence_sources') or [], 'transfer_assessment': report['planning_decision'],
            'quality_contract_version': QUALITY_CONTRACT_VERSION, 'research_gaps': []}
    if not pack['region_code']:
        raise ValueError('Report/snapshot has no region code; do not guess')
    router = LLMRouter(project_root=root, env_values=env)
    router.config['mode'] = 'student_budget'  # in-memory override only
    router.providers['openai'].generate = AsyncMock(side_effect=RuntimeError('Paid calls forbidden in diagnostic'))
    if compare_thinking and router.effective_routes()['transferability']['provider'] != 'qwen':
        raise ValueError('Thinking comparison requires the existing Qwen route')
    feedback = candidate_delivery_issues(pack, pack['transfer_assessment'])
    if fresh:
        pack.pop('transfer_assessment')
    print(json.dumps({'event': 'start', 'mode': 'fresh' if fresh else 'repair',
                      'cases': len(cases), 'issues_before': len(feedback)}, ensure_ascii=False), flush=True)
    try:
        comparison = (compare_final_requests(router.providers['qwen'], pack, root,
                                              capture_only=capture_only)
                      if (compare_thinking or capture_only) else nullcontext())
        with comparison:
            result = await TransferabilityAgent(api_key='', model='', llm_router=router).assess(
                evidence_pack=pack, revision_feedback=None if fresh else feedback)
        issues = candidate_delivery_issues(pack, result)
        stabilized, corrections = stabilize_candidate_decision(pack, result)
        stabilized_issues = candidate_delivery_issues(pack, stabilized)
        print(json.dumps({'event': 'result', 'candidate_contract_passed': not issues,
                          'report_approved': False, 'issues_after': issues, 'decision': result,
                          'stabilized_candidate_contract_passed': not stabilized_issues,
                          'stabilized_issues': stabilized_issues,
                          'automatic_corrections': corrections,
                          'stabilized_decision': stabilized,
                          'trace': router.consume_trace()}, ensure_ascii=False), flush=True)
    except ComparisonComplete:
        print(json.dumps({'event': 'comparison_complete', 'report_approved': False,
                          'automatic_repairs': 0}), flush=True)
    except Exception as exc:
        print(json.dumps({'event': 'failure', 'code': getattr(exc, 'code', type(exc).__name__),
                          'message': str(exc), 'trace': router.consume_trace()}, ensure_ascii=False), flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_id')
    parser.add_argument('--fresh', action='store_true', help='Compare fresh candidates from the same evidence without the previous rejected decision; diagnostic only')
    parser.add_argument('--compare-thinking', action='store_true', help='Diagnostic only: run the identical first final request once with think=false and once with think=true, without repairs')
    parser.add_argument('--capture-only', action='store_true', help='Freeze the first final request after required reads, without generating candidate answers')
    args = parser.parse_args()
    asyncio.run(run(args.report_id, fresh=args.fresh, compare_thinking=args.compare_thinking,
                    capture_only=args.capture_only))
