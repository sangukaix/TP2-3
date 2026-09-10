import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from ai_server.app.region_readiness_audit import read_audit

class AuditTest(unittest.TestCase):
    def test_missing_or_expired_is_not_green(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'audit.json'
            with patch('ai_server.app.region_readiness_audit.AUDIT_PATH',p):
                self.assertEqual(read_audit()['regions'],[])
                p.write_text(json.dumps({'checked_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),'regions':[{'verified':True}]}))
                self.assertEqual(read_audit()['regions'],[])
    def test_current_result_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'audit.json'
            payload={'checked_at':datetime.now(timezone.utc).isoformat(),'regions':[{'region_code':'51110','verified':False}],'status':'completed'}
            p.write_text(json.dumps(payload))
            with patch('ai_server.app.region_readiness_audit.AUDIT_PATH',p):self.assertEqual(read_audit(),payload)
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
