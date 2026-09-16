"""Large source/case pairs must be delivered completely before citation."""
import copy
import json
import unittest

from ai_server.app.llm.evidence_tools import EvidenceTools, compact_json
from ai_server.app.llm.local_agent import _prefetch_required_evidence
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.proposal_layout_v9 import execution_groups, period


class LargeCaseEvidenceTest(unittest.TestCase):
    def pack(self):
        card = {'source_id': 'case:festival:long', 'case_region': '문경시',
                'operating_model': '공예 체험 축제',
                'festival_statistics': {'annual': [{'year': 2025, 'visitors': 256570}],
                                        'scope': '동일 기준의 공식 통계. ' * 400},
                'retrieval_basis': {'kind': 'external_benchmark'}}
        return {'sources': [copy.deepcopy(card)], 'benchmark_cases': [card]}

    def test_all_pages_required_and_original_reconstructed(self):
        pack = self.pack()
        before = copy.deepcopy(pack)
        tools = EvidenceTools(pack)
        sid = pack['sources'][0]['source_id']
        original = {'source_id': sid, **tools.sources[sid]}
        page = tools.execute('read_collected_source', {'source_id': sid})
        self.assertNotIn(sid, tools.read_source_ids)
        with self.assertRaises(LLMProviderError):
            tools.verify_citations({'case_source_id': sid})
        pages = [page]
        while page.get('next_offset') is not None:
            page = tools.execute('read_collected_source', {'source_id': sid, 'offset': page['next_offset']})
            pages.append(page)
        self.assertEqual(json.loads(''.join(p['serialized_json_segment'] for p in pages)), original)
        self.assertTrue(all(len(compact_json(p).encode('utf-8')) <= 12000 for p in pages))
        tools.verify_citations({'case_source_id': sid})
        self.assertEqual(pack, before)
        invalid = tools.execute('read_collected_source', {'source_id': sid, 'offset': len(pages)})
        self.assertIn('error', invalid)

    def test_prefetch_reads_large_festival_and_all_pdf_chunks(self):
        pack = self.pack()
        pack['sources'].extend([{'source_id': 'case:festival:long', 'chunk_id': f'chunk:{i}',
                                'summary': '원문' * 2500} for i in range(2)])
        tools = EvidenceTools(pack, task='transferability')
        pages = _prefetch_required_evidence(tools, 'transferability')
        reads = [p['result'] for p in pages if p['tool'] == 'read_collected_source']
        self.assertTrue(reads)
        self.assertFalse(any('error' in p for p in reads))
        self.assertIn('case:festival:long', tools.read_source_ids)
        self.assertEqual(json.loads(''.join(p['serialized_json_segment'] for p in reads))['chunks'],
                         tools.sources['case:festival:long']['chunks'])

    def test_two_evaluation_steps_do_not_move_launch_month(self):
        steps = [{'task': task, 'schedule': month} for task, month in [
            ('참여 업체 및 환급 기준 확정', '2026-10'),
            ('증빙 및 환급 시스템 점검', '2026-10'),
            ('시범 운영 및 모니터링', '2026-11'),
            ('성과 데이터 수집 및 분석', '2026-12'),
            ('사업 지속 여부 검토', '2026-12')]]
        groups = execution_groups({'strategies': [{'implementation_steps': steps}]})
        self.assertEqual([s for group in groups for s in group], steps)
        self.assertEqual(period(groups[1]), '2026-10')
        self.assertEqual(period(groups[2]), '2026-11')
        self.assertEqual(period(groups[3]), '2026-12')


if __name__ == '__main__':
    unittest.main()
