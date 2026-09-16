"""Parent/district boundaries, same-period math, optional failures and tool handoff."""
import asyncio
import csv
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from ai_server.app.provincial_context_store import compare_observations, load_provincial_context
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.agents.evidence_agent import EvidenceAgent
from ai_server.app.agents.planner_agent import _build_revision_evidence_pack
from data_pipeline.tools.build_provincial_context import build, OUTPUT


def fixture():
    rows = []
    for month, visitor, spend, rate, nights in [('202506', 200, 2000, 20, 2), ('202606', 220, 2400, 22, 2.5)]:
        for metric, value in [('visitors', visitor), ('spending_krw', spend), ('lodging_rate_pct', rate), ('lodging_nights', nights)]:
            rows.append(dict(province_code='51', province_name='강원특별자치도', year_month=month,
                metric_name=metric, metric_value=value, source_id='province:sample',
                source_sha256='abc', source_file='sample.zip', source_member='sample.csv'))
    history = [dict(year_month='202506', visitors=100, spending_krw=1000),
               dict(year_month='202606', visitors=90, spending_krw=1100, lodging_rate_pct=10, lodging_nights=2)]
    return history, rows


class ProvinceContextTest(unittest.TestCase):
    def test_same_month_differences_and_source_preserved(self):
        history, rows = fixture()
        context = compare_observations('51130', '강원특별자치도', history, rows)
        values = {r['metric']: r for r in context['comparisons']}
        self.assertEqual(values['visitors']['district_value'], -10)
        self.assertEqual(values['visitors']['province_value'], 10)
        self.assertEqual(values['visitors']['gap'], -20)
        self.assertEqual(values['spending_krw']['gap'], -10)
        self.assertEqual(values['lodging_rate_pct']['gap'], -12)
        self.assertTrue(context['source_records'][0]['source_files'])

    def test_missing_latest_never_silently_uses_old_period(self):
        history, rows = fixture()
        history.append(dict(year_month='202607', visitors=95, spending_krw=1200))
        self.assertFalse(compare_observations('51130', '강원특별자치도', history, rows)['available'])
        self.assertFalse(compare_observations('11', '서울특별시', history, rows)['available'])
        self.assertFalse(compare_observations('30170', '대전광역시', history, rows)['available'])

    def test_zero_or_missing_baseline_omits_growth(self):
        history, rows = fixture()
        history[0]['visitors'] = 0
        del history[0]['spending_krw']
        context = compare_observations('51130', '강원특별자치도', history, rows)
        self.assertEqual({r['metric'] for r in context['comparisons']}, {'lodging_rate_pct', 'lodging_nights'})

    def test_optional_database_failure_does_not_break_generation(self):
        history, _ = fixture()
        with patch('ai_server.app.provincial_context_store._connect', side_effect=RuntimeError('db unavailable')):
            self.assertFalse(load_provincial_context('51130', history, {})['available'])

    def test_existing_metrics_tool_carries_context_without_changing_ml(self):
        history, rows = fixture()
        context = compare_observations('51130', '강원특별자치도', history, rows)
        payload = {'snapshot': {'provincial_context': context, 'ml_analysis': {'status': 'available', 'forecasts': [123]}},
                   'sources': context['source_records']}
        before = deepcopy(payload)
        tool = EvidenceTools(payload, task='planner')
        self.assertEqual(tool.execute('get_region_metrics', {})['provincial_context'], context)
        self.assertEqual(payload, before)

    def test_evidence_and_revision_keep_parent_source_without_network(self):
        history, rows = fixture()
        context = compare_observations('51130', '강원특별자치도', history, rows)
        snapshot = {'region_name': '강원특별자치도 원주시', 'period': '2026-06',
                    'provincial_context': context, 'observations': []}
        with patch('ai_server.app.agents.evidence_agent.OfficialTourismRagStore.search', new=AsyncMock(return_value=[])):
            pack = asyncio.run(EvidenceAgent(project_root=Path(__file__).resolve().parents[1], env_values={}).collect(
                region_code='51130', snapshot=snapshot))
        self.assertIn(context['source_id'], [r['source_id'] for r in pack['sources']])
        revision = _build_revision_evidence_pack(pack, {})
        self.assertIn(context['source_id'], [r['source_id'] for r in revision['sources']])

    def test_real_snapshot_build_units_scope_and_reproducibility(self):
        with TemporaryDirectory() as folder:
            summary = build(output=Path(folder))
            self.assertEqual((summary['province_count'], summary['row_count']), (15, 1800))
            with (Path(folder) / 'monthly_context.csv').open(encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            seoul = {r['metric_name']: r for r in rows if r['province_code'] == '11' and r['year_month'] == '202606'}
            self.assertEqual(float(seoul['visitors']['metric_value']), 43301695)
            self.assertEqual(float(seoul['spending_krw']['metric_value']), 3737108405000)
            self.assertEqual(len({(r['province_code'], r['year_month'], r['metric_name']) for r in rows}), 1800)
            self.assertEqual((Path(folder) / 'monthly_context.csv').read_bytes(), (OUTPUT / 'monthly_context.csv').read_bytes())


if __name__ == '__main__':
    unittest.main()
