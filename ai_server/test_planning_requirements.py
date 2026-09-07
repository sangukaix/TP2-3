"""원주 미승인 사례를 재현한다. 유료 API·GPU·MySQL 없이 정상/오류 경로 검증."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from ai_server.app.agents.planning_requirements import (
    EXECUTION_EVIDENCE_RULES, QUALITY_CONTRACT_VERSION, build_completion_checklist,
    candidate_delivery_issues, execution_delivery_issues, has_cost_formula, has_unlabeled_fixed_budget_total,
    is_budget_only_title, measurement_missing, timeframe_schedule_issues,
)
from ai_server.app.agents.plan_quality_gate import build_plan_quality_precheck, merge_quality_precheck
from ai_server.app.agents.planner_agent import _build_revision_evidence_pack
from ai_server.app.agents.transferability_agent import TransferabilityAgent
from ai_server.app.agents.report_orchestrator import orchestrate_strategy_report, _CASE_STUDY_CACHE, _EVIDENCE_CACHE
from ai_server.app.agents import prompts
from ai_server.app.llm.local_agent import _prefetch_required_evidence
from ai_server.app.llm.local_prompts import local_instructions
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.llm.errors import LLMProviderError
from ai_server.test_report_orchestrator import _draft, FakePlannerAgent

MEASUREMENT = '분자: 취소 제외 지급 건수 / 분모: 적격 신청 건수. 기준기간은 운영 전 4주, 담당자 원자료를 매주 집계하여 순차 도입 비교집단과 비교. 착수 전 기준선을 확인해 목표 확정.'


def transfer(valid=True):
    candidates = [{'candidate_id': f'candidate:{i}', 'candidate_type': kind, 'title': f'지역 시범 {i}',
                   'mechanism': '운영 원리', 'local_fit': '2026-06 지역 관측값으로 가설 검토',
                   'prerequisites': '가맹점 및 자료 제공 협약 전 지급 보류',
                   'budget_formula': '적격 신청 건수×지급 단가 + 운영일수×일 단가. 담당자가 견적 확인' if valid else '환급 지원금 + 운영비',
                   'measurement_plan': MEASUREMENT if valid else '상품권 결제 증가율',
                   'evidence_source_ids': ['dataset:1'] if valid else ['case:1'],
                   'case_source_ids': [f'case:{i}']}
                  for i, kind in ((1, 'spend_conversion'), (2, 'reservation_conversion'))]
    return {'selection_status': 'ready' if valid else 'needs_evidence', 'selected_candidate_id': 'candidate:1',
            'selection_reason': '자료 제공 조건과 운영 난도를 비교한 조건부 후보 선정',
            'recommended_case_ids': ['case:1', 'case:2'], 'candidate_assessments': [],
            'strategy_brief': {'working_title': '원주 조건부 시범', 'supporting_case_ids': ['case:1']},
            'design_candidates': candidates}


def pack(valid=True):
    return {'region_code': '51130', 'region_name': '강원특별자치도 원주시',
            'quality_contract_version': QUALITY_CONTRACT_VERSION, 'snapshot': {},
            'transfer_assessment': transfer(valid), 'research_gaps': [],
            'sources': [{'source_id': 'dataset:1', 'source_type': 'dataset'},
                        {'source_id': 'case:1', 'source_type': 'benchmark_case'},
                        {'source_id': 'case:2', 'source_type': 'benchmark_case'}],
            'benchmark_cases': [{'source_id': 'case:1', 'intervention': '지역 환급'},
                                {'source_id': 'case:2', 'intervention': '시간대 예약'}]}


class PlanningRequirementsTest(unittest.TestCase):
    def test_budget_word_alone_is_not_a_formula(self):
        self.assertFalse(has_cost_formula('상품권 발행비 + 환급금 + 홍보비 (공식 단가 확인 필요)'))
        self.assertTrue(has_cost_formula('신청 수량 × 공식 단가 + 운영일수 × 일 단가'))

    def test_unlabeled_total_cannot_copy_another_region_budget(self):
        self.assertTrue(has_unlabeled_fixed_budget_total('총 1,000,000,000원으로 편성'))
        self.assertTrue(has_unlabeled_fixed_budget_total('총 10억 원'))
        self.assertFalse(has_unlabeled_fixed_budget_total('기획 가정·미확정 참고 견적: 총 10억 원'))

    def test_budget_only_title_is_not_an_intervention(self):
        self.assertTrue(is_budget_only_title('야간관광 특화도시 예산 편성'))
        self.assertFalse(is_budget_only_title('야간 예약·식음 결제 연계 시범'))

    def test_step_outside_declared_timeframe_is_critical(self):
        strategy = {
            'timeframe': '2026-09 ~ 2026-11, 3개월',
            'implementation_steps': [
                {'schedule': '2026-09'}, {'schedule': '2026-10'}, {'schedule': '2026-11'},
                {'schedule': '2026-12'}, {'schedule': '2027-01'},
            ],
        }
        issues = timeframe_schedule_issues(strategy, 'strategies[1]')
        self.assertEqual(issues[0]['severity'], 'critical')
        self.assertIn('기간', issues[0]['problem'])

    def test_variable_formula_does_not_require_invented_money(self):
        result = build_plan_quality_precheck(pack(), _draft('정상'))
        self.assertEqual(result['issues'], [])

    def test_candidate_needs_local_evidence_not_only_another_city_case(self):
        issues = candidate_delivery_issues(pack(False), transfer(False))
        self.assertEqual(sum(row['field'].endswith('.local_fit') for row in issues), 2)

    def test_ready_flag_cannot_hide_broken_candidate_contract(self):
        evidence = pack(False)
        evidence['transfer_assessment']['selection_status'] = 'ready'
        precheck = build_plan_quality_precheck(evidence, _draft('본문'))
        self.assertFalse(merge_quality_precheck({'approved': True, 'overall_score': 95}, precheck)['approved'])

    def test_two_candidates_not_misreported_as_candidate_count_shortage(self):
        evidence = pack()
        evidence['transfer_assessment']['selection_status'] = 'needs_evidence'
        fields = [row['field'] for row in build_plan_quality_precheck(evidence, _draft('본문'))['issues']]
        self.assertIn('planning_decision.selection_status', fields)
        self.assertNotIn('planning_decision', fields)

    def test_kpi_one_keyword_is_not_full_measurement_design(self):
        self.assertIn('확인 주기', measurement_missing('전년 대비 증가율 비교'))
        self.assertEqual(measurement_missing(MEASUREMENT), [])

    def test_incorrect_growth_formula_is_critical(self):
        issues = execution_delivery_issues({'kpi': '결제액 증가율 (분자: 사업기간 결제액 / 분모: 전년 동기 결제액)'}, 'strategies[1]')
        self.assertTrue(any(row['field'].endswith('growth_formula') and row['severity'] == 'critical' for row in issues))

    def test_growth_difference_and_zero_guard_are_accepted(self):
        kpi = MEASUREMENT + ' 증가율=(이번 값-전년 값)/전년 값×100; 전년 값 0이면 산정 불가.'
        self.assertFalse(any(row['field'].endswith('growth_formula') for row in execution_delivery_issues({'kpi': kpi}, 's')))

    def test_unfounded_twenty_percent_success_rule_is_flagged(self):
        issues = execution_delivery_issues({'kpi': MEASUREMENT.split('착수 전')[0] + '성공 20% 이상, 미만이면 중단'}, 's')
        self.assertTrue(any(row['field'].endswith('threshold_basis') for row in issues))

    def test_labeled_provisional_threshold_is_not_misreported_as_confirmed(self):
        issues = execution_delivery_issues({'kpi': MEASUREMENT + '잠정 가정 목표 20% 달성 시 확대 검토'}, 's')
        self.assertFalse(any(row['field'].endswith('threshold_basis') for row in issues))

    def test_missing_operating_owner_is_detected(self):
        issues = execution_delivery_issues({'kpi': MEASUREMENT, 'implementation_steps': [{'task': '환급 시스템 준비'}]}, 's')
        self.assertTrue(any(row['field'].endswith('.task') for row in issues))

    def test_all_deterministic_findings_are_retained_for_user(self):
        report = _draft('부실')
        report['strategies'][0]['kpi'] = '20% 이상이면 성공, 증가율=올해/전년'
        report['strategies'][0]['implementation_steps'] = [{'step': i, 'schedule': '1주', 'task': '준비', 'deliverable': '표'} for i in range(1, 6)]
        short = build_plan_quality_precheck(pack(False), report)
        full = build_plan_quality_precheck(pack(False), report, limit=None)
        self.assertGreater(len(full['issues']), 8)
        self.assertEqual(short['issue_count'], len(full['issues']))
        self.assertEqual(len(short['issues']), 8)
        self.assertEqual(short['issues'][0]['severity'], 'critical')

    def test_checklist_separates_writing_issues_from_acquisition(self):
        report = _draft('환급')
        evidence = pack(False)
        review = build_plan_quality_precheck(evidence, report, limit=None)
        checklist = build_completion_checklist(review, evidence, report)
        by_id = {row['id']: row for row in checklist}
        self.assertIn('2건', by_id['case_fit']['action'])
        self.assertIn('voucher_rules', by_id)
        self.assertIn('개인정보', str(by_id['voucher_rules']['required_materials']))
        self.assertNotIn('web_candidates', by_id)

    def test_web_configuration_is_optional_and_not_case_data(self):
        evidence = pack()
        evidence['research_gaps'] = ['무료 공식 웹 검색 API 키가 설정되지 않았습니다.']
        rows = build_completion_checklist({'issues': []}, evidence, _draft('본문'))
        self.assertEqual([row['id'] for row in rows], ['web_candidates'])
        self.assertIn('선택', rows[0]['status'])

    def test_local_and_cloud_receive_same_new_contract(self):
        for task in ('transferability', 'planner', 'planner_revision', 'reviewer'):
            self.assertIn(EXECUTION_EVIDENCE_RULES, local_instructions(task))
            self.assertIn(prompts.NATIONWIDE_CASE_RULES, local_instructions(task))
        for rules in (prompts.TRANSFERABILITY_INSTRUCTIONS, prompts.PLANNER_INSTRUCTIONS, prompts.REVIEW_INSTRUCTIONS):
            self.assertIn(EXECUTION_EVIDENCE_RULES, rules)

    def test_revision_retains_contract_gaps_and_candidate_sources(self):
        evidence = pack()
        evidence['research_gaps'] = ['측정 협약 확인 필요']
        revised = _build_revision_evidence_pack(evidence, _draft('본문'))
        self.assertEqual(revised['quality_contract_version'], QUALITY_CONTRACT_VERSION)
        self.assertEqual(revised['research_gaps'], evidence['research_gaps'])
        self.assertTrue({'case:1', 'case:2'} <= {row['source_id'] for row in revised['sources']})

    def test_prefetch_reads_selected_not_arbitrary_first_case_and_all_candidates(self):
        evidence = pack()
        evidence['benchmark_cases'].insert(0, {'source_id': 'case:unused', 'intervention': '야간 행사'})
        workspace = EvidenceTools({'evidence_pack': evidence}, task='reviewer')
        before = deepcopy(workspace.pack)
        fetched = _prefetch_required_evidence(workspace, 'reviewer')
        self.assertTrue({'case:1', 'case:2'} <= workspace.read_source_ids)
        self.assertNotIn('case:unused', workspace.read_source_ids)
        self.assertEqual(sum(row['tool'] == 'read_task_section' for row in fetched), 1)
        # 선택 후보 원문은 get_planning_decision, 비교 후보는 별도 조각으로 한 번씩 전달한다.
        selected = next(row['result']['selected_candidate'] for row in fetched if row['tool'] == 'get_planning_decision')
        self.assertEqual(selected, evidence['transfer_assessment']['design_candidates'][0])
        self.assertEqual(workspace.pack, before)

    def test_revision_keeps_candidate_local_fact_and_added_case_source(self):
        evidence = pack()
        evidence['sources'].extend([
            {'source_id': 'regional-status:51130', 'source_type': 'regional_tourism_status'},
            {'source_id': 'case:3', 'source_type': 'benchmark_case'},
        ])
        evidence['transfer_assessment']['design_candidates'][1]['evidence_source_ids'].append('regional-status:51130')
        evidence['benchmark_cases'].append({'source_id': 'case:3', 'intervention': '체험 예약'})
        revised = _build_revision_evidence_pack(evidence, _draft('본문'))
        self.assertTrue({'regional-status:51130', 'case:3'} <= {row['source_id'] for row in revised['sources']})


class RepairFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_repair_feedback_is_visible_in_local_tools_without_dropping_previous_comparison(self):
        router = SimpleNamespace(generate=AsyncMock(return_value={}))
        evidence = pack(False)
        issues = candidate_delivery_issues(evidence, evidence['transfer_assessment'])
        await TransferabilityAgent(api_key='', model='unused', llm_router=router).assess(evidence_pack=evidence, revision_feedback=issues)
        request = router.generate.call_args.args[0]
        tools = EvidenceTools(request.input_payload, task='transferability')
        self.assertEqual(tools.overview()['quality_review_feedback']['issues'], issues)
        self.assertEqual(tools.pack['transfer_assessment'], evidence['transfer_assessment'])
        self.assertEqual(request.task, 'transferability')
        self.assertEqual(request.local_max_output_tokens, 5600)

    async def run_flow(self, repair_fails=False, repair_valid=True):
        evidence = pack(False)
        class Evidence:
            def __init__(self, **kwargs): pass
            async def collect(self, **kwargs):
                return {'sources': evidence['sources'], 'research_gaps': [], 'trace': []}
        class Cases:
            def __init__(self, **kwargs): pass
            async def collect(self, **kwargs):
                return {'benchmark_cases': evidence['benchmark_cases'], 'sources': [], 'research_gaps': [], 'trace': []}
        assessments = []
        class Transfer:
            def __init__(self, **kwargs): pass
            async def assess(self, *, evidence_pack, revision_feedback=None):
                assessments.append(deepcopy(revision_feedback))
                if revision_feedback and repair_fails:
                    raise LLMProviderError('OLLAMA_TIMEOUT', '테스트 실패')
                return transfer(bool(revision_feedback) and repair_valid)
        final_flags = []
        async def review(**kwargs):
            final_flags.append(kwargs.get('final_pass', False))
            return {'approved': True, 'overall_score': 90, 'issues': [], 'summary': '검수'}
        router = SimpleNamespace(local_first=True, student_budget=True,
                                 public_config=lambda: {}, effective_routes=lambda: {},
                                 preflight_local_models=AsyncMock(), consume_trace=lambda: [])
        ml = SimpleNamespace(model_dump=lambda **kwargs: {}, status='unavailable', reason_code='test', horizon_policy={})
        _CASE_STUDY_CACHE.clear()
        _EVIDENCE_CACHE.clear()
        with (
            TemporaryDirectory() as directory,
            patch('ai_server.app.agents.report_orchestrator.LLMRouter', return_value=router),
            patch('ai_server.app.agents.report_orchestrator.build_planning_ml_evidence', return_value=ml),
            patch('ai_server.app.agents.report_orchestrator.EvidenceAgent', Evidence),
            patch('ai_server.app.agents.report_orchestrator.CaseStudyAgent', Cases),
            patch('ai_server.app.agents.report_orchestrator.TransferabilityAgent', Transfer),
            patch('ai_server.app.agents.report_orchestrator.PlannerAgent', FakePlannerAgent),
            patch('ai_server.app.agents.report_orchestrator.ReviewerAgent', return_value=SimpleNamespace(review=review)),
        ):
            result = await orchestrate_strategy_report(project_root=Path(directory), env_values={}, region_code='51130',
                                                       snapshot={'region_name': '강원특별자치도 원주시'}, report_schema={})
        return result, assessments, final_flags

    async def test_upstream_repair_happens_once_before_draft_and_one_final_audit(self):
        result, calls, final_flags = await self.run_flow()
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1])
        self.assertEqual(result['planning_decision']['selection_status'], 'ready')
        self.assertEqual(final_flags, [False, True])
        self.assertTrue(result['quality_review']['approved'])

    async def test_failed_candidate_repair_preserves_draft_and_blocks_paid_audit(self):
        result, calls, final_flags = await self.run_flow(repair_fails=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['planning_decision']['selection_status'], 'needs_evidence')
        self.assertFalse(result['quality_review']['approved'])
        self.assertNotIn(True, final_flags)
        self.assertTrue(result['quality_review']['completion_checklist'])

    async def test_repair_still_insufficient_does_not_loop_or_force_ready(self):
        result, calls, final_flags = await self.run_flow(repair_valid=False)
        self.assertEqual(len(calls), 2)
        self.assertFalse(result['quality_review']['approved'])
        self.assertTrue(result['quality_review']['validation_findings'])
        self.assertNotIn(True, final_flags)


if __name__ == '__main__':
    unittest.main()
