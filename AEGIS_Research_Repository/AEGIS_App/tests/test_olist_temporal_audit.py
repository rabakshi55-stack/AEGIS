"""Read-only Step 200 retrospective outcome reconciliation tests."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olist_temporal_audit import _fixture, audit, self_test


class OlistTemporalAuditTests(unittest.TestCase):
    def test_all_seven_controls(self):
        report = self_test()
        self.assertTrue(report["all_pass"])
        self.assertEqual(len(report["checks"]), 7)

    def test_phase_and_month_statistics_are_historical_only(self):
        frozen, source = _fixture()
        report = audit(frozen, source, min_group=2)
        self.assertEqual(report["status"], "RETROSPECTIVE_SOURCE_ALIGNED_NOT_PROSPECTIVE")
        self.assertEqual(report["phase_tagged_cohorts"]["TRAIN"]["comparable_delivered_orders"], 1)
        self.assertEqual(report["phase_tagged_cohorts"]["TEST"]["comparable_delivered_orders"], 2)
        self.assertEqual(report["overall_scored_cohort"]["research_ranking_auc"], 1.0)
        self.assertEqual(report["overall_scored_cohort"]["excluded_or_unknown_outcomes"], 1)
        self.assertFalse(report["future_features_independently_proven_asof"])
        self.assertFalse(report["holdout_isolation_independently_verified"])
        self.assertFalse(report["contractual_delivery_promise_certified"])
        self.assertFalse(report["prospective_accuracy_certified"])

    def test_source_date_mismatch_blocks_ranking(self):
        frozen, source = _fixture()
        changed = deepcopy(frozen)
        changed.orders[0]["Purchase_Time"] = "2018-07-06T10:00:00"
        report = audit(changed, source, min_group=2)
        self.assertEqual(report["status"], "BLOCKED_SOURCE_OR_FROZEN_PURCHASE_TIME_MISMATCH")
        self.assertEqual(report["source_alignment_issue_counts"],
                         {"FROZEN_PURCHASE_TIMESTAMP_DIFFERS_FROM_SOURCE": 1})
        self.assertIsNone(report["overall_scored_cohort"]["research_ranking_auc"])
        self.assertIsNone(report["phase_tagged_cohorts"]["TEST"]["research_ranking_auc"])

    def test_source_registry_difference_is_rejected(self):
        frozen, source = _fixture()
        corrupt = source.replace(b"D,delivered", b"X,delivered")
        with self.assertRaisesRegex(ValueError, "match the original Olist registry"):
            audit(frozen, corrupt, min_group=2)

    def test_no_metrics_for_immature_or_single_outcome_class(self):
        frozen, source = _fixture()
        report = audit(frozen, source, min_group=30)
        self.assertIsNone(report["phase_tagged_cohorts"]["TRAIN"]["research_ranking_auc"])
        self.assertIsNone(report["phase_tagged_cohorts"]["TEST"]["research_ranking_auc"])
        self.assertIsNotNone(report["overall_scored_cohort"]["late_rate_among_comparable"])


if __name__ == "__main__":
    unittest.main()
