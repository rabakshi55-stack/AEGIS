"""Portable integrity and research-boundary tests for review evidence."""
import json, shutil, tempfile, unittest
from pathlib import Path
from review_v3.read_only import get_review_evidence, HERE

class ReviewV3Tests(unittest.TestCase):
    def test_review_is_available_but_not_certified(self):
        r=get_review_evidence(); self.assertTrue(r['available'],r.get('error')); self.assertFalse(r['untouched_holdout_certified']); self.assertEqual(r['operational_approval'],'NOT_GRANTED')
        self.assertEqual(r['population']['mature_comparable'],25796); self.assertAlmostEqual(r['calibrated']['roc_auc'],.45726911189421937)
        self.assertGreater(r['calibrated']['brier'],r['raw']['brier'])
    def test_equal_cost_scope_and_risk_lock(self):
        r=get_review_evidence(); self.assertEqual(r['monthly_common_cost_usd'],1698024); self.assertEqual(r['sequential_common_cost_usd'],1717967.5); self.assertFalse(r['risk_lock_changes_assignment'])
        self.assertNotEqual(r['archived_daily_quoted_cost_usd'],r['sequential_common_cost_usd'])
    def test_tampered_report_is_withheld(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'evidence'; shutil.copytree(HERE/'evidence',dest)
            with (dest/'predictive_review.json').open('a') as f: f.write(' ')
            self.assertFalse(get_review_evidence(dest)['available'])
    def test_missing_report_is_withheld(self):
        with tempfile.TemporaryDirectory() as tmp: self.assertFalse(get_review_evidence(Path(tmp))['available'])
