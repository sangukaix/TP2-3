"""전국 사례 탐색·전달 계약. 외부 LLM/검색/임베딩/DB 없이 검증한다."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from ai_server.app.case_scope import build_case_search_policy, case_relation, select_case_cards, nationwide_case_query
from ai_server.app.agents.case_study_agent import CaseStudyAgent, _case_mechanism_family, _load_curated_case_cards
from ai_server.app.agents.planner_agent import _build_revision_evidence_pack
from ai_server.app.agents.transferability_agent import TransferabilityAgent
from ai_server.app.llm.evidence_tools import EvidenceTools, compact_json
from ai_server.app.llm.local_agent import _prefetch_required_evidence
from ai_server.app.rag_store import OfficialTourismRagStore


def snapshot():
    return {'region_name': '강원특별자치도 원주시', 'period': '2025-07 ~ 2026-06',
            'nationwide_comparison': {'available': True, 'period': '2025-07 ~ 2026-06',
                                     'peer_regions': [{'region_code': '41150', 'region_name': '경기도 의정부시', 'rank': 1}]}}


def card(key, region, mechanism='예약 재고 운영'):
    return {'source_id': key, 'source_url': 'https://visitkorea.or.kr/' + key,
            'case_region': region, 'source_title': region + ' 공식 운영 사례',
            'operating_model': mechanism, 'intervention': mechanism, 'problem_addressed': '방문 전환',
            'evidence_strength': 'medium', 'observed_result': '공식 확인 필요',
            'measurement_period': '2025', 'published_or_updated_at': '2025-12-01'}


class CaseScopeTests(unittest.TestCase):
    def test_unverified_case_numbers_stay_in_audit_not_generation_card(self):
        root = Path(__file__).resolve().parents[1]
        records = [json.loads(line) for line in (root / 'data/rag/official_case_studies.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        record = next(row for row in records if row['source_id'] == 'case:gangjin_half_price_2024')
        self.assertIn('46', json.dumps(record['historical_unverified_claim'], ensure_ascii=False))
        cards = _load_curated_case_cards(root, ['jeonnam.go.kr'])
        current = next(row for row in cards if row['source_id'] == record['source_id'])
        self.assertFalse(current['quantitative_result_approved'])
        self.assertNotIn('historical_unverified_claim', current)
        self.assertNotIn('46%', json.dumps(current, ensure_ascii=False))

    def test_same_province_accepts_official_name_alias(self):
        self.assertEqual(case_relation(card('a', '강원도 춘천시'), snapshot())['scope'], 'same_province')

    def test_cross_province_peer_is_not_same_province_or_population_match(self):
        relation = case_relation(card('a', '경기도 의정부시'), snapshot())
        self.assertEqual(relation, {'scope': 'cross_province_peer', 'peer_region_code': '41150'})
        self.assertEqual(build_case_search_policy(snapshot())['resident_population_comparison'],
                         'not_available_in_current_peer_features')

    def test_same_district_name_does_not_join_unrelated_regions(self):
        data = {'region_name': '서울특별시 중구'}
        self.assertEqual(case_relation(card('a', '대구광역시 중구'), data)['scope'], 'cross_province')
        self.assertEqual(case_relation(card('a', '중구'), data)['scope'], 'national_or_unresolved')

    def test_unavailable_comparison_cannot_be_used_as_verified_peer(self):
        data = snapshot()
        data['nationwide_comparison']['available'] = False
        self.assertIsNone(case_relation(card('a', '경기도 의정부시'), data)['peer_region_code'])

    def test_rag_all_code_does_not_turn_gangjin_into_national_program(self):
        item = {**card('a', '전라남도 강진군'), 'region_code': 'ALL'}
        self.assertEqual(case_relation(item, snapshot())['scope'], 'cross_province')

    def test_many_local_cases_do_not_exclude_cross_province_peer(self):
        rows = [card('local' + str(i), '강원도 춘천시') for i in range(10)]
        rows += [card('peer', '경기도 의정부시'), card('seoul', '서울특별시 종로구', '교통 접근 운영')]
        original = deepcopy(rows)
        chosen, coverage = select_case_cards(rows, snapshot(), mechanism_key=_case_mechanism_family)
        self.assertEqual(len(chosen), 8)
        self.assertTrue({'peer', 'seoul'} <= {row['source_id'] for row in chosen})
        self.assertEqual(coverage['excluded_candidates'], 4)
        self.assertEqual(rows, original)

    def test_sparse_local_catalog_still_uses_nationwide_cards(self):
        rows = [card('outside', '전남 강진군'), card('national', '전국 참여지역')]
        selected, coverage = select_case_cards(rows, snapshot(), mechanism_key=_case_mechanism_family)
        self.assertEqual(len(selected), 2)
        self.assertNotIn('same_province', coverage['scope_counts'])

    def test_national_query_does_not_repeat_selected_province_as_filter(self):
        query = nationwide_case_query(snapshot())
        self.assertIn('전국', query)
        self.assertIn('경기도 의정부시', query)
        self.assertNotIn('원주시', query)

    def test_prefetch_keeps_two_mechanisms_and_reads_outside_case(self):
        rows = [card('local1', '강원도 춘천시'), card('local2', '강원도 강릉시', '체크인 숙박 운영'),
                card('outside', '경기도 의정부시', '교통 접근 운영')]
        for row in rows:
            row['retrieval_context'] = case_relation(row, snapshot())
        workspace = EvidenceTools({'snapshot': snapshot(), 'benchmark_cases': rows}, task='transferability')
        _prefetch_required_evidence(workspace, 'transferability')
        self.assertEqual(set(workspace.read_case_source_ids()), {'local1', 'outside'})
        self.assertEqual(workspace.missing_required_reads(), [])

    def test_revision_preserves_case_scope(self):
        pack = {'case_search_policy': build_case_search_policy(snapshot()), 'case_search_coverage': {'selected_candidates': 2}}
        revised = _build_revision_evidence_pack(pack, {})
        self.assertEqual(revised['case_search_policy'], pack['case_search_policy'])


class NationwideRagTests(unittest.IsolatedAsyncioTestCase):
    def make_store(self, path):
        store = OfficialTourismRagStore(persist_directory=path / 'chroma', api_key='unused',
                                       embedding_model='unused', allowed_domains=['visitkorea.or.kr'],
                                       local_reference_path=path / 'references.jsonl')
        metadata = [
            {'region_code': '51130', 'document_type': 'policy', 'source_id': 'local'},
            {'region_code': '46810', 'document_type': 'case_study', 'source_id': 'outside'},
            {'region_code': '11110', 'document_type': 'tourism_page', 'source_id': 'other_place'},
            {'region_code': '11110', 'document_type': 'policy', 'source_id': 'other_policy'},
            {'region_code': 'ALL', 'document_type': 'data_definition', 'source_id': 'common'},
        ]
        for row in metadata:
            row['source_url'] = 'https://visitkorea.or.kr/' + row['source_id']
        store._collection = lambda: SimpleNamespace(count=lambda: len(metadata),
            get=lambda **_: {'metadatas': metadata, 'documents': ['관광 예약 운영'] * len(metadata)})
        store._embeddings = AsyncMock(side_effect=AssertionError('no paid embeddings'))
        return store, metadata

    async def test_case_scope_expands_only_case_documents_local_stays_strict(self):
        with TemporaryDirectory() as tmp:
            store, _ = self.make_store(Path(tmp))
            args = dict(query='관광 예약', region_code='51130', region_name='강원특별자치도 원주시', local_only=True)
            local = await store.search(**args)
            national = await store.search(**args, nationwide_cases=True)
            self.assertEqual({x['source_id'] for x in local}, {'local', 'common'})
            self.assertEqual({x['source_id'] for x in national}, {'local', 'common', 'outside'})
            store._embeddings.assert_not_awaited()

    async def test_local_jsonl_accepts_other_case_but_not_unapproved_or_policy(self):
        with TemporaryDirectory() as tmp:
            store, metadata = self.make_store(Path(tmp))
            records = [{**row, 'content': '관광 예약 운영'} for row in metadata]
            records.append({**records[1], 'source_id': 'unapproved', 'approved_for_rag': False})
            store.local_reference_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in records), encoding='utf-8')
            store._collection = lambda: SimpleNamespace(count=lambda: 0)
            results = await store.search(query='관광 예약', region_code='51130', region_name='원주시', local_only=True, nationwide_cases=True)
            self.assertEqual({x['source_id'] for x in results}, {'local', 'common', 'outside'})
            self.assertEqual(next(x for x in results if x['source_id'] == 'outside')['region_code'], '46810')

    async def test_semantic_query_filters_before_top_k_and_preserves_region(self):
        with TemporaryDirectory() as tmp:
            store, metadata = self.make_store(Path(tmp))
            seen = {}
            def query(**kwargs):
                seen.update(kwargs)
                return {'metadatas': [metadata], 'documents': [['관광 예약 운영'] * len(metadata)], 'distances': [[0.1] * len(metadata)]}
            store._collection = lambda: SimpleNamespace(count=lambda: 5, query=query)
            store._embeddings = AsyncMock(return_value=[[0.1]])
            rows = await store.search(query='관광 예약', region_code='51130', region_name='원주시', nationwide_cases=True)
            self.assertIn('where', seen)
            self.assertEqual({x['source_id'] for x in rows}, {'local', 'common', 'outside'})


class CaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_student_budget_passes_national_rag_and_scope_without_cloud(self):
        router = SimpleNamespace(student_budget=True, local_first=True, generate=AsyncMock(side_effect=AssertionError('no cloud')))
        rows = [card('outside', '전남 강진군'), card('other', '서울특별시 종로구', '교통 접근 운영')]
        rag = [{'source_id': 'rag-other', 'source_type': 'rag', 'document_type': 'case_study',
                'region_code': '41150', 'source_url': 'https://visitkorea.or.kr/rag', 'summary': '검수된 운영 문서'}]
        with patch('ai_server.app.agents.case_study_agent._load_curated_case_cards', return_value=rows), \
             patch.object(OfficialTourismRagStore, 'search', new=AsyncMock(return_value=rag)) as search:
            pack = await CaseStudyAgent(project_root=Path('.'), env_values={}, llm_router=router).collect(region_code='51130', snapshot=snapshot())
        self.assertTrue(search.call_args.kwargs['nationwide_cases'])
        self.assertIn('rag-other', {x['source_id'] for x in pack['sources']})
        self.assertEqual(pack['case_search_policy']['search_scope'], 'nationwide')
        self.assertEqual(pack['case_search_coverage']['selected_candidates'], 2)
        self.assertTrue(any('같은 시도' in gap for gap in pack['research_gaps']))
        router.generate.assert_not_awaited()
        workspace = EvidenceTools({'snapshot': snapshot(), **pack}, task='transferability')
        self.assertNotIn('error', workspace.execute('get_case_comparison_matrix', {}))
        self.assertLess(len(compact_json(workspace.overview()).encode('utf-8')), 12000)

    async def test_transfer_agent_passes_scope_to_local_or_cloud_router(self):
        router = SimpleNamespace(generate=AsyncMock(return_value={}))
        policy = build_case_search_policy(snapshot())
        pack = {'snapshot': snapshot(), 'benchmark_cases': [card('a', '전남 강진군')], 'case_search_policy': policy}
        await TransferabilityAgent(api_key='unused', model='unchanged', llm_router=router).assess(evidence_pack=pack)
        request = router.generate.call_args.args[0]
        self.assertEqual(request.input_payload['case_search_policy'], policy)

    async def test_current_card_overrides_stale_rag_version_of_same_case(self):
        router = SimpleNamespace(student_budget=True, local_first=True)
        rows = [card('case:current', '전남 강진군')]
        rows[0]['observed_result'] = '측정기간 미검증. 성과 수치 인용 보류'
        rows[0]['quantitative_result_approved'] = False
        rag = [{'source_id': 'case:current', 'source_url': rows[0]['source_url'], 'summary': '오래된 확정 성과'}]
        with patch('ai_server.app.agents.case_study_agent._load_curated_case_cards', return_value=rows), \
             patch.object(OfficialTourismRagStore, 'search', new=AsyncMock(return_value=rag)):
            result = await CaseStudyAgent(project_root=Path('.'), env_values={}, llm_router=router).collect(region_code='51130', snapshot=snapshot())
        self.assertEqual(len(result['sources']), 1)
        self.assertNotIn('오래된', result['sources'][0]['summary'])
        self.assertFalse(result['sources'][0]['quantitative_result_approved'])


if __name__ == '__main__':
    unittest.main()
