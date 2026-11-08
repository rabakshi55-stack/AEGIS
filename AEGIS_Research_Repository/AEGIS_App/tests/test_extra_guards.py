from pathlib import Path
import sys
import unittest
from io import BytesIO
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import conversation
from prospective_validation import _fixture,evaluate

class ExtraEvidenceGuards(unittest.TestCase):
    def setUp(self):
        self.original = "Of 3 comparable delivery pairs, 2 are recorded after the promise date. Not a certified KPI."
        self.facts = {"date_pairs":3,"after_promise":2,"supplier_causality_certified":False}
    def mock_reply(self, reply):
        def run(request, timeout):
            return BytesIO(json.dumps({"message":{"content":reply}}).encode())
        return run
    def test_unverified_qualifier_cannot_disappear(self):
        with self.assertRaisesRegex(conversation.LocalModelUnavailable,'uncertainty qualification'):
            conversation.natural_answer('How did it go?',self.original,self.facts,[],
                http_open=self.mock_reply('There were 2 of 3 rows after the promise.'))
    def test_sourcing_guarantee_rejected_without_numbers(self):
        with self.assertRaisesRegex(conversation.LocalModelUnavailable,'action-safety'):
            conversation.natural_answer('Which is best?',self.original,self.facts,[],
                http_open=self.mock_reply('Supplier XYZ is more reliable. Definitely use them.'))
    def test_research_score_out_of_range_fails_closed(self):
        s,o,p=_fixture();s[0]['research_score']='1.4'
        r=evaluate(s,o,p)
        self.assertEqual(r['status'],'BLOCKED_INTEGRITY_ISSUES')
        self.assertIsNone(r['auc_ranking'])
    def test_mean_score_gap_is_descriptive_not_certified(self):
        s,o,p=_fixture();r=evaluate(s,o,p)
        self.assertEqual(r['mean_uncalibrated_research_score'],.475)
        self.assertEqual(r['absolute_score_mean_vs_late_rate_gap'],.025)
        self.assertIsNone(r['brier_for_uncalibrated_scores'])
        self.assertFalse(r['probability_calibration_certified'])

if __name__=='__main__':unittest.main()
