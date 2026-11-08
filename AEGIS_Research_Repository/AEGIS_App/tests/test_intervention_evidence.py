"""Tests that AEGIS comparisons never imply certified causal effects."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intervention_evidence import _fixture_comparison, evaluate_comparison, self_test


class InterventionEvidenceTests(unittest.TestCase):
    def test_seven_software_fixtures_pass_without_real_causal_claims(self):
        result = self_test()
        self.assertTrue(result["all_pass"])
        self.assertEqual(len(result["checks"]), 7)
        self.assertFalse(result["real_causal_effect_established"])

    def test_descriptive_group_difference_cannot_certify_supplier_switch(self):
        source, plan = _fixture_comparison()
        report = evaluate_comparison(source, plan)
        self.assertEqual(report["status"], "DESCRIPTIVE_GROUP_DIFFERENCE_ONLY_UNATTESTED")
        self.assertEqual(report["recorded_late_rate_by_group"],
                         {"control": 0.0, "treatment": 1.0})
        self.assertEqual(report["descriptive_treatment_minus_control"], 1.0)
        self.assertFalse(report["assignment_procedure_independently_verified"])
        self.assertFalse(report["intervention_execution_independently_verified"])
        self.assertFalse(report["true_supplier_causality_certified"])
        self.assertFalse(report["true_intervention_benefit_certified"])
        self.assertEqual(report["operational_approval"], "NOT_GRANTED")

    def test_missing_delivery_status_and_outcome_do_not_count(self):
        source, plan = _fixture_comparison()
        altered = copy.deepcopy(source)
        del altered["realized_outcomes"][1][0]["delivery_status"]
        report = evaluate_comparison(altered, plan)
        self.assertEqual(report["status"], "BLOCKED_SOURCE_OR_DESIGN_INTEGRITY")
        self.assertIn("MISSING_VERIFIED_DELIVERY_STATUS", report["design_issue_counts"])
        self.assertIsNone(report["descriptive_treatment_minus_control"])

        canceled = copy.deepcopy(source)
        canceled["realized_outcomes"][1][0]["delivery_status"] = "canceled"
        report = evaluate_comparison(canceled, plan)
        self.assertEqual(report["status"], "INCOMPLETE_PROSPECTIVE_OUTCOMES")
        self.assertIsNone(report["descriptive_treatment_minus_control"])

    def test_registrations_and_groups_must_be_valid(self):
        source, plan = _fixture_comparison()
        late = copy.deepcopy(plan)
        late["registered_at"] = "2025-08-01T00:00:00+00:00"
        with self.assertRaises(ValueError):
            evaluate_comparison(source, late)

        bad = copy.deepcopy(source)
        bad["comparison_assignment"][1][0]["evaluation_group"] = "SOME_OTHER_GROUP"
        report = evaluate_comparison(bad, plan)
        self.assertEqual(report["status"], "BLOCKED_SOURCE_OR_DESIGN_INTEGRITY")
        self.assertIn("INVALID_OR_UNDECLARED_GROUP", report["design_issue_counts"])


if __name__ == "__main__":
    unittest.main()
