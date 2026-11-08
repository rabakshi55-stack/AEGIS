"""AEGIS Step 192: adversarial, self-contained provenance-gate fixtures."""

import copy
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asof_validation import _fixture, load_csv_folder, self_test, validate


class AsOfValidationTests(unittest.TestCase):
    def test_paired_positive_and_negative_fixture_checks(self):
        result = self_test()
        self.assertTrue(result["all_pass"])
        self.assertEqual(len(result["checks"]), 9)
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["operational_approval"], "NOT_GRANTED")
        self.assertEqual(result["automatic_business_action"], "DISABLED")

    def test_healthy_fixture_is_not_a_business_certification(self):
        data = _fixture()
        unchanged = copy.deepcopy(data)
        report = validate(data)
        self.assertEqual(data, unchanged)
        self.assertEqual(report["status"], "STRUCTURE_AND_ASOF_CONSISTENT_UNATTESTED")
        self.assertFalse(report["source_system_independently_attested"])
        self.assertFalse(report["currency_and_delivery_semantics_certified"])
        self.assertFalse(report["supplier_capacity_jointly_certified"])
        self.assertFalse(report["predictive_calibration_certified"])
        self.assertFalse(report["real_world_intervention_effect_established"])
        self.assertEqual(report["operational_approval"], "NOT_GRANTED")
        self.assertNotIn("FIXTURE-1", str(report))

    def test_adversarial_rejections(self):
        changes = [
            ("orders_at_decision", "destination_known_at", "2025-07-04T00:00:00+00:00", "FUTURE_KNOWN_ORDER_FEATURE"),
            ("orders_at_decision", "purchase_timestamp", "2025-07-02T09:00:00+00:00", "DECISION_BEFORE_PURCHASE"),
            ("supplier_quotes", "eligible_for_item", "false", "SUPPLIER_NOT_ELIGIBLE"),
            ("supplier_quotes", "minimum_order_qty", "20", "BELOW_SUPPLIER_MOQ"),
            ("supplier_quotes", "unit_cost", "invalid", "INVALID_QUOTE_OR_TIMESTAMP"),
            ("supplier_capacity", "available_units", "5", "ALLOCATION_EXCEEDS_ASOF_CAPACITY"),
            ("baseline_allocations", "allocated_units", "11", "DEMAND_ALLOCATION_UNITS_MISMATCH"),
            ("realized_outcomes", "outcome_recorded_at", "2025-07-09T09:00:00+00:00", "OUTCOME_RECORDED_BEFORE_DELIVERY"),
            ("comparison_assignment", "assignment_timestamp", "2025-07-05T09:00:00+00:00", "COMPARISON_ASSIGNED_AFTER_DECISION"),
        ]
        for table, field, value, code in changes:
            with self.subTest(table=table, field=field):
                data = _fixture()
                data[table][1][0][field] = value
                report = validate(data)
                self.assertEqual(report["status"], "BLOCKED_FOR_REVIEW")
                self.assertIn(code, report["issue_counts"])

    def test_duplicate_key_and_blank_field_do_not_pass(self):
        data = _fixture()
        data["orders_at_decision"][1].append(copy.deepcopy(data["orders_at_decision"][1][0]))
        data["orders_at_decision"][1][1]["destination_state"] = ""
        report = validate(data)
        self.assertIn("DUPLICATE_KEY", report["issue_counts"])
        self.assertIn("BLANK_REQUIRED_FIELD", report["issue_counts"])

    def test_csv_reader_with_exact_eight_names_and_missing_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, (headers, rows) in _fixture().items():
                with (folder / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
            self.assertEqual(validate(load_csv_folder(folder))["issues_total"], 0)
            (folder / "supplier_quotes.csv").unlink()
            report = validate(load_csv_folder(folder))
            self.assertIn("MISSING_TABLE", report["issue_counts"])
            self.assertEqual(report["operational_approval"], "NOT_GRANTED")


if __name__ == "__main__":
    unittest.main()
