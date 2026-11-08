"""Automatic chart selection: synthetic examples, no private business records."""
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intake import LocalDataset, IntakeStore


class AdaptiveChartSelectionTests(unittest.TestCase):
    @staticmethod
    def dataset(name, content):
        return LocalDataset(name, content.encode("utf-8"))

    def test_delivery_source_generates_date_comparison_with_exact_counts(self):
        sample = self.dataset("deliveries.csv", """order_id,supplier_id,order_date,promised_delivery_date,actual_delivery_timestamp,quantity
A,S1,2026-01-01,2026-01-10,2026-01-12,5
B,S1,2026-01-05,2026-01-10,2026-01-10,6
C,S2,2026-02-02,2026-02-10,2026-02-08,2
D,S2,2026-02-03,2026-02-10,2026-02-11,4
""")
        result = sample.profile()["adaptive_dashboard"]
        by_id = {chart["id"]:chart for chart in result["charts"]}
        self.assertEqual(result["business_context"], "Delivery and logistics records (inferred)")
        self.assertEqual(by_id["date_comparison"]["values"], [
            {"label":"Before mapped date","count":1},
            {"label":"On mapped date","count":1},
            {"label":"After mapped date","count":2}])
        self.assertEqual(by_id["date_comparison"]["source"],"CURRENT_UPLOADED_DATASET")
        self.assertFalse(by_id["date_comparison"]["certified"])
        self.assertIn("not contractual lateness",by_id["date_comparison"]["caution"])
        self.assertNotIn("order_id",json.dumps(by_id["date_comparison"]["values"]))

    def test_sales_data_gets_revenue_trend_and_category_comparison(self):
        sample = self.dataset("sales.csv", """date,category,revenue,invoice_id
2026-01-01,North,10,I1
2026-01-02,South,20,I2
2026-02-02,North,30,I3
2026-02-10,South,40,I4
2026-03-01,South,50,I5
2026-03-02,North,60,I6
""")
        plan = sample.profile()["adaptive_dashboard"]
        charts={item["id"]:item for item in plan["charts"]}
        self.assertIn("Sales",plan["business_context"])
        self.assertEqual(charts["recorded_amount_trend"]["type"],"line")
        self.assertEqual([x["count"] for x in charts["recorded_amount_trend"]["values"]],[30,70,110])
        self.assertEqual(sum(x["count"] for x in charts["recorded_amount_by_group"]["values"]),210)
        self.assertTrue(all(x["permitted_action"] == "NONE" if "permitted_action" in x else not x["certified"] for x in plan["charts"]))

    def test_inventory_stock_by_warehouse_no_supplier_claim(self):
        sample=self.dataset("inventory.csv", """warehouse,stock_quantity,item_code
East,8,S1
East,7,S2
West,5,S3
West,4,S4
Central,2,S5
Central,6,S6
""")
        plan=sample.profile()["adaptive_dashboard"]
        charts={c["id"]:c for c in plan["charts"]}
        self.assertIn("Inventory",plan["business_context"])
        self.assertEqual(sum(p["count"] for p in charts["units_by_group"]["values"]),32)
        self.assertNotIn("supplier",json.dumps(plan).lower().split("warnings")[0])

    def test_no_semantics_gives_quality_fallback_not_invented_outcomes(self):
        sample=self.dataset("random.csv", """reference,notes
X1,red
X2,blue
X3,yellow
""")
        plan=sample.profile()["adaptive_dashboard"]
        self.assertEqual(plan["business_context"],"Unclassified business dataset")
        self.assertTrue(plan["charts"])
        self.assertTrue(all(c["id"] not in ("date_comparison","recorded_amount_trend") for c in plan["charts"]))
        self.assertFalse(any(c["prediction"] for c in plan["charts"]))
        self.assertEqual(plan["permitted_action"],"NONE")

    def test_dataset_replacement_and_mapping_recompute_plan(self):
        store=IntakeStore()
        first=store.upload("one.csv",b"supplier_id,region,quantity\nS1,North,5\nS1,North,6\nS2,South,2\nS2,South,3\n")
        by_id={c["id"]:c for c in first["adaptive_dashboard"]["charts"]}
        self.assertEqual(by_id["units_by_group"]["source_columns"],["quantity","supplier_id"])
        mapped=store.mapping({"supplier_id":"region","required_units":"quantity"})
        by_id={c["id"]:c for c in mapped["adaptive_dashboard"]["charts"]}
        self.assertEqual(by_id["units_by_group"]["source_columns"],["quantity","region"])
        after=store.upload("two.csv",b"score\n12\n15\n19\n30\n40\n60\n")
        self.assertNotIn("supplier_id",json.dumps(after["adaptive_dashboard"]))
        self.assertEqual(after["adaptive_dashboard"]["status"],"DESCRIPTIVE_ONLY")

    def test_supplier_date_comparison_shows_denominators_not_causality(self):
        rows = ["supplier_id,promised_delivery_date,actual_delivery_timestamp"]
        for i in range(10):
            rows.append(f"A,2026-01-01,{'2026-01-02' if i < 6 else '2026-01-01'}")
            rows.append(f"B,2026-01-01,{'2026-01-02' if i < 1 else '2026-01-01'}")
        d=self.dataset("suppliers.csv", "\n".join(rows)+"\n")
        charts={c["id"]:c for c in d.profile()["adaptive_dashboard"]["charts"]}
        c=charts["recorded_date_exceptions_by_supplier"]
        self.assertEqual(c["value_label"],"After mapped date (%)")
        self.assertEqual(c["values"][0]["count"],60)
        self.assertEqual(c["values"][1]["count"],10)
        self.assertEqual(c["values"][0]["comparable_rows"],10)
        self.assertIn("not a supplier reliability", c["caution"])
        self.assertFalse(c["certified"])

    def test_many_unique_identifiers_not_shown_as_donut(self):
        content="supplier_id,order_date\n" + "\n".join(f"Unique-{i},2026-01-01" for i in range(30))+"\n"
        result=self.dataset("unique.csv",content).profile()["adaptive_dashboard"]
        self.assertNotIn("records_by_group",[c["id"] for c in result["charts"]])

    def test_incomplete_date_columns_do_not_make_unjustified_late_rate(self):
        content="promised_delivery_date,actual_delivery_timestamp\n" + "2026-01-01,\n"*10 + "2026-01-01,2026-01-02\n"
        result=self.dataset("missing.csv",content).profile()["adaptive_dashboard"]
        charts={c["id"]:c for c in result["charts"]}
        if "date_comparison" in charts:
            self.assertIn("10 rows lacked",charts["date_comparison"]["caution"])
        self.assertTrue(any(c["id"]=="field_completeness" for c in charts.values()))

    def test_html_like_labels_are_values_not_markup(self):
        d=self.dataset("safe.csv","supplier_id,quantity\n<script>,1\n<script>,2\nOther,3\nOther,4\n")
        plan=d.profile()["adaptive_dashboard"]
        self.assertIn("<script>",json.dumps(plan))
        self.assertTrue(all(c["source"]=="CURRENT_UPLOADED_DATASET" for c in plan["charts"]))
        self.assertLessEqual(len(plan["charts"]),5)


if __name__=="__main__":
    unittest.main()
