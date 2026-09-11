import unittest
from ai_server.app.case_mechanism import case_mechanism_family
from ai_server.app.agents.case_study_agent import _case_mechanism_family as scout_family
from ai_server.app.llm.evidence_tools import _case_mechanism_family as tool_family


class SharedCaseMechanismTest(unittest.TestCase):
    def test_incidental_lodging_does_not_override_intervention(self):
        cases = [
            ({'intervention': '반값여행 지역환급', 'risks': ['숙박 통계는 별도 확인']}, 'spend_conversion'),
            ({'intervention': '디지털 관광주민증', 'operating_model': '숙박·교통 할인'}, 'return_visit'),
            ({'intervention': '시간예약 전환', 'risks': ['야간 운영 미정']}, 'reservation_conversion'),
        ]
        for case, expected in cases:
            self.assertEqual(case_mechanism_family(case), expected)
            self.assertEqual(scout_family(case), expected)
            self.assertEqual(tool_family(case), expected)

    def test_missing_mechanism_is_not_inferred_from_conditions(self):
        self.assertEqual(tool_family({'risks': ['숙박 협약 필요']}), 'other_operation')
