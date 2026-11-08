"""Research-evidence provenance tests: local only, no training or operations."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_validation import get_evidence, EVIDENCE_PATH, BUNDLE_PATH


class ValidationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    def test_actual_archived_evidence_matches_uploaded_bundle(self):
        result = get_evidence()
        self.assertTrue(result['available'], result.get('error'))
        self.assertEqual(result['phases']['ALL']['count'], 58911)
        self.assertEqual(result['phases']['VALIDATION']['late_count'], 2645)
        self.assertLess(result['phases']['VALIDATION']['roc_auc'], .6)
        self.assertEqual(result['operational_approval'], 'NOT_GRANTED')
        self.assertFalse(result['prospective_certified'])
        self.assertEqual(result['automatic_business_actions'], 'DISABLED')

    def _write_data(self, path, evidence):
        path.write_text(json.dumps(evidence), encoding='utf-8')

    def test_missing_evidence_blocks_metrics(self):
        result = get_evidence(evidence_path=Path('/nonexistent/aegis/evidence.json'))
        self.assertFalse(result['available'])
        self.assertNotIn('phases', result)

    def test_modified_bundle_blocks_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'different.json'
            bundle.write_bytes(b'{}')
            result = get_evidence(bundle_path=bundle)
            self.assertFalse(result['available'])
            self.assertNotIn('phases', result)

    def test_wrong_late_count_blocks_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / 'bad.json'
            broken = json.loads(json.dumps(self.evidence))
            broken['phases']['VALIDATION']['late_count'] += 1
            self._write_data(evidence, broken)
            result = get_evidence(evidence_path=evidence)
            self.assertFalse(result['available'])

    def test_falsely_certified_prospective_holdout_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / 'bad.json'
            broken = dict(self.evidence)
            broken['pristine_prospective_holdout'] = True
            self._write_data(evidence, broken)
            result = get_evidence(evidence_path=evidence)
            self.assertFalse(result['available'])

    def test_unapproved_operational_action_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / 'bad.json'
            broken = dict(self.evidence)
            broken['automatic_business_actions'] = 'ENABLED'
            self._write_data(evidence, broken)
            result = get_evidence(evidence_path=evidence)
            self.assertFalse(result['available'])

    def test_source_report_tampering_not_claimed_as_certification(self):
        result = get_evidence()
        self.assertIn('application does not independently recheck original Olist CSVs', result['disclaimer'])

if __name__ == '__main__':
    unittest.main()
