import unittest
from copy import deepcopy
from ai_server.app.idea_proposal import prepare_idea_report, bounded_chat_reply


class IdeaProposalTest(unittest.TestCase):
    def report(self):
        return {'summary': '사업 제안', 'strategies': [{'title': '강진 사례 반값 환급', 'solution': '지역상품권 환급'}],
                'ml_analysis': {'status': 'available', 'forecasts': []},
                'quality_review': {'approved': False, 'issues': ['original']},
                'planning_decision': {'design_candidates': [{'candidate_id': 'a', 'title': '반값여행', 'case_source_ids': ['case:gangjin']} ]}}

    def test_defaults_preserve_facts_review_and_input(self):
        r = self.report(); before = deepcopy(r); result = prepare_idea_report(r)
        self.assertEqual(r, before)
        self.assertEqual(result['execution_scenario'], {'visitor_target_pct': 20, 'spending_target_pct': 20})
        self.assertEqual(result['ml_analysis'], r['ml_analysis'])
        self.assertEqual(result['quality_review'], r['quality_review'])
        self.assertEqual(result['target_proposal_basis']['observed_visitors'], 2480000)
        self.assertIn('사업 단독 효과', result['target_proposal_basis']['explanation'])
        e=result['reference_estimate']; self.assertEqual(sum(row['amount'] for row in e['items']),e['total_krw'])

    def test_user_goals_win_and_unrelated_case_is_not_gangjin(self):
        r=self.report();r['execution_scenario']={'visitor_target_pct': 4, 'spending_target_pct': 6}
        r['strategies']=[{'title':'문화 체험', 'solution':'체험 운영'}]
        result=prepare_idea_report(r)
        self.assertEqual(result['execution_scenario'], r['execution_scenario'])
        self.assertEqual(result['target_proposal_basis']['source_url'], '')
        self.assertEqual(result['target_proposal_basis']['spending_target_pct'],6)

    def test_scope_and_numeric_edits_do_not_need_llm(self):
        r=self.report()
        out=bounded_chat_reply(r, '63빌딩 짓는 기획서 만들어줘')
        self.assertIsNone(out['report_patch']);self.assertIn('1개',out['answer'])
        patch=bounded_chat_reply(r,'방문 목표 4%, 소비 목표 5%로 바꿔줘')['report_patch']
        self.assertEqual(patch['execution_scenario']['visitor_target_pct'],4)
        self.assertNotIn('ml_analysis',patch)
        for total in (1, 100000000):
            estimate=bounded_chat_reply(r,f'견적 총액 {total}원으로 변경')['report_patch']['reference_estimate']
            self.assertEqual(sum(row['amount'] for row in estimate['items']),total)
            self.assertTrue(all(row['amount']>=0 for row in estimate['items']))
            self.assertNotIn('quantity',estimate)

    def test_low_budget_remains_a_budget_allocation(self):
        r=self.report();r['planning_brief']={'budget_hard_limit':True,'budget_max_krw':1000000}
        e=prepare_idea_report(r)['reference_estimate']
        self.assertEqual(e['total_krw'],1000000)
        self.assertTrue(e['within_hard_budget'])
        self.assertIsNone(bounded_chat_reply(r,'견적 총액 2억원으로 변경')['report_patch'])

    def test_word_estimates_keep_won_precision(self):
        from docx import Document
        from ai_server.test_proposal_presentation_v3_contract import _sample_report
        from ai_server.app.proposal_document import create_strategy_proposal_document
        r=_sample_report(); r['strategies'][0]['title']='반값 환급'
        doc=Document(create_strategy_proposal_document(r))
        text='\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        estimate=prepare_idea_report(r)['reference_estimate']
        for item in estimate['items']:
            self.assertIn(f"{item['amount']:,}원",text)
        self.assertIn(f"{estimate['total_krw']:,}원",text)
        self.assertNotIn('₩0억',text)

if __name__ == '__main__':
    unittest.main()
