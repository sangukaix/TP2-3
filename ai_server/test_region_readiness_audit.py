import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from ai_server.app.region_readiness_audit import read_audit

class AuditTest(unittest.TestCase):
    def inspect(self, *, files='files', sql='sql', fresh=True, days=30, ready=True):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'audit.json'
            payload={'checked_at':(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(),
                     'regions':[{'region_code':'43114','verified':False,'data_ready':ready,
                                 'input_signature':'files','sql_signature':'sql',
                                 'details':{'latest_observed_month':'202606'}}],'status':'completed'}
            p.write_text(json.dumps(payload))
            with patch('ai_server.app.region_readiness_audit.AUDIT_PATH',p), \
                 patch('ai_server.ml.region_catalog.list_region_data_catalog',return_value=[SimpleNamespace(region_code='43114')]), \
                 patch('ai_server.app.region_readiness_audit.file_signature',return_value=files), \
                 patch('ai_server.app.region_readiness_audit.sql_signatures',return_value={'43114':sql} if sql else {},side_effect=ConnectionError() if sql=='offline' else None), \
                 patch('ai_server.ml.data_freshness.assess_data_freshness',return_value=SimpleNamespace(can_generate=fresh)):
                return read_audit()['regions'][0]

    def test_unchanged_data_does_not_expire_after_a_day(self):
        self.assertTrue(self.inspect(days=30)['data_ready'])
        self.assertFalse(self.inspect(ready=False)['data_ready'])

    def test_actual_changes_block_until_reviewed(self):
        for kwargs in ({'files':'changed'}, {'sql':'changed'}, {'sql':None}, {'sql':'offline'}, {'fresh':False}):
            with self.subTest(kwargs=kwargs):
                row=self.inspect(**kwargs)
                self.assertFalse(row['data_ready'])
                self.assertTrue(row['readiness_reason'])

    def test_missing_audit_is_not_green(self):
        with patch('ai_server.app.region_readiness_audit.AUDIT_PATH',Path('not-an-audit.json')):
            self.assertEqual(read_audit()['regions'],[])

    def test_file_replacement_or_deletion_changes_signature(self):
        from dataclasses import dataclass
        from ai_server.app.region_readiness_audit import file_signature
        @dataclass
        class Entry:
            region_code: str
            raw_path: Path
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); raw=root/'raw'; raw.mkdir()
            f=raw/'data.csv'; f.write_text('123')
            with patch('ai_server.app.region_readiness_audit.ROOT',root):
                entry=Entry('43114',raw); before=file_signature(entry)
                f.write_text('new-data')
                self.assertNotEqual(before,file_signature(entry))
                before=file_signature(entry); f.unlink()
                self.assertNotEqual(before,file_signature(entry))
if __name__=='__main__':unittest.main()


class RuntimeReadinessTest(unittest.IsolatedAsyncioTestCase):
    async def test_green_requires_data_and_installed_local_models(self):
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        from ai_server.app.main import read_regions_readiness_audit
        from ai_server.app.llm.models import ProviderHealth
        q=AsyncMock(return_value=ProviderHealth('ollama','active','ok',['q']))
        g=AsyncMock(return_value=ProviderHealth('ollama','active','ok',['g']))
        router=SimpleNamespace(providers={'qwen':SimpleNamespace(health=q),'gemma':SimpleNamespace(health=g)},
            effective_routes=lambda:{'transferability':{'provider':'qwen','model':'q'},'planner':{'provider':'gemma','model':'g'}})
        audit={'checked_at':'now','status':'completed','regions':[
            {'region_code':'11620','region_name':'관악구','verified':False,'data_ready':True,'issues':[]},
            {'region_code':'unknown','region_name':'미준비','verified':False,'data_ready':False,'issues':[]}]}
        with patch('ai_server.app.main._llm_router',return_value=router),patch('ai_server.app.region_readiness_audit.read_audit',return_value=audit):
            result=await read_regions_readiness_audit()
            self.assertEqual([r['generation_ready'] for r in result['regions']],[True,False])
            g.return_value=ProviderHealth('ollama','inactive','offline',[])
            result=await read_regions_readiness_audit()
            self.assertFalse(any(r['generation_ready'] for r in result['regions']))
            self.assertTrue(result['regions'][0]['data_ready'])
            g.side_effect=ConnectionError('offline')
            result=await read_regions_readiness_audit()
            self.assertTrue(result['regions'][0]['data_ready'])
            self.assertFalse(result['local_models_ready'])
