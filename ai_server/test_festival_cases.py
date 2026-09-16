"""Real downloaded data + bounded pipeline contracts; no LLM or web calls."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from ai_server.app.festival_cases import load_catalog, shortlist, as_case, attach_festival_statistics
from ai_server.app.case_scope import select_case_cards
from ai_server.app.case_mechanism import case_mechanism_family
from ai_server.app.agents.case_study_agent import CaseStudyAgent
from ai_server.app.proposal_case_outcomes import source_outcome, report_outcome
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.case_recommendation import link_decision

ROOT=Path(__file__).resolve().parents[1]


def snapshot(code='28237', name='인천광역시 부평구', metric='visitors'):
    return {'region_code':code,'region_name':name,'period':'202606',
            'ml_analysis':{'latest_observed_month':'202606','signals':[
                {'kind':'forecast_signal','metric':metric,'change_percent':-3}]}}


class FestivalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog,cls.status=load_catalog(ROOT,{})

    def test_real_catalog_and_arithmetic(self):
        self.assertEqual(len(self.catalog),92)
        self.assertEqual(sum(len(c['annual']) for c in self.catalog),212)
        item=next(c for c in self.catalog if c['name']=='부평풍물대축제')
        last=item['comparisons'][-1]
        self.assertEqual(last['total']['difference'],26308)
        self.assertAlmostEqual(last['total']['change_pct'],11.02,places=2)

    def test_region_specific_local_baselines_and_external_regions(self):
        for code,name,expected in [('28237','인천광역시 부평구','부평풍물대축제'),
                                  ('50110','제주특별자치도 제주시','탐라문화제'),
                                  ('51780','강원특별자치도 철원군','한탄강얼음트레킹축제')]:
            rows=shortlist(self.catalog,snapshot(code,name))
            self.assertEqual(rows[0]['name'],expected)
            self.assertTrue(all(r['region_code']!=code for r in rows[1:]))
            self.assertGreaterEqual(len({r['region_code'] for r in rows}),3)

    def test_overall_growth_cannot_hide_external_daily_decline(self):
        c=next(r for r in self.catalog if r['name']=='한탄강얼음트레킹축제')
        self.assertGreater(c['comparisons'][-1]['total']['change_pct'],0)
        self.assertLess(c['comparisons'][-1]['outside_daily']['change_pct'],0)
        self.assertNotIn(c['festival_id'],[r['festival_id'] for r in shortlist(self.catalog,snapshot(),limit=100)])

    def test_duration_correction_not_raw_total_growth(self):
        c=deepcopy(next(r for r in self.catalog if r['name']=='부평풍물대축제'))
        c['comparisons'][-1]['daily']['change_pct']=-1
        self.assertEqual(shortlist([c],snapshot('50110','제주특별자치도 제주시')),[])

    def test_peers_and_ml_directions_change_order_without_modifying_source(self):
        s=snapshot('50110','제주특별자치도 제주시','spending_krw')
        s['nationwide_comparison']={'available':True,'peer_regions':[{'region_code':'44760'}]}
        original=deepcopy(self.catalog)
        rows=shortlist(self.catalog,s)
        self.assertTrue(any('소비 전망 조사: 상품·상권 연계 주제' in r['retrieval_basis']['components'] for r in rows))
        self.assertEqual(original,self.catalog)

    def test_future_years_are_not_used(self):
        s=snapshot();s['ml_analysis']['latest_observed_month']='202312'
        rows=shortlist(self.catalog,s)
        self.assertTrue(all(r['annual'][-1]['year']<=2023 for r in rows))

    def test_homepage_does_not_collapse_distinct_tables(self):
        cards=[as_case(r,self.status['dataset_hash']) for r in shortlist(self.catalog,snapshot())]
        selected,_=select_case_cards(cards,snapshot(),mechanism_key=case_mechanism_family)
        self.assertEqual(len(selected),len(cards))
        self.assertEqual(len({c['source_url'] for c in cards}),1)

    def test_exact_document_link_keeps_csv_provenance(self):
        card=as_case(shortlist(self.catalog,snapshot())[0],self.status['dataset_hash'])
        document={**card,'source_id':'case:official','source_url':'https://www.icbp.go.kr/example',
                  'retrieval_method':'official_web_search','operating_model':'공식 공연 운영 문서'}
        result=attach_festival_statistics([card,document])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['source_id'],'case:official')
        self.assertEqual(result[0]['festival_statistics']['source_file']['sha256'],card['festival_statistics']['source_file']['sha256'])
        document['case_region']='서울특별시 중구'
        self.assertEqual(len(attach_festival_statistics([card,document])),2)

    def test_no_participation_rate_or_money_invented(self):
        card=as_case(shortlist(self.catalog,snapshot())[0],self.status['dataset_hash'])
        self.assertEqual(card['operating_statistics'],[])
        self.assertIn('연도 열 없음',card['festival_statistics']['audience_period'])
        self.assertIn('변환 금지',card['festival_statistics']['indicator_rule'])

    def test_case_scout_tools_and_export_keep_the_same_source(self):
        agent=CaseStudyAgent(project_root=ROOT,env_values={'ENABLE_CASE_STUDY_WEB_RESEARCH':'false'})
        with patch('ai_server.app.agents.case_study_agent.OfficialTourismRagStore.search',new=AsyncMock(return_value=[])):
            pack=asyncio.run(agent.collect(region_code='28237',snapshot=snapshot()))
        festivals=[c for c in pack['benchmark_cases'] if c.get('festival_statistics')]
        self.assertGreaterEqual(len(festivals),3)
        source=next(c for c in pack['sources'] if c.get('festival_statistics') and c['case_region']=='인천광역시 부평구')
        workspace=EvidenceTools({'benchmark_cases':pack['benchmark_cases'],'sources':pack['sources'],
                                 'case_research_plan':pack['case_research_plan']},task='transferability')
        self.assertIn(source['source_id'],workspace.sources)
        self.assertIn('festival_candidates',workspace._case_matrix()['research_plan'])
        decision={'selected_candidate_id':'one','design_candidates':[{'candidate_id':'one','mechanism':'지역 문화 체험 축제',
                   'case_source_ids':[source['source_id']]}]}
        linked=link_decision(decision,pack['sources'])
        report={'evidence_sources':pack['sources'],'planning_decision':linked,
                'strategies':[{'solution':'지역 문화 체험 축제'}]}
        outcome=report_outcome(report)
        self.assertEqual((outcome['before'],outcome['after']),(238798,265106))
        self.assertIn('부평풍물',outcome['title'])

    def test_negative_local_comparison_is_preserved(self):
        card=as_case(shortlist(self.catalog,snapshot('50110','제주특별자치도 제주시'))[0],self.status['dataset_hash'])
        outcome=source_outcome(card)
        self.assertLess(outcome['after'],outcome['before'])

    def test_no_data_and_bad_cache_do_not_fabricate_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_catalog(Path(tmp),{})[0],[])
            target=Path(tmp)/'data/processed/festival_cases';target.mkdir(parents=True)
            (target/'summary.json').write_text(json.dumps({'dataset_hash':'bad','festival_count':1}))
            (target/'catalog.json').write_text('{"festivals":[]}')
            rows,status=load_catalog(Path(tmp),{})
            self.assertEqual(rows,[])
            self.assertEqual(status['error'],'snapshot_hash_mismatch')
            (target/'catalog.json').unlink()
            self.assertEqual(load_catalog(Path(tmp),{})[1]['error'],'invalid_snapshot')
            (target/'summary.json').write_text('{')
            self.assertEqual(load_catalog(Path(tmp),{})[1]['error'],'invalid_summary')


if __name__=='__main__':
    unittest.main()
