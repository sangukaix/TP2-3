import copy
import unittest
from unittest.mock import AsyncMock
from ai_server.app.case_recommendation import link_decision, match_cases
from ai_server.app.agents.transferability_agent import TransferabilityAgent


def sources():
    return [dict(source_id='case:budget', source_url='https://example.go.kr/budget',
                 intervention='야간관광 예산 편성', operating_model='사업비 편성', evidence_strength='high'),
            dict(source_id='case:refund', source_url='https://example.go.kr/refund',
                 intervention='지역 환급', operating_model='여행비를 상품권으로 환급', evidence_strength='low'),
            dict(source_id='case:stay', source_url='https://example.go.kr/stay',
                 intervention='숙박 체류상품', operating_model='숙소 식사 체험 예약', evidence_strength='medium')]


def decision():
    return {'selected_candidate_id':'a','strategy_brief':{},'design_candidates':[
        {'candidate_id':'a','mechanism':'여행비 일부를 지역상품권으로 환급',
         'case_source_ids':['case:budget'],'evidence_source_ids':['dataset:1','case:budget']}]}


class RecommendationTest(unittest.TestCase):
    def test_document_match_overrides_llm_budget_choice_without_mutating_input(self):
        before=decision();after=link_decision(before,sources())
        self.assertEqual(after['recommended_case_ids'],['case:refund'])
        self.assertEqual(after['strategy_brief']['supporting_case_ids'],['case:refund'])
        self.assertEqual(after['design_candidates'][0]['evidence_source_ids'],['dataset:1','case:refund'])
        self.assertEqual(before,decision())
        self.assertEqual(link_decision(after,sources())['case_linkage']['original_case_source_ids'],['case:budget'])

    def test_no_matching_operation_does_not_fabricate_reference(self):
        self.assertEqual(match_cases({'mechanism':'야간 공연'},sources()),[])
        source=sources()[1];source['source_url']=''
        self.assertEqual(match_cases(decision()['design_candidates'][0],[source]),[])

    def test_repeated_linking_preserves_repaired_explanation_and_audit(self):
        original = decision()
        original['design_candidates'][0].update(local_fit='잘못된 예산 사례 비교', differentiation='이전 설명')
        linked = link_decision(original, sources())
        self.assertEqual(link_decision(linked, sources()), linked)
        linked['design_candidates'][0].update(local_fit='지역 소비 관측에 근거한 새 비교', differentiation='운영 규모 차이')
        linked['selection_reason'] = '숙박안과 소비안을 비교한 장단점'
        before = copy.deepcopy(linked)
        again = link_decision(linked, sources())
        self.assertEqual(again, before)
        self.assertEqual(again['design_candidates'][0]['case_linkage']['original_local_fit'], '잘못된 예산 사례 비교')
        self.assertEqual(again['case_linkage']['original_case_source_ids'], ['case:budget'])
        self.assertEqual(linked, before)

    def test_valid_citation_and_selection_explanation_survive_linkage(self):
        original=decision()
        original['selection_reason']='숙박 결제 유도를 검토하되 참여업체 협의 부담을 대안과 비교했다.'
        original['design_candidates'][0]['case_source_ids']=['case:z_valid']
        pool=[{**sources()[1],'source_id':'case:a_other','evidence_strength':'high'}, {**sources()[1],'source_id':'case:z_valid'}]
        linked=link_decision(original,pool)
        self.assertEqual(linked['recommended_case_ids'],['case:z_valid'])
        self.assertEqual(linked['selection_reason'],original['selection_reason'])
        self.assertEqual(link_decision(linked,pool),linked)

    def test_missing_citation_uses_region_context_not_alphabetical_id(self):
        pool=[{**sources()[1],'source_id':'case:a_far','retrieval_context':{'scope':'cross_province'}}, {**sources()[1],'source_id':'case:z_local','retrieval_context':{'scope':'same_province'}}]
        self.assertEqual(link_decision(decision(),pool)['recommended_case_ids'],['case:z_local'])

    def test_auto_includes_documented_reservation_mobility_and_experience(self):
        from ai_server.app.case_recommendation import allowed_operation
        for mechanism in ['시간대 예약 입장', '시티투어 교통 연계', '공예 체험 운영']:
            candidate={'mechanism':mechanism}
            self.assertTrue(allowed_operation(candidate,{'input_profile':'guided_v2','business_direction':'auto'}))
            self.assertFalse(allowed_operation(candidate,{'input_profile':'guided_v2','business_direction':'spend_conversion'}))

    def test_extra_reference_is_not_mislabelled_as_evaluated_candidate(self):
        from ai_server.app.case_recommendation import case_reference_role
        report={'strategies':[{'solution':'여행비 환급'}], 'planning_decision':{},'evidence_sources':[{**source,'source_type':'benchmark_case'} for source in sources()]}
        self.assertEqual(case_reference_role(report,report['evidence_sources'][1]),'핵심 운영 참고')
        self.assertEqual(case_reference_role(report,report['evidence_sources'][2]),'추가 운영 참고')

    def test_export_primary_keeps_the_selected_reference(self):
        from ai_server.app.case_recommendation import report_cases
        report={'strategies':[{'solution':'여행비 환급'}], 'planning_decision':{'selected_candidate_id':'a','design_candidates':[{'candidate_id':'a','mechanism':'여행비 환급','case_source_ids':['case:z_valid']}]},'evidence_sources':[{**sources()[1],'source_id':sid,'source_type':'benchmark_case'} for sid in ['case:a_other','case:z_valid']]}
        self.assertEqual(report_cases(report)[1][0]['source_id'],'case:z_valid')


class AgentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_model_selection_failure_is_returned_for_existing_repair(self):
        router = AsyncMock()
        router.local_first = True
        raw = decision()
        raw['design_candidates'][0]['mechanism'] = '야간 공연'
        raw['design_candidates'].append({'candidate_id': 'b', 'mechanism': '숙박 체험'})
        router.generate.return_value = raw
        result = await TransferabilityAgent(api_key='', model='', llm_router=router).assess(
            evidence_pack={'benchmark_cases': sources(), 'planning_brief': {'input_profile': 'guided_v2', 'business_direction': 'auto'}})
        self.assertEqual(router.generate.await_count, 1)
        self.assertEqual(result['selected_candidate_id'], 'a')
        self.assertEqual(result['constraint_repair']['eligible_candidate_ids'], ['b'])
        self.assertEqual(result['selection_status'], 'needs_evidence')

    async def test_budget_filtered_before_model_and_result_linked_after_model(self):
        router=AsyncMock();router.generate.return_value=decision()
        agent=TransferabilityAgent(api_key='',model='',llm_router=router)
        result=await agent.assess(evidence_pack={'benchmark_cases':sources()})
        request=router.generate.call_args.args[0]
        self.assertNotIn('case:budget',str(request.input_payload['benchmark_cases']))
        self.assertEqual(result['recommended_case_ids'],['case:refund'])
