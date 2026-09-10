import asyncio
import unittest
from ai_server.app.generation_progress import track_progress, notify_progress

class ProgressTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_jobs_and_cleanup_are_isolated(self):
        first=[];second=[]
        async def run(events):
            with track_progress(lambda step,message:events.append((step,message))):
                notify_progress(0,'start')
                await asyncio.sleep(0)
                notify_progress(2,'draft')
            notify_progress(3,'outside')
        await asyncio.gather(run(first),run(second))
        self.assertEqual(first,[(0,'start'),(2,'draft')])
        self.assertEqual(second,first)

    async def test_job_response_preserves_progress(self):
        from unittest.mock import patch
        from ai_server.app.main import _strategy_job_response
        jobs={'test':{'region_code':'11620','region_name':'관악구','status':'running','message':'초안 작성','progress_step':2}}
        with patch('ai_server.app.main.STRATEGY_REPORT_JOBS',jobs):
            result=_strategy_job_response('test')
            self.assertEqual(result.progress_step,2)
            self.assertEqual(result.message,'초안 작성')
