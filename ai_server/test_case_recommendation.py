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


class AgentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_budget_filtered_before_model_and_result_linked_after_model(self):
        router=AsyncMock();router.generate.return_value=decision()
        agent=TransferabilityAgent(api_key='',model='',llm_router=router)
        result=await agent.assess(evidence_pack={'benchmark_cases':sources()})
        request=router.generate.call_args.args[0]
        self.assertNotIn('case:budget',str(request.input_payload['benchmark_cases']))
        self.assertEqual(result['recommended_case_ids'],['case:refund'])
