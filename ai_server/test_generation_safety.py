"""실제 생성/결제 없이 저장 실패 분리, 운영 샘플 금지, 비동기 응답을 검증합니다."""

import asyncio
from io import BytesIO
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from ai_server.app import main
from ai_server.app.report_review_status import review_label


class ReportStub:
    def model_dump(self, **kwargs):
        return {'region_name': '서울특별시 강남구', 'strategies': []}


class GenerationSafetyTests(unittest.IsolatedAsyncioTestCase):
    def test_no_implicit_growth_target(self):
        with self.assertRaises(ValidationError):
            main.ExecutionScenario.model_validate({})
        with self.assertRaises(ValidationError):
            main.ExecutionScenario.model_validate({'visitor_target_pct': 3})

    def test_document_does_not_hide_failed_or_stale_review(self):
        self.assertIn('초안', review_label({}))
        report = {'quality_review': {'approved':True, 'overall_score':90}}
        self.assertIn('통과', review_label(report))
        report['quality_review']['issues'] = [{'severity':'major'}]
        self.assertIn('초안', review_label(report))
        report['quality_review']['review_stale'] = True
        self.assertIn('미검수', review_label(report))
        report['generation_mode'] = 'offline_sample'
        self.assertIn('Agent 미실행', review_label(report))

    def test_failed_word_does_not_discard_ppt_or_report(self):
        with (patch.object(main, 'save_strategy_report') as save,
              patch.object(main, 'create_strategy_proposal_document', side_effect=ValueError('bad docx')),
              patch.object(main, 'create_strategy_proposal_presentation', return_value=BytesIO(b'ppt')),
              patch.object(main, 'write_document') as write):
            warnings = main._persist_completed_strategy_report('test-id','11680',ReportStub())
        save.assert_called_once()
        self.assertEqual(write.call_args.args[1], 'pptx')
        self.assertIn('DOCX', warnings[0])

    async def test_production_quota_error_never_becomes_sample_success(self):
        request = main.ReportRequest(region_name='서울특별시 강남구')
        jobs = {'test-id': {'region_code':'11680', 'region_name':request.region_name}}
        with (patch.dict(main.ENV_VALUES, {'APP_ENV':'production'}),
              patch.object(main, 'STRATEGY_REPORT_JOBS', jobs),
              patch.object(main, 'build_region_snapshot', return_value={}),
              patch.object(main, 'generate_orchestrated_report', new=AsyncMock(side_effect=HTTPException(429, {'message':'quota credit'}))),
              patch.object(main, '_persist_job_state_best_effort'),
              patch.object(main, 'build_offline_sample_report') as sample):
            await main._run_strategy_report_job('test-id','11680',request)
        self.assertEqual(jobs['test-id']['status'], 'failed')
        sample.assert_not_called()

    async def test_slow_document_persistence_keeps_event_loop_responsive(self):
        request = main.ReportRequest(region_name='서울특별시 강남구')
        jobs = {'test-id': {'region_code':'11680', 'region_name':request.region_name}}
        started, release = Event(), Event()
        def slow_persist(*args, **kwargs):
            started.set()
            release.wait(2)
            return []
        with (patch.object(main, 'STRATEGY_REPORT_JOBS', jobs),
              patch.object(main, 'build_region_snapshot', return_value={}),
              patch.object(main, 'generate_orchestrated_report', new=AsyncMock(return_value=ReportStub())),
              patch.object(main, '_persist_job_state_best_effort'),
              patch.object(main, '_persist_completed_strategy_report', side_effect=slow_persist)):
            task = asyncio.create_task(main._run_strategy_report_job('test-id','11680',request))
            try:
                await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)
                self.assertEqual(jobs['test-id']['status'], 'running')
                self.assertFalse(task.done())
            finally:
                release.set()
                await task
        self.assertEqual(jobs['test-id']['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
