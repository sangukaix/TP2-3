import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from ai_server.app.agents.chat_assistant_agent import TourismChatAssistantAgent, supplied_urls
from ai_server.app.llm.chat_context import pack_report, unpack_report, revision_report


class ChatRoutingTest(unittest.IsolatedAsyncioTestCase):
    def test_revision_keeps_cited_evidence_and_lists_other_references(self):
        report = {'strategies': [{'source_id': 'read'}], 'evidence_sources': [
            {'source_id': 'read', 'source_type': 'rag', 'summary': 'full'},
            {'source_id': 'other', 'source_type': 'rag', 'summary': 'not used', 'title': 'reference'}]}
        scoped = revision_report(report)
        self.assertEqual(scoped['evidence_sources'], [report['evidence_sources'][0]])
        self.assertEqual(scoped['reference_only_not_read'][0]['source_id'], 'other')
        self.assertEqual(len(report['evidence_sources']), 2)
    def test_report_evidence_roundtrip(self):
        source = '공식 근거의 수치와 단위를 변경하지 않습니다.' * 10
        report = {'agent_trace': [{'duration_ms': 20}], 'sources': [{'text': source, 'value': None}, {'text': source, 'value': 23}],
                  'collision': {'__chat_text_ref_v1__': 8}, 'ml_analysis': {'visitors': 2345678}}
        self.assertEqual(unpack_report(pack_report(report)), {key: value for key, value in report.items() if key != 'agent_trace'})
    def test_source_url_must_be_in_supplied_material(self):
        self.assertEqual(supplied_urls({'sources': [{'url': 'https://example.go.kr/a'}], 'empty': []}), {'https://example.go.kr/a'})
        self.assertEqual(supplied_urls(None), set())
    async def call(self, question, web=True, report=None):
        router = SimpleNamespace(generate=AsyncMock(return_value={'mode': 'revise', 'sources': [], 'report_patch': {'solution': '수정'}}),
                                 trace=[{'provider': 'gemma', 'model': 'gemma4:26b', 'web_search_used': False, 'usage': {'output_tokens': 10}}])
        result = await TourismChatAssistantAgent(env_values={}, llm_router=router).answer(
            snapshot={'region_name': '원주시', 'period': '2026-06'}, question=question, history=[],
            current_report=report, enable_web_search=web)
        return router.generate.call_args.args[0], result

    async def test_checkbox_does_not_force_paid_research(self):
        request, result = await self.call('기획안을 더 구체적으로 바꿔줘', report={'strategies': [{}]})
        self.assertEqual(request.task, 'chat_revise')
        self.assertFalse(request.requires_web_search)
        self.assertIsNone(request.tools)
        self.assertEqual(result['generation_mode'], 'local')
        self.assertEqual(result['execution']['model'], 'gemma4:26b')

    async def test_research_requires_permission_and_intent(self):
        request, _ = await self.call('최신 공식 사례를 검색해줘')
        self.assertTrue(request.requires_web_search)
        request, _ = await self.call('최신 공식 사례를 검색해줘', web=False)
        self.assertFalse(request.requires_web_search)

    async def test_no_report_no_patch(self):
        _, result = await self.call('수정해줘', report=None)
        self.assertIsNone(result['report_patch'])


if __name__ == '__main__':
    unittest.main()
