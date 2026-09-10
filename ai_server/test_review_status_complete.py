import unittest

from ai_server.app.report_review_status import review_label


class CompleteReviewStatusTest(unittest.TestCase):
    def test_hidden_validation_issue_blocks_approval_label(self):
        report = {'quality_review': {'approved': True, 'overall_score': 95, 'issues': [],
                  'validation_findings': [{'severity': 'major', 'problem': 'missing cost'}]}}
        self.assertNotIn('통과', review_label(report))

    def test_incomplete_audit_blocks_approval_label(self):
        report = {'quality_review': {'approved': True, 'overall_score': 95,
                                    'final_audit_completed': False}}
        self.assertNotIn('통과', review_label(report))

    def test_complete_review_keeps_approval_label(self):
        report = {'quality_review': {'approved': True, 'overall_score': 95,
                                    'final_audit_completed': True}}
        self.assertIn('통과', review_label(report))
