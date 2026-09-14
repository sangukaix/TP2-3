"""Saved Bupyeong diagnostic only: no network, model, report write or approval."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
blocked = []


def guard(event, args):
    if event not in ('socket.connect', 'socket.getaddrinfo'):
        return
    frame = sys._getframe()
    while frame:
        if frame.f_code is socket.socketpair.__code__:
            return
        frame = frame.f_back
    blocked.append(event)
    raise OSError('OFFLINE_REPLAY: network disabled')


sys.addaudithook(guard)
from ai_server.app.agents.planner_agent import PlannerAgent
from ai_server.app.agents.planning_requirements import (
    QUALITY_CONTRACT_VERSION, candidate_delivery_issues, stabilize_candidate_decision,
)
from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck


async def main():
    path = ROOT / 'storage/previews/case_research_diagnostics/20260913_111923_030012_28237/diagnostic.json'
    source_bytes = path.read_bytes()
    original = json.loads(source_bytes.decode('utf-8'))
    pack = deepcopy(original['input_evidence_pack'])
    pack['quality_contract_version'] = QUALITY_CONTRACT_VERSION
    decision, corrections = stabilize_candidate_decision(pack, original['planning_decision'])
    pack['transfer_assessment'] = decision
    findings = candidate_delivery_issues(pack, decision)
    pack['candidate_validation_findings'] = findings
    router = SimpleNamespace(generate=AsyncMock(return_value={}))
    await PlannerAgent(api_key='', model='', report_schema={}, llm_router=router).write(pack)
    payload = router.generate.call_args.args[0].input_payload
    assert payload['quality_review_feedback']['issues'] == findings
    checks = build_plan_quality_precheck(pack, original['draft'], limit=None)
    # Do not rewrite the stored Gemma response or pretend to have generated a new one.
    output = {
        'mode': 'offline_input_replay', 'source_file': str(path.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'llm_calls': 0, 'paid_calls': 0, 'blocked_network_attempts': len(blocked),
        'report_approved': False, 'draft_regenerated': False,
        'candidate_corrections': corrections,
        'candidate_handoff_findings': findings,
        'stabilized_candidates': decision['design_candidates'],
        'unchanged_draft_findings': checks,
        'manual_remaining': [
            '선정 후보의 서울 사례 인용과 인천 시장사업 운영 규모가 섞인 의미 문제를 실제 Qwen 재비교로 확인해야 한다.',
            '기존 Gemma 초안의 업체 수×지급 단가, 00% 목표는 여전히 잘못된 본문이며 이번에는 재생성하지 않았다.',
            '서울 개막 전후 1주 매출20%를 사업이 직접 증가시켰다고 쓴 인과 표현은 원문 기간·범위와 함께 수정해야 한다.',
            '선택 지역 장소의 근거 연결과 실제 참여 조건은 별도 의미 검수가 필요하다.',
        ],
    }
    assert path.read_bytes() == source_bytes
    target = Path(__file__).with_name('planner_handoff_saved_replay.json')
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'output': str(target.relative_to(ROOT)), 'source_unchanged': True,
        'candidate_corrections': len(corrections), 'handoff_findings': len(findings),
        'draft_issue_fields': [r['field'] for r in checks['issues']],
        'llm_calls': 0, 'paid_calls': 0, 'report_approved': False,
    }, ensure_ascii=False, indent=2))
    for candidate in decision['design_candidates']:
        print(candidate['title'])
        print(candidate['budget_formula'])
        print(candidate['measurement_plan'])


asyncio.run(main())
