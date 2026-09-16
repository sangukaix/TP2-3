import unittest
from ai_server.app.proposal_case_outcomes import source_outcome, SEOUL_ATTACHMENT


class CaseOutcomeBindingTest(unittest.TestCase):
    def source(self, **changes):
        return dict({'source_url': f'https://culture.seoul.go.kr/culture/cmmn/file/fileDown.do?atchFileId={SEOUL_ATTACHMENT}&fileSn=2',
                     'case_region':'서울특별시 문화유산 집적지역', 'intervention':'문화유산 야간 개방'}, **changes)

    def test_verified_constituent_event_has_period_scope_and_sources(self):
        result=source_outcome(self.source())
        self.assertAlmostEqual((result['after']/result['before']-1)*100,30)
        self.assertEqual(result['parent_page'],83)
        self.assertIn('행사',result['metric'])
        self.assertIn('계절',result['interpretation'])
        self.assertEqual(len(result['references']),3)

    def test_night_keyword_and_same_attachment_other_file_do_not_borrow_results(self):
        self.assertIsNone(source_outcome(self.source(source_url='https://example.org/night-tourism')))
        self.assertIsNone(source_outcome(self.source(case_region='제주시')))
        self.assertIsNone(source_outcome(self.source(source_url=f'https://culture.seoul.go.kr/culture/cmmn/file/fileDown.do?atchFileId={SEOUL_ATTACHMENT}&fileSn=1')))
