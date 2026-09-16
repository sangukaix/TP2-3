"""실측 오류의 작성 입력/보정 검증. 모델·SQL·웹 호출 없이 실행한다."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from ai_server.app.agents.planner_agent import PlannerAgent
from ai_server.app.agents.planning_requirements import (
    candidate_delivery_issues, execution_delivery_issues, stabilize_candidate_decision,
    uses_merchant_count_for_visitor_payout, has_placeholder_rate,
    measurement_missing,
)
from ai_server.app.llm.context_tables import decode_tables
from ai_server.test_planning_requirements import pack, transfer
from ai_server import test_local_agent_tools as local_fixtures

request = local_fixtures.request
required_calls = local_fixtures.required_calls


class OperationFallbackTest(unittest.TestCase):
    def test_real_bupyeong_roles_are_recognized_without_inventing_an_actor(self):
        for task, missing in (
            ('안전 관리자가 야간 보행 동선을 점검함', False),
            ('기획팀이 원장을 분석하여 종료 보고함', False),
            ('안전 관리자 확보 및 기획팀 구성 검토', True),
        ):
            strategy = {'implementation_steps': [{'task': task, 'deliverable': '보고서'}]}
            with self.subTest(task=task):
                self.assertEqual(any('.task' in r['field'] for r in execution_delivery_issues(strategy, 's')), missing)

    def test_unsupported_stop_rule_is_replaced_not_relabelled_as_an_assumption(self):
        original = transfer(False)
        candidate = original['design_candidates'][0]
        rule = '야간 체류 시간이 10% 증가하거나 5% 감소할 경우 중단함'
        candidate['stop_or_scale_rule'] = rule
        case_id = candidate['case_source_ids'][0]
        original['candidate_assessments'] = [{'case_source_id': case_id, 'validation_plan': rule}]
        before = deepcopy(original)
        result, corrections = stabilize_candidate_decision(pack(), original)
        self.assertEqual(original, before)
        self.assertNotIn('10%', result['design_candidates'][0]['stop_or_scale_rule'])
        self.assertEqual(result['candidate_assessments'][0]['validation_plan'], result['design_candidates'][0]['stop_or_scale_rule'])
        self.assertEqual(result['candidate_assessments'][0]['original_validation_plan'], rule)
        self.assertTrue(any(r.get('original_value') == rule for r in corrections))
        candidate['stop_or_scale_rule'] = '가정 목표안: 완료율 10% 이상이면 확대 검토'
        result, _ = stabilize_candidate_decision(pack(), original)
        self.assertEqual(result['design_candidates'][0]['stop_or_scale_rule'], candidate['stop_or_scale_rule'])

    def test_monthly_period_and_role_in_deliverable_are_not_missing(self):
        self.assertNotIn('확인 주기', measurement_missing('측정주기: 월간'))
        self.assertIn('확인 주기', measurement_missing('측정주기: 정기적으로'))
        strategy = {'implementation_steps': [{'task': '성과 분석 및 정산', 'deliverable': '결과 보고서 | 담당: 운영 사무국'}]}
        self.assertFalse(any('.task' in r['field'] for r in execution_delivery_issues(strategy, 'strategies[1]')))
        strategy['implementation_steps'][0]['deliverable'] = '결과 보고서'
        self.assertTrue(any('.task' in r['field'] for r in execution_delivery_issues(strategy, 'strategies[1]')))
        strategy['implementation_steps'][0]['task'] = '운영 인력이 인증 기록을 관리하고 자격 요건을 충족한 참여자에게 혜택을 지급함'
        self.assertFalse(any('.task' in r['field'] for r in execution_delivery_issues(strategy, 'strategies[1]')))
        strategy['implementation_steps'][0]['task'] = '운영 인력 확보 및 참여자 모집'
        self.assertTrue(any('.task' in r['field'] for r in execution_delivery_issues(strategy, 'strategies[1]')))

    def test_relinked_citations_need_semantic_recomparison_not_automatic_quality_pass(self):
        original = transfer()
        original['design_candidates'][0]['case_linkage'] = {
            'original_case_source_ids': ['case:1', 'case:unrelated'],
            'matched_source_ids': ['case:1'],
        }
        findings = candidate_delivery_issues(pack(), original)
        self.assertIn('planning_decision.design_candidates[1].case_linkage', {r['field'] for r in findings})
        corrected, _ = stabilize_candidate_decision(pack(), original)
        self.assertTrue(any(r['field'].endswith('.case_linkage') for r in candidate_delivery_issues(pack(), corrected)))
        # 새 비교가 올바른 인용만 반환하면 이전 감사본을 새 비교 결과에 강제 이월하지 않는다.
        original['design_candidates'][0].pop('case_linkage')
        self.assertFalse(any(r['field'].endswith('.case_linkage') for r in candidate_delivery_issues(pack(), original)))

    def repaired(self, mechanism, kind='spend_conversion'):
        original = transfer(False)
        original['design_candidates'][0].update(mechanism=mechanism, candidate_type=kind)
        before = deepcopy(original)
        result, corrections = stabilize_candidate_decision(pack(), original)
        self.assertEqual(original, before)
        self.assertEqual(result['selection_status'], 'needs_evidence')
        self.assertTrue(corrections)
        return result

    def test_stamp_coupon_uses_issued_coupons_not_refunded_money_or_merchants(self):
        result = self.repaired('GPS 스탬프 투어 완주자에게 소비쿠폰 지급')
        selected = result['design_candidates'][0]
        self.assertIn('분모=적격 지급 쿠폰 ID 수', selected['measurement_plan'])
        self.assertIn('같은 지급 코호트와 유효기간', selected['measurement_plan'])
        self.assertNotIn('환급', selected['measurement_plan'])
        self.assertIn('적격 지급 건수×건별 쿠폰 액면가', selected['budget_formula'])
        self.assertEqual(result['strategy_brief']['budget_formula'], selected['budget_formula'])
        # 숫자 없는 변수식으로 두며 다른 도시의 11개 시장/8코스/5천원을 만들지 않는다.
        self.assertNotIn('5,000', selected['budget_formula'])

    def test_refund_keeps_per_claim_cap_and_money_denominator(self):
        selected = self.repaired('여행비 일부를 상품권으로 환급')['design_candidates'][0]
        self.assertIn('min(', selected['budget_formula'])
        self.assertIn('분모=지급한 환급액 합계', selected['measurement_plan'])

    def test_measurement_comparison_separates_operating_cohorts_and_sales(self):
        result = self.repaired('GPS 스탬프 투어 완주자에게 소비쿠폰 지급')
        plan = result['design_candidates'][0]['measurement_plan']
        self.assertIn('각각 자기 집단의 분모', plan)
        self.assertIn('미운영 집단에는 승인·발급 분모가 없으므로', plan)
        self.assertIn('매출 비교는 별도 지표', plan)
        self.assertIn('취소 제외 결제액', plan)
        self.assertNotIn('미운영 집단과 동일 분모로 비교한다', plan)
        self.assertEqual(result['strategy_brief']['success_metrics'], plan)

    def test_exact_legacy_server_guidance_is_repaired_without_mutating_source(self):
        original = transfer()
        original['design_candidates'][0]['measurement_plan'] += (
            ' 같은 콘텐츠·기간의 순차 도입 미운영 집단과 동일 분모로 비교한다. ')
        before = deepcopy(original)
        result, corrections = stabilize_candidate_decision(pack(), original)
        self.assertEqual(original, before)
        self.assertTrue(any(r['field'].endswith('.measurement_plan') for r in corrections))
        self.assertNotIn('미운영 집단과 동일 분모로 비교한다',
                         result['design_candidates'][0]['measurement_plan'])

    def test_night_program_is_not_overnight_conversion_despite_model_enum(self):
        selected = self.repaired('야간 공연을 운영한다', 'stay_conversion')['design_candidates'][0]
        self.assertIn('야간 프로그램 이용 완료율', selected['measurement_plan'])
        self.assertNotIn('숙박 전환율', selected['measurement_plan'])

    def test_unknown_consumption_operation_does_not_invent_refund(self):
        selected = self.repaired('기존 상권 이용을 돕는다')['design_candidates'][0]
        self.assertIn('유효 참여완료율', selected['measurement_plan'])
        self.assertNotIn('환급', selected['measurement_plan'])

    def test_valid_plan_is_preserved(self):
        original = transfer()
        result, corrections = stabilize_candidate_decision(pack(), original)
        self.assertEqual(result, original)
        self.assertEqual(corrections, [])

    def test_visitor_payout_wrong_unit_gets_actionable_feedback_and_candidate_repair(self):
        wrong = '기획 가정: [참여 업체 수 × 건별 지급 단가(5,000원)] + [시스템 운영 및 홍보비]'
        self.assertTrue(uses_merchant_count_for_visitor_payout(wrong))
        self.assertFalse(uses_merchant_count_for_visitor_payout('참여 업체 수×업체 준비비 + 적격 지급 건수×건별 지급 단가'))
        original = transfer()
        original['design_candidates'][0].update(mechanism='완주자에게 쿠폰 지급', budget_formula=wrong)
        findings = candidate_delivery_issues(pack(), original)
        self.assertTrue(any(row['field'].endswith('.payout_quantity') for row in findings))
        corrected, _ = stabilize_candidate_decision(pack(), original)
        self.assertNotIn('참여 업체 수 × 건별 지급', corrected['design_candidates'][0]['budget_formula'])
        findings = execution_delivery_issues({'budget': wrong, 'kpi': '쿠폰 사용률 00% 달성 시 유지(착수 전 확정)'}, 'strategies[1]')
        self.assertIn('strategies[1].budget.payout_quantity', {row['field'] for row in findings})
        self.assertIn('strategies[1].kpi.placeholder', {row['field'] for row in findings})
        for valid in ('0%', '10%', '100%', '0.00%'):
            self.assertFalse(has_placeholder_rate(valid))


class PlannerHandoffTest(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_findings_reach_first_draft_and_revision_without_input_mutation(self):
        evidence = pack(False)
        findings = candidate_delivery_issues(evidence, evidence['transfer_assessment'])
        evidence['candidate_validation_findings'] = findings
        before = deepcopy(evidence)
        router = SimpleNamespace(generate=AsyncMock(return_value={}))
        agent = PlannerAgent(api_key='', model='', report_schema=request().schema, llm_router=router)
        await agent.write(evidence)
        sent = router.generate.call_args.args[0]
        self.assertEqual(sent.task, 'planner')
        self.assertEqual(sent.input_payload['quality_review_feedback']['issues'], findings)
        self.assertEqual(sent.input_payload['quality_review_feedback']['scope'], 'candidate_handoff')
        await agent.write(evidence, revision_feedback={'issues': findings[:1]}, previous_draft={'summary': '기존 초안'})
        sent = router.generate.call_args.args[0]
        self.assertEqual(sent.task, 'planner_revision')
        self.assertEqual(sent.input_payload['quality_review_feedback']['issues'], findings)
        self.assertEqual(sent.input_payload['evidence_pack']['candidate_validation_findings'], findings)
        self.assertEqual(evidence, before)

    async def test_real_local_message_path_delivers_initial_handoff_once_after_tools(self):
        original = request()
        evidence = original.input_payload['evidence_pack']
        findings = [{'severity': 'major', 'field': 'budget_formula', 'problem': '지급 수량 오류',
                     'revision_instruction': '적격 지급 건수와 점포 수를 구분하세요.'}]
        evidence['candidate_validation_findings'] = findings
        router = SimpleNamespace(generate=AsyncMock(return_value={}))
        await PlannerAgent(api_key='', model='', report_schema=original.schema, llm_router=router).write(evidence)
        captured = router.generate.call_args.args[0]
        provider = local_fixtures.LocalAgentRunnerTests().provider([
            required_calls(), {'role': 'assistant', 'content': '조회 완료'},
            {'role': 'assistant', 'content': '{"answer":"응답 대역"}'},
        ])
        await provider.generate(replace(captured, max_output_tokens=2000))
        messages = provider.seen[-1]['messages']
        feedbacks = [(i, row['content']) for i, row in enumerate(messages)
                     if row.get('content', '').startswith('아래는 후보 비교에서 남은 보완 항목이다.')]
        self.assertEqual(len(feedbacks), 1)
        index, text = feedbacks[0]
        self.assertGreater(index, max(i for i, row in enumerate(messages) if row['role'] == 'tool'))
        self.assertEqual(decode_tables(json.loads(text.split('\n', 1)[1]))['issues'], findings)
