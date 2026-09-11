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
    is_budget_only_title, measurement_missing, overclaims_local_fit, stabilize_candidate_decision,
    timeframe_schedule_issues, uses_region_wide_refund_budget,
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
    def test_regionwide_observations_cannot_become_pilot_refund_budget_or_effect(self):
        budget = '외지인 방문객 수 × 평균 지출액 × 환급률 + 운영비 10%'
        local_fit = '내비게이션 검색량을 바탕으로 교통 할인이 효과적일 수 있다.'
        self.assertTrue(uses_region_wide_refund_budget(budget))
        self.assertTrue(overclaims_local_fit(local_fit))
        value = transfer()
        value['design_candidates'][0]['budget_formula'] = budget
        value['design_candidates'][0]['local_fit'] = local_fit
        value['design_candidates'][0]['measurement_plan'] = (
            '지표=사용률, 분자=사용 ID, 분모=발급 ID. 기준기간=운영 전 4주, 월별 측정. '
            '원자료=사업 담당자의 발급·사용 원장. 비교집단=전국 평균 사용률.'
        )
        fields = {row['field'] for row in candidate_delivery_issues(pack(), value)}
        self.assertIn('planning_decision.design_candidates[1].budget_formula.population_scope', fields)
        self.assertIn('planning_decision.design_candidates[1].local_fit.interpretation', fields)
        self.assertIn('planning_decision.design_candidates[1].measurement_plan.comparison_source', fields)
        stabilized, corrections = stabilize_candidate_decision(pack(), value)
        candidate = stabilized['design_candidates'][0]
        self.assertIn('기획 가정/미확정', candidate['budget_formula'])
        self.assertIn('사업의 적합성·효과 증거가 아니다', candidate['local_fit'])
        self.assertNotIn('전국 평균', candidate['measurement_plan'])
        self.assertEqual(stabilized['strategy_brief']['budget_formula'], candidate['budget_formula'])
        self.assertTrue(corrections)
        strategy = {'title': '원주시 환급 시범', 'budget': budget, 'kpi': candidate['measurement_plan'],
                    'implementation_steps': []}
        self.assertIn('strategies[1].budget.population_scope',
                      {row['field'] for row in execution_delivery_issues(strategy, 'strategies[1]')})

    def test_server_stabilizes_mechanical_candidate_errors_without_approving(self):
        evidence = pack()
        evidence['benchmark_cases'][0]['case_region'] = '전북특별자치도 전주시'
        value = transfer(False)
        value['selection_status'] = 'ready'
        value['selected_candidate_id'] = 'candidate:missing'
        value['recommended_case_ids'].append('case:invented')
        value['strategy_brief'].update({
            'pilot_scope': '전북특별자치도 전주시',
            'budget_formula': '총 10억 원. 운영일수×일 단가',
        })
        value['design_candidates'][0]['title'] = '야간관광 예산 편성 모델 도입'
        stabilized, corrections = stabilize_candidate_decision(evidence, value)
        self.assertTrue(corrections)
        self.assertEqual(stabilized['selection_status'], 'needs_evidence')
        self.assertEqual(stabilized['selected_candidate_id'], 'candidate:1')
        self.assertNotIn('case:invented', stabilized['recommended_case_ids'])
        self.assertIn('강원특별자치도 원주시', stabilized['strategy_brief']['pilot_scope'])
        self.assertIn('기획 가정/미확정', stabilized['strategy_brief']['budget_formula'])
        self.assertIn('이용·결제', stabilized['design_candidates'][0]['title'])
        self.assertIn('분자=', stabilized['design_candidates'][0]['measurement_plan'])
        self.assertFalse(any(row['severity'] == 'critical'
                             for row in candidate_delivery_issues(evidence, stabilized)))

    def test_fresh_trial_budget_alias_type_and_unjustified_threshold_are_rejected(self):
        value = transfer()
        row = value['design_candidates'][1]
        row.update(title='야간관광 특화도시 예산 편성 모델 도입',
                   candidate_type='night_time_experience',
                   stop_or_scale_rule='성공 기준: 소비 증가율 10% 이상. 중단 기준: 5% 미만.')
        fields = {x['field'] for x in candidate_delivery_issues(pack(), value)}
        for suffix in ('title', 'candidate_type', 'stop_or_scale_rule'):
            self.assertIn('planning_decision.design_candidates[2].' + suffix, fields)
        self.assertFalse(is_budget_only_title('야간 예약·체험 모델 도입'))

    def test_quarterly_frequency_is_not_reported_as_missing(self):
        self.assertNotIn('확인 주기', measurement_missing(MEASUREMENT.replace('매주', '분기별')))
        self.assertIn('확인 주기', measurement_missing(MEASUREMENT.replace('매주', '정기적으로')))

    def test_collection_ledger_is_valid_raw_measurement_source(self):
        self.assertNotIn('원자료·수집방법', measurement_missing(
            '분자=완료 ID, 분모=승인 ID. 운영 전 4주 기준, 매주 측정. '
            '수집방법: 사업 담당자 집계 원장. 미운영일과 비교.'
        ))

    def test_unapproved_case_performance_is_removed_from_comparison(self):
        evidence = pack()
        evidence['benchmark_cases'][0].update(
            case_region='전라남도 강진군', quantitative_result_approved=False,
        )
        report = _draft('본문')
        report['strategies'][0]['comparison_analysis'] = '강진군 소비 118.7억 원, 전년 대비 1.7배 증가 사례를 적용한다.'
        fields = {row['field'] for row in build_plan_quality_precheck(evidence, report, limit=None)['issues']}
        self.assertIn('strategies[1].comparison_analysis.unapproved_case_result', fields)
        report['strategies'][0]['comparison_analysis'] = '강진군의 신청·증빙·지역상품권 환급 절차만 참고한다.'
        fields = {row['field'] for row in build_plan_quality_precheck(evidence, report, limit=None)['issues']}
        self.assertNotIn('strategies[1].comparison_analysis.unapproved_case_result', fields)

    def test_unlabeled_candidate_and_brief_totals_block_even_with_multiplication(self):
        value = transfer()
        value['selection_status'] = 'needs_evidence'
        budget = '총 10억 원. 운영일수×일 단가 + 적격 건수×지급 단가'
        value['design_candidates'][0]['budget_formula'] = budget
        value['strategy_brief']['budget_formula'] = budget
        found = [row for row in candidate_delivery_issues(pack(), value)
                 if row['field'].endswith('.fixed_total')]
        self.assertEqual(len(found), 2)
        self.assertTrue(all(row['severity'] == 'critical' for row in found))
        value['design_candidates'][0]['budget_formula'] = '미확정 참고 견적: ' + budget
        value['strategy_brief']['budget_formula'] = '미확정 참고 견적: ' + budget
        self.assertFalse(any(row['field'].endswith('.fixed_total')
                             for row in candidate_delivery_issues(pack(), value)))

    def test_other_city_scope_copy_is_rejected_but_reference_is_allowed(self):
        evidence = pack()
        evidence['benchmark_cases'][0]['case_region'] = '전북특별자치도 전주시'
        value = transfer()
        value['strategy_brief']['pilot_scope'] = '전북특별자치도 전주시'
        self.assertTrue(any(row['field'].endswith('.pilot_scope') for row in candidate_delivery_issues(evidence, value)))
        value['strategy_brief']['pilot_scope'] = '원주시에서 전주시 운영 방식을 참고한 조건부 한 권역 시범'
        self.assertFalse(any(row['field'].endswith('.pilot_scope') for row in candidate_delivery_issues(evidence, value)))

    def test_other_city_title_and_target_users_are_localized_without_approving(self):
        evidence = pack()
        evidence['benchmark_cases'][0]['case_region'] = '전라남도 강진군'
        value = transfer()
        value['design_candidates'][0]['title'] = '강진 반값여행 지역환급 모델 도입'
        value['strategy_brief'].update({
            'working_title': '강진 반값여행 지역환급 모델 도입',
            'target_users': '강진을 여행하는 방문객',
            'pilot_scope': '전라남도 강진군',
        })
        fields = {row['field'] for row in candidate_delivery_issues(evidence, value)}
        self.assertIn('planning_decision.design_candidates[1].title', fields)
        self.assertIn('planning_decision.strategy_brief.working_title', fields)
        self.assertIn('planning_decision.strategy_brief.target_users', fields)
        stabilized, corrections = stabilize_candidate_decision(evidence, value)
        self.assertTrue(corrections)
        self.assertEqual(stabilized['selection_status'], 'needs_evidence')
        self.assertNotIn('강진', stabilized['design_candidates'][0]['title'])
        self.assertNotIn('강진', stabilized['strategy_brief']['working_title'])
        self.assertEqual(stabilized['strategy_brief']['target_users'], '강원특별자치도 원주시 방문객')
        self.assertIn('강원특별자치도 원주시', stabilized['strategy_brief']['pilot_scope'])

    def test_budget_only_mechanism_is_not_hidden_by_title_rewrite(self):
        evidence = pack()
        evidence['benchmark_cases'][0]['case_region'] = '전북특별자치도 전주시'
        value = transfer()
        value['design_candidates'][1].update({
            'title': '전주시 야간관광 특화도시 예산 편성 모델 도입',
            'mechanism': '야간 콘텐츠를 지속 운영할 예산 구조 마련',
        })
        stabilized, _ = stabilize_candidate_decision(evidence, value)
        self.assertEqual(stabilized['design_candidates'][1]['title'], value['design_candidates'][1]['title'])
        fields = {row['field'] for row in candidate_delivery_issues(evidence, stabilized)}
        self.assertIn('planning_decision.design_candidates[2].title', fields)
        self.assertIn('planning_decision.design_candidates[2].mechanism', fields)

    def test_complete_revision_feedback_keeps_more_than_eight_findings(self):
        findings = [{'severity': 'major', 'field': f'field:{i}', 'problem': f'problem:{i}',
                     'revision_instruction': 'repair'} for i in range(16)]
        review = {'approved': True, 'overall_score': 90, 'issues': [], 'summary': 'review'}
        result = merge_quality_precheck(review, {'checked': True, 'issues': findings}, limit=None)
        self.assertEqual(len(result['issues']), 16)
        self.assertFalse(result['approved'])
        repeated = merge_quality_precheck(result, {'checked': True, 'issues': findings}, limit=None)
        self.assertEqual(repeated['summary'], result['summary'])
        self.assertEqual(len(repeated['issues']), 16)

    def test_corrupted_brief_case_id_is_rejected(self):
        value = transfer()
        value['strategy_brief']['supporting_case_ids'] = ['case:unknown']
        self.assertTrue(any(row['field'].endswith('.case_source_ids') for row in candidate_delivery_issues(pack(), value)))

    def test_candidate_without_registered_case_stays_needs_review(self):
        value = transfer()
        value['recommended_case_ids'] = []
        value['design_candidates'][0]['case_source_ids'] = []
        fields = {row['field'] for row in candidate_delivery_issues(pack(), value)}
        self.assertIn('planning_decision.recommended_case_ids', fields)
        self.assertIn('planning_decision.design_candidates[1].case_source_ids', fields)

    def test_duplicate_candidate_types_are_rejected(self):
        value = transfer()
        value['design_candidates'][1]['candidate_type'] = 'spend_conversion'
        self.assertTrue(any(row['field'].endswith('.candidate_type') for row in candidate_delivery_issues(pack(), value)))

    def test_budget_word_alone_is_not_a_formula(self):
        self.assertFalse(has_cost_formula('수량×단가 산식: 사무관리(10%) 1억 원, 행사운영(40%) 4억 원. 기획 가정'))
        self.assertTrue(has_cost_formula('수량×단가 산식: 운영일수×일 단가 + 적격 신청 건수×건별 단가'))
        self.assertFalse(has_cost_formula('상품권 발행비 + 환급금 + 홍보비 (공식 단가 확인 필요)'))
        self.assertTrue(has_cost_formula('신청 수량 × 공식 단가 + 운영일수 × 일 단가'))

    def test_unlabeled_total_cannot_copy_another_region_budget(self):
        self.assertTrue(has_unlabeled_fixed_budget_total('총 1,000,000,000원으로 편성'))
        self.assertTrue(has_unlabeled_fixed_budget_total('총 10억 원'))
        self.assertFalse(has_unlabeled_fixed_budget_total('기획 가정·미확정 참고 견적: 총 10억 원'))

    def test_budget_only_title_is_not_an_intervention(self):
        self.assertTrue(is_budget_only_title('야간관광 특화도시 예산 편성'))
        self.assertTrue(is_budget_only_title('야간관광 특화도시 운영 예산 체계 구축'))
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

    def test_candidate_repair_does_not_prioritize_rejected_case_but_keeps_draft(self):
        evidence = pack()
        evidence['benchmark_cases'] = [
            {'source_id': 'case:return', 'intervention': '관광주민증'},
            {'source_id': 'case:refund', 'intervention': '반값여행 환급'},
            {'source_id': 'case:budget', 'intervention': '야간 예산 편성'},
        ]
        evidence['transfer_assessment']['recommended_case_ids'] = ['case:budget']
        # sources는 과거 선택안 순서일 수 있으므로 현재 benchmark_cases 순서와 다르게 둔다.
        evidence['sources'].insert(0, {'source_id': 'case:budget', 'source_type': 'benchmark_case'})
        evidence['transfer_assessment']['strategy_brief']['supporting_case_ids'] = ['case:budget']
        payload = {'evidence_pack': evidence, 'quality_review_feedback': {'issues': [{'field': 'title'}]}}
        before = deepcopy(payload)
        workspace = EvidenceTools(payload, task='transferability')
        fetched = _prefetch_required_evidence(workspace, 'transferability')
        fetched_tools = {row['tool'] for row in fetched}
        self.assertNotIn('get_nationwide_bigdata_context', fetched_tools)
        self.assertNotIn('get_case_comparison_matrix', fetched_tools)
        self.assertTrue({'case:return', 'case:refund'} <= workspace.read_source_ids)
        self.assertNotIn('case:budget', workspace.read_source_ids)
        decision = workspace.execute('get_planning_decision', {})
        self.assertEqual(decision['review_context']['status'], 'rejected_candidate_draft')
        self.assertEqual(decision['strategy_brief'], evidence['transfer_assessment']['strategy_brief'])
        self.assertEqual(payload, before)
        reviewer = EvidenceTools(payload, task='reviewer')
        _prefetch_required_evidence(reviewer, 'reviewer')
        self.assertIn('case:budget', reviewer.read_source_ids)
        self.assertNotIn('review_context', reviewer.execute('get_planning_decision', {}))

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

    def test_planner_prefetch_omits_duplicate_nationwide_macro_table(self):
        evidence = pack()
        evidence['snapshot']['nationwide_bigdata_context'] = {'available': True, 'monthly_rows': ['large']}
        workspace = EvidenceTools({'evidence_pack': evidence}, task='planner')
        fetched = _prefetch_required_evidence(workspace, 'planner')
        self.assertNotIn('get_nationwide_bigdata_context', {row['tool'] for row in fetched})
        self.assertNotIn('get_nationwide_bigdata_context', workspace.missing_required_reads())


class RepairFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_provider_receives_repair_instructions_and_all_findings(self):
        evidence = pack(False)
        issues = candidate_delivery_issues(evidence, evidence['transfer_assessment'])
        with patch('ai_server.app.agents.transferability_agent.create_structured_response',
                   new_callable=AsyncMock, return_value={}) as generate:
            await TransferabilityAgent(api_key='', model='unused').assess(
                evidence_pack=evidence, revision_feedback=issues)
        sent = generate.call_args.kwargs
        self.assertIn('이번 호출은 후보 보완입니다', sent['instructions'])
        self.assertEqual(sent['input_payload']['quality_review_feedback']['issues'], issues)
        self.assertEqual(sent['input_payload']['transfer_assessment'], evidence['transfer_assessment'])

    async def test_repair_feedback_is_visible_in_local_tools_without_dropping_previous_comparison(self):
        router = SimpleNamespace(generate=AsyncMock(return_value={}))
        evidence = pack(False)
        issues = candidate_delivery_issues(evidence, evidence['transfer_assessment'])
        await TransferabilityAgent(api_key='', model='unused', llm_router=router).assess(evidence_pack=evidence, revision_feedback=issues)
        request = router.generate.call_args.args[0]
        tools = EvidenceTools(request.input_payload, task='transferability')
        reference = tools.overview()['quality_review_feedback_reference']
        self.assertEqual(reference['path'], '/quality_review_feedback')
        self.assertEqual(reference['issue_count'], len(issues))
        self.assertEqual(tools.pack['transfer_assessment'], evidence['transfer_assessment'])
        self.assertEqual(request.task, 'transferability')
        self.assertEqual(request.local_max_output_tokens, 8000)

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
        self.assertTrue(result['planning_decision']['automatic_corrections'])
        self.assertFalse(result['quality_review']['approved'])
        self.assertNotIn(True, final_flags)
        self.assertTrue(result['quality_review']['completion_checklist'])

    async def test_repair_still_insufficient_does_not_loop_or_force_ready(self):
        result, calls, final_flags = await self.run_flow(repair_valid=False)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['planning_decision']['selection_status'], 'needs_evidence')
        self.assertFalse(result['quality_review']['approved'])
        self.assertNotIn(True, final_flags)


if __name__ == '__main__':
    unittest.main()
