"""Document chunks must survive collection, merging, revision and local reads."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from ai_server.app.evidence_sources import merge_evidence_sources
from ai_server.app.agents.planner_agent import _build_revision_evidence_pack
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.rag_store import OfficialTourismRagStore


class EvidenceSourcesTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'source_id': 'pdf:seminar', 'chunk_id': f'pdf:seminar:p{i}',
             'title': 'Official seminar', 'page_start': i, 'page_end': i,
             'source_url': 'https://example.go.kr/seminar.pdf',
             'source_type': 'rag', 'summary': f'Exact page {i} evidence'}
            for i in range(1, 4)
        ]

    def test_merge_keeps_all_pages_and_latest_identical_chunk(self):
        original = deepcopy(self.rows)
        correction = {**self.rows[1], 'summary': 'Corrected page 2'}
        merged = merge_evidence_sources(self.rows, [correction])
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[1]['summary'], 'Corrected page 2')
        self.assertEqual(self.rows, original)
        merged[0]['summary'] = 'mutable copy'
        self.assertEqual(self.rows, original)

    def test_chunk_ids_are_scoped_by_parent_document(self):
        rows = [{**row, 'chunk_id': 'page1', 'source_id': f'pdf:{i}'}
                for i, row in enumerate(self.rows)]
        self.assertEqual(len(merge_evidence_sources(rows)), 3)

    def test_revision_keeps_every_page_of_cited_document(self):
        revised = _build_revision_evidence_pack(
            {'sources': self.rows}, {'summary': 'Read pdf:seminar for the actual evidence.'},
        )
        self.assertEqual(revised['sources'], self.rows)

    def test_chunk_pagination_preserves_evidence_and_requires_complete_read(self):
        payload = {'evidence_pack': {'sources': merge_evidence_sources(self.rows, self.rows)}}
        tools = EvidenceTools(payload)
        index = tools.execute('search_collected_sources', {})
        self.assertEqual(index['items'][0]['title'], 'Official seminar')
        self.assertEqual(index['items'][0]['chunk_count'], 3)
        self.assertEqual(tools.overview()['source_count'], 1)
        self.assertEqual(tools.overview()['source_chunk_count'], 3)
        first = tools.execute('read_collected_source', {'source_id': 'pdf:seminar'})
        self.assertEqual(first['next_offset'], 1)
        self.assertNotIn('pdf:seminar', tools.read_source_ids)
        second = tools.execute('read_collected_source', {'source_id': 'pdf:seminar', 'offset': 1, 'limit': 2})
        self.assertIsNone(second['next_offset'])
        self.assertEqual(first['chunks'] + second['chunks'], self.rows)
        self.assertIn('pdf:seminar', tools.read_source_ids)
        self.assertEqual(payload['evidence_pack']['sources'], self.rows)

    def test_invalid_and_oversized_pages_are_not_marked_read(self):
        tools = EvidenceTools({'sources': self.rows})
        result = tools.execute('read_collected_source', {'source_id': 'pdf:seminar', 'offset': 3})
        self.assertIn('error', result)
        tools.sources['pdf:seminar']['chunks'][0]['summary'] = 'x' * 13000
        result = tools.execute('read_collected_source', {'source_id': 'pdf:seminar'})
        self.assertEqual(result['error'], 'EVIDENCE_RESULT_TOO_LARGE')
        self.assertNotIn('pdf:seminar', tools.read_source_ids)


class RagChunkReadTest(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_retrieval_keeps_full_text_pages_and_chunk_identity(self):
        with TemporaryDirectory() as directory:
            store = OfficialTourismRagStore(persist_directory=Path(directory), api_key='',
                                            embedding_model='test', allowed_domains=['example.go.kr'])
            metadata = [{'source_id': 'pdf:1', 'chunk_id': f'pdf:1:p{i}',
                         'page_references': str(i), 'region_code': 'ALL',
                         'source_url': 'https://example.go.kr/doc.pdf'} for i in (1, 2)]
            documents = ['a' * 1600, 'b' * 1700]
            store._collection = lambda: SimpleNamespace(count=lambda: 2, query=lambda **kwargs: {
                'metadatas': [metadata], 'documents': [documents], 'distances': [[0.1, 0.2]],
            })
            store._embeddings = AsyncMock(return_value=[[0.1]])
            rows = await store.search(query='tourism', region_code='51130', region_name='원주시')
            self.assertEqual([row['summary'] for row in rows], documents)
            self.assertEqual([row['page_references'] for row in rows], ['1', '2'])
            self.assertEqual([row['chunk_id'] for row in rows], ['pdf:1:p1', 'pdf:1:p2'])


if __name__ == '__main__':
    unittest.main()
