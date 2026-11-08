"""Synthetic-only tests for the independent historical outcome attachment."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_outcomes import HistoricalOutcomes, HistoricalOutcomeStore


IDS = ["fake-order-a", "fake-order-b", "fake-order-c", "fake-order-d"]
CSV = (
    "order_id,order_estimated_delivery_date,order_delivered_customer_date,order_status,order_purchase_timestamp\n"
    "fake-order-a,2018-08-10 00:00:00,2018-08-09 19:01:00,delivered,2018-08-01\n"
    "fake-order-b,2018-08-10 00:00:00,2018-08-10 22:01:00,delivered,2018-08-01\n"
    "fake-order-c,2018-08-10 00:00:00,2018-08-11 01:01:00,delivered,2018-08-01\n"
    "fake-order-d,2018-08-10 00:00:00,,shipped,2018-08-01\n"
).encode()


class OlistOutcomeTests(unittest.TestCase):
    def test_nondelivered_canceled_or_conflicting_status_never_enters_timing_denominator(self):
        source = (
            "order_id,order_status,order_estimated_delivery_date,order_delivered_customer_date,order_purchase_timestamp\n"
            "fake-order-a,delivered,2018-08-10,2018-08-11,2018-08-01\n"
            "fake-order-b,canceled,2018-08-10,2018-08-09,2018-08-01\n"
            "fake-order-c,shipped,2018-08-10,,2018-08-01\n"
            "fake-order-d,delivered,2018-08-10,2018-07-01,2018-08-01\n"
        ).encode()
        result = HistoricalOutcomes("olist_orders_dataset.csv", source, IDS)
        self.assertEqual(result.summary["comparable"], 1)
        self.assertEqual(result.summary["after"], 1)
        self.assertEqual(result.summary["before"], 0)
        self.assertEqual(result.summary["contradictory_status_delivery"], 1)
        self.assertEqual(result.summary["not_recorded_as_delivered"], 1)
        self.assertEqual(result.summary["delivery_before_purchase"], 1)
        self.assertTrue(result.summary["all_records_reconciled"])
        self.assertFalse(result.summary["business_kpi_certified"])

    def test_missing_order_status_column_fails_closed(self):
        stripped = CSV.replace(b"order_status,", b"")
        stripped = stripped.replace(b",delivered,", b",").replace(b",shipped,", b",")
        with self.assertRaisesRegex(ValueError, "order_status"):
            HistoricalOutcomes("olist_orders_dataset.csv", stripped, IDS)

    def test_missing_purchase_timestamp_rejected_and_invalid_purchase_excluded(self):
        stripped = CSV.replace(b",order_purchase_timestamp", b"")
        stripped = stripped.replace(b",2018-08-01\n", b"\n")
        with self.assertRaisesRegex(ValueError, "order_purchase_timestamp"):
            HistoricalOutcomes("olist_orders_dataset.csv", stripped, IDS)
        malformed = CSV.replace(b"delivered,2018-08-01\n", b"delivered,garbled\n", 1)
        result = HistoricalOutcomes("olist_orders_dataset.csv", malformed, IDS)
        self.assertEqual(result.summary["invalid_purchase_timestamp"], 1)
        self.assertEqual(result.summary["comparable"], 2)

    def test_source_calendar_day_comparison_preserves_denominator(self):
        data = HistoricalOutcomes("olist_orders_dataset.csv", CSV, IDS)
        self.assertEqual(data.summary["source_orders"], 4)
        self.assertEqual(data.summary["comparable"], 3)
        self.assertEqual(data.summary["before"], 1)
        self.assertEqual(data.summary["on"], 1)
        self.assertEqual(data.summary["after"], 1)
        self.assertEqual(data.summary["missing_actual"], 0)
        self.assertEqual(data.summary["not_recorded_as_delivered"], 1)
        self.assertFalse(data.summary["business_kpi_certified"])
        self.assertIn("1 of 3 comparable", data.explain("How many were delivered after the estimated date?"))
        self.assertIn("1 of 3 comparable", data.explain("How many delivered before the estimated date?"))
        self.assertIn("2 of 3 comparable", data.explain("How many were on time?"))
        self.assertIn("same calendar day", data.explain("Was this order late?", IDS[1]))
        self.assertIn("recomputed", data.explain("Are you sure?", IDS[0],
                                                [{"question":"How many were delivered after?"}]))

    def test_exact_registry_reconciliation_and_no_partial_replacement(self):
        store=HistoricalOutcomeStore()
        initial=store.attach("olist_orders_dataset.csv", CSV, IDS)
        self.assertTrue(initial["loaded"])
        bad=CSV.replace(b"fake-order-b", b"not-a-source")
        with self.assertRaisesRegex(ValueError, "match the original Olist registry"):
            store.attach("olist_orders_dataset.csv", bad, IDS)
        self.assertTrue(store.status()["loaded"])
        with self.assertRaisesRegex(ValueError, "No partial import"):
            HistoricalOutcomes("olist_orders_dataset.csv", CSV, IDS + ["fake-order-e"])
        with self.assertRaisesRegex(ValueError, "not the original Olist"):
            HistoricalOutcomes("other.csv", b"order_id,value\na,1\n", IDS)
        self.assertFalse(store.clear()["loaded"])


if __name__ == "__main__":
    unittest.main()
