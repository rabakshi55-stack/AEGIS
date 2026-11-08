"""Independent controls for prospective shadow-evaluation research semantics."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prospective_validation import _auc, _average_precision, _fixture, evaluate, self_test


class ProspectiveShadowTests(unittest.TestCase):
    def test_all_ten_software_controls(self):
        result = self_test()
        self.assertTrue(result["all_pass"])
        self.assertEqual(len(result["checks"]), 10)
        self.assertEqual(result["operational_approval"], "NOT_GRANTED")

    def test_auc_and_average_precision_are_not_calibration(self):
        self.assertEqual(_auc([(1, .5), (0, .5)]), .5)
        self.assertEqual(_average_precision([(1, .5), (0, .5)]), .5)
        self.assertEqual(_auc([(1, .9), (0, .1)]), 1.0)
        self.assertEqual(_auc([(1, .1), (0, .9)]), 0.0)
        self.assertIsNone(_auc([(1, .2), (1, .4)]))
        score, outcome, plan = _fixture()
        result = evaluate(score, outcome, plan)
        self.assertIsNone(result["brier_for_uncalibrated_scores"])
        self.assertFalse(result["probability_calibration_certified"])
        self.assertFalse(result["prospective_generalization_certified"])

    def test_pre_registration_and_model_chronology(self):
        score, outcome, plan = _fixture()
        bad_plan = copy.deepcopy(plan)
        bad_plan["registered_at"] = "2025-08-01T00:00:00+00:00"
        with self.assertRaises(ValueError):
            evaluate(score, outcome, bad_plan)
        before_plan = copy.deepcopy(score)
        before_plan[0]["score_recorded_at"] = "2025-06-10T00:00:00+00:00"
        result = evaluate(before_plan, outcome, plan)
        self.assertEqual(result["status"], "BLOCKED_INTEGRITY_ISSUES")
        self.assertIn("SCORE_RECORDED_BEFORE_RESEARCH_PLAN", result["issue_counts"])

    def test_unknown_outcomes_never_count_as_not_late(self):
        score, outcome, plan = _fixture()
        changed = copy.deepcopy(outcome)
        changed[0]["actual_delivery_timestamp"] = ""
        result = evaluate(score, changed, plan)
        self.assertEqual(result["unknown_or_unmatured_outcomes"], 1)
        self.assertEqual(result["mature_outcomes"], 3)
        self.assertIsNone(result["auc_ranking"])

    def test_future_faked_model_identity_suppresses_metrics(self):
        score, outcome, plan = _fixture()
        changed = copy.deepcopy(score)
        changed[0]["model_version"] = "UNVERIFIED_RETRAIN"
        result = evaluate(changed, outcome, plan)
        self.assertEqual(result["status"], "BLOCKED_INTEGRITY_ISSUES")
        self.assertIsNone(result["average_precision_ranking"])
        self.assertFalse(result["model_digest_independently_verified"])

    def test_features_known_after_score_does_not_pass(self):
        score, outcome, plan = _fixture()
        changed = copy.deepcopy(score)
        changed[0]["feature_latest_known_at"] = "2025-07-01T09:59:30+00:00"
        result = evaluate(changed, outcome, plan)
        self.assertEqual(result["status"], "BLOCKED_INTEGRITY_ISSUES")
        self.assertIn("FEATURE_KNOWN_AFTER_SCORE_WAS_RECORDED", result["issue_counts"])


if __name__ == "__main__":
    unittest.main()
