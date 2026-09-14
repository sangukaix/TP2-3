"""One local Gemma revision and Qwen recheck; no paid calls or report saves."""
import asyncio
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ai_server.app.runtime_env import load_project_env
from ai_server.app.main import REPORT_SCHEMA
from ai_server.app.llm.router import LLMRouter
from ai_server.app.agents.planner_agent import PlannerAgent
from ai_server.app.agents.reviewer_agent import ReviewerAgent
from ai_server.app.agents.transferability_agent import TransferabilityAgent
from ai_server.app.agents.planning_requirements import stabilize_candidate_decision, candidate_delivery_issues
from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck, merge_quality_precheck


async def main(repair_candidates=False, gemma_context=None):
    source_run = ('20260914_114600_230977_28237_revision' if repair_candidates else '20260914_111922_897878_28237')
    path = ROOT / 'storage/previews/case_research_diagnostics' / source_run / 'diagnostic.json'
    original_bytes = path.read_bytes()
    previous = json.loads(original_bytes.decode('utf-8'))
    pack = deepcopy(previous['input_evidence_pack'])
    decision, corrections = stabilize_candidate_decision(pack, previous.get('planning_decision') or pack['transfer_assessment'])
    pack['transfer_assessment'] = decision
    pack['candidate_validation_findings'] = candidate_delivery_issues(pack, decision)
    precheck = build_plan_quality_precheck(pack, previous['draft'], limit=None)
    # Human-reviewed issues are explicit diagnostic feedback, not a fake model verdict.
    precheck['issues'].extend([] if repair_candidates else [
        {'severity': 'major', 'field': 'observed_findings[3].interpretation',
         'problem': '10월 한 달의 방문 -3.74%·소비 -6.27%를 4분기 전체 전망으로 표현했다.',
         'revision_instruction': '10월이라고 정확히 표기하거나 10~12월 합계를 전년 동기 합계와 비교하라. ML 원문 수치는 바꾸지 마라.'},
        {'severity': 'major', 'field': 'strategies[1].comparison_analysis',
         'problem': '단순 전후 매출 변화를 사업이 매출을 높인 인과효과로 표현했다.',
         'revision_instruction': '사례의 운영 방식은 참고하되 전후 관측의 기간·범위와 단독 인과효과가 아니라는 경계를 보존하라.'},
    ])
    precheck['issue_count'] = len(precheck['issues'])
    feedback = merge_quality_precheck({'approved': False, 'overall_score': 0, 'issues': []}, precheck, limit=None)
    folder = ROOT / 'storage/previews/case_research_diagnostics' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + ('_28237_candidate_repair' if repair_candidates else '_28237_revision'))
    folder.mkdir(parents=True)
    result = {'source_file': str(path.relative_to(ROOT)), 'source_sha256': hashlib.sha256(original_bytes).hexdigest(),
              'paid_calls': 0, 'report_approved': False, 'status': 'prepared', 'input_evidence_pack': pack,
              'candidate_corrections': corrections, 'revision_feedback': feedback,
              'scope': 'saved candidate stabilization, one Gemma revision, one Qwen recheck; candidate semantic recomparison not run'}

    def save():
        (folder / 'diagnostic.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')

    env_values = load_project_env(ROOT)
    if gemma_context is not None:
        env_values['OLLAMA_GEMMA_CONTEXT_LENGTH'] = str(gemma_context)
    result['requested_contexts'] = {
        'qwen': env_values.get('OLLAMA_QWEN_CONTEXT_LENGTH'),
        'gemma': env_values.get('OLLAMA_GEMMA_CONTEXT_LENGTH'),
    }
    router = LLMRouter(project_root=ROOT, env_values=env_values)
    router.config['mode'] = 'local_first'
    async def block_paid(request):
        raise RuntimeError('Paid calls forbidden in saved revision diagnostic')
    router.providers['openai'].generate = block_paid
    assert router.effective_routes()['planner_revision']['provider'] == 'gemma'
    assert router.effective_routes()['reviewer']['provider'] == 'qwen'
    save()
    try:
        await router.preflight_local_models()
        if repair_candidates:
            assert router.effective_routes()['transferability']['provider'] == 'qwen'
            result['scope'] = 'one saved candidate repair, one Gemma revision, one Qwen recheck; paid/report saves blocked'
            candidate_feedback = deepcopy(pack['candidate_validation_findings'])
            candidate_feedback.append({
                'severity': 'major', 'field': 'planning_decision.design_candidates',
                'problem': '다른 운영 후보에 동일 사례 ID들을 반복 인용했고 예산·측정·중단 필드에도 준비 조건을 반복했다.',
                'revision_instruction': '각 후보에 실제 가져올 장치가 있는 사례만 인용하라. 스탬프 완주 쿠폰과 숙박 할인은 이용 조건·분모가 다르다. '
                    '선택 지역 관측/ML 신호를 각 후보의 행동과 연결하고, 선택 이유에는 대안보다 나은 점과 불리한 점을 써라. '
                    '예산은 수량×단가 가정, 측정은 지표 정의·기간·원장·같은 분모 비교, 중단은 별도 운영 판단이다. 동일 문장을 복사하지 마라. '
                    '사업이 없는 전년도에는 지급 쿠폰 분모가 없으므로 쿠폰 사용률은 동일 조건 발급 집단끼리 비교하고 전후 매출 비교와 분리하라.'})
            result['candidate_repair_feedback'] = candidate_feedback
            save()
            print('Qwen one targeted candidate repair; paid calls blocked', flush=True)
            repaired = await TransferabilityAgent(api_key='', model='', llm_router=router).assess(
                evidence_pack=pack, revision_feedback=candidate_feedback)
            result['raw_repaired_decision'] = repaired
            decision, corrections = stabilize_candidate_decision(pack, repaired)
            result['candidate_corrections'] = corrections
            pack['transfer_assessment'] = decision
            pack['candidate_validation_findings'] = candidate_delivery_issues(pack, decision)
            result['planning_decision'] = decision
            result['provider_trace'] = router.consume_trace()
            checks = build_plan_quality_precheck(pack, previous['draft'], limit=None)
            checks['issues'].extend([
                {'severity': 'major', 'field': 'strategies[1]', 'problem': '후보 재비교 결과와 본문의 일관성 확인 필요',
                 'revision_instruction': '재비교된 선택 후보의 운영 방식·사례 ID·대상·혜택 조건·예산·측정으로 본문을 동기화하라. '
                    '완주 조건과 거점 한 곳 방문 인증을 혼동하지 마라. 쿠폰 사용률은 같은 조건의 지급 집단끼리 비교하고 미운영 지역의 매출 비교와 분리하라. '
                    '이미 교정한 10월 전망 기간 및 사례 전후 변화의 비인과 해석을 유지하라.'},
            ])
            checks['issue_count'] = len(checks['issues'])
            feedback = merge_quality_precheck({'approved': False, 'overall_score': 0, 'issues': []}, checks, limit=None)
            result['revision_feedback'] = feedback
            result['status'] = 'candidate_repair_completed'
            save()
        print('Gemma one local revision; paid calls blocked', flush=True)
        result['draft'] = await PlannerAgent(api_key='', model='', report_schema=REPORT_SCHEMA, llm_router=router).write(
            pack, revision_feedback=feedback, previous_draft=previous['draft'])
        result['status'] = 'revision_completed'
        result.setdefault('provider_trace', []).extend(router.consume_trace())
        checks = build_plan_quality_precheck(pack, result['draft'], limit=None)
        result['precheck'] = checks
        save()
        print('Qwen local recheck', flush=True)
        review = await ReviewerAgent(api_key='', model='', llm_router=router).review(
            evidence_pack=pack, draft_report=result['draft'], deterministic_precheck=checks)
        result['local_review'] = review
        result['merged_local_review'] = merge_quality_precheck(review, checks, limit=None)
        result['status'] = 'completed_unapproved_diagnostic'
    except Exception as exc:
        result['status'] = 'failed'
        result['error_code'] = getattr(exc, 'code', type(exc).__name__)
    finally:
        result.setdefault('provider_trace', []).extend(router.consume_trace())
        result['source_unchanged'] = path.read_bytes() == original_bytes
        save()
        print(json.dumps({'status': result['status'], 'paid_calls': 0, 'output': str(folder)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair-candidates', action='store_true')
    parser.add_argument('--gemma-context', type=int, choices=[65536, 131072])
    args = parser.parse_args()
    asyncio.run(main(args.repair_candidates, args.gemma_context))
