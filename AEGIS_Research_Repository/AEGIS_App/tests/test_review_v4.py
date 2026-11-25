import unittest,tempfile,shutil
from pathlib import Path
from review_v4 import get_final_evidence,ROOT
class FinalReview(unittest.TestCase):
    def test_external_research_only(self):
        r=get_final_evidence();self.assertTrue(r['available'],r.get('error'));self.assertEqual(r['operational_approval'],'NOT_GRANTED');j=r['external'];self.assertEqual(j['counts']['eligible_orders'],175002);self.assertFalse(j['untouched_team_attestation']);self.assertLess(j['raw']['roc_auc'],.5);self.assertGreater(j['calibrated']['brier'],j['training_prior_baseline']['brier'])
    def test_challenger_no_jd(self):
        c=get_final_evidence()['challenger'];self.assertFalse(c['jd_used']);self.assertFalse(c['operational_approval']);self.assertEqual(len(c['selection']),4)
    def test_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'Review_V4';shutil.copytree(ROOT,dest);p=dest/'JD/result.json';p.write_text(p.read_text()+' ');self.assertFalse(get_final_evidence(dest)['available'])
    def test_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:self.assertFalse(get_final_evidence(Path(tmp))['available'])
