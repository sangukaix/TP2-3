"""New layout data and text invariants, without network or paid LLM calls."""
import copy
import unittest
from pptx import Presentation
from ai_server.test_proposal_presentation_v3_contract import _sample_report
from ai_server.app.proposal_presentation_v4 import create_strategy_proposal_presentation
from ai_server.app.proposal_layout_v7 import wrap_words

class LayoutV7Test(unittest.TestCase):
    def test_native_chart_values_and_input_immutability(self):
        report=_sample_report();before=copy.deepcopy(report)
        deck=Presentation(create_strategy_proposal_presentation(report))
        charts=[s.chart for s in deck.slides[3].shapes if s.has_chart]
        self.assertEqual(list(charts[0].series[0].values),[1800,1810,1820])
        self.assertEqual(list(charts[1].series[0].values),[4700,4740,4780])
        self.assertEqual(len(charts[0].series),2)
        self.assertAlmostEqual(charts[0].series[1].values[-1],1820*1.01)
        self.assertEqual(report,before)

    def test_missing_targets_never_generate_uplift(self):
        report=_sample_report();report['execution_scenario']=None
        deck=Presentation(create_strategy_proposal_presentation(report))
        self.assertTrue(all(len(s.chart.series)==2 for s in deck.slides[3].shapes if s.has_chart))
        table=next(s.table for s in deck.slides[7].shapes if s.has_table)
        self.assertNotEqual(table.cell(1,2).text,'목표율 미입력')
        chart=next(s.chart for s in deck.slides[3].shapes if s.has_chart)
        self.assertAlmostEqual(chart.series[1].values[-1], chart.series[0].values[-1]*1.05)

    def test_five_steps_are_kept_in_four_rows(self):
        deck=Presentation(create_strategy_proposal_presentation(_sample_report()))
        self.assertEqual(len([s for s in deck.slides[6].shapes if s.name.startswith('flow-node-')]),4)
        self.assertIn('실행 작업 5',deck.slides[6].notes_slide.notes_text_frame.text)
        self.assertIn('확인 산출물 5',deck.slides[6].notes_slide.notes_text_frame.text)

    def test_wrapping_preserves_words_without_last_word_orphan(self):
        sentence='방문객이 지역 내에서 지출한 금액의 일부를 지역상품권으로 돌려받는 방식으로 혜택이 다시 지역 내 상점에서 사용되도록 설계'
        lines=wrap_words(sentence,883,34)
        self.assertEqual(' '.join(lines),sentence)
        self.assertGreater(len(lines[-1].split()),1)
        self.assertTrue(all(word in sentence.split() for line in lines for word in line.split()))

if __name__=='__main__':unittest.main()
