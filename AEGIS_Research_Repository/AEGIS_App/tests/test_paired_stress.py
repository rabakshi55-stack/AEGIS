"""Tests for AEGIS's independently disclosed synthetic paired stress study."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paired_stress import _source_bytes, build_candidate_menu, export_experiment, run_experiment


FIXTURE_FILES = {
    "purchase_orders.csv": (
        "purchase_order_id,order_date,component_id,plant_id,supplier_id,order_quantity_units\n"
        "PO-A,2025-07-07,CMP-007,PLT-1,S1,100\n"
        "PO-B,2025-07-14,CMP-007,PLT-1,S2,150\n"
    ),
    "supplier_component_options.csv": (
        "supplier_id,component_id,quoted_unit_cost_usd,minimum_order_qty,approved_for_sourcing\n"
        "S1,CMP-007,10.00,50,1\nS2,CMP-007,12.00,50,1\n"
    ),
    "transport_lanes.csv": (
        "origin_type,destination_type,origin_id,destination_id,freight_cost_per_unit_usd\n"
        "supplier,plant,S1,PLT-1,2.00\n"
        "supplier,plant,S2,PLT-1,1.50\n"
    ),
    "suppliers.csv": (
        "supplier_id,region,contract_on_time_target,qualified_flag\n"
        "S1,North,0.90,1\nS2,South,0.80,1\n"
    ),
}


class PairedStressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        data = self.root / "data"
        data.mkdir()
        for filename, text in FIXTURE_FILES.items():
            (data / filename).write_text(text, encoding="utf-8")
        self.zip = self.root / "source.zip"
        with zipfile.ZipFile(self.zip, "w") as archive:
            for filename, text in FIXTURE_FILES.items():
                archive.writestr("AEGIS_4_0_v0_2/data/" + filename, text)

    def test_complete_common_shocks_and_fixed_research_gate(self):
        before = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        result = run_experiment(self.zip, scenarios=12, seed=7)
        report = result["report"]
        self.assertEqual(report["candidate_pair_count"], 4)
        self.assertEqual(report["paired_rows"], 48)
        self.assertEqual(report["coverage_percent"], 100.0)
        self.assertTrue(all(report["independent_checks"].values()))
        self.assertFalse(report["real_supplier_causality_established"])
        self.assertFalse(report["real_intervention_effect_established"])
        self.assertFalse(report["joint_capacity_feasibility_retested"])
        self.assertFalse(report["late_delivery_probabilities_estimated"])
        self.assertEqual(report["permitted_business_action"], "NONE")
        self.assertEqual(report["operational_approval"], "NOT_GRANTED")
        self.assertEqual(before, hashlib.sha256(self.zip.read_bytes()).hexdigest())
        self.assertEqual(result, run_experiment(self.zip, scenarios=12, seed=7))

        for scenario in range(1, 13):
            rows = [x for x in result["paired_exposures"] if x["scenario_id"] == scenario]
            self.assertEqual(len(rows), 4)
            self.assertEqual(len({x["global_shock"] for x in rows}), 1)
        for row in result["pair_summary"]:
            if row["baseline"]:
                self.assertEqual(row["mean_paired_index_difference"], 0.0)
                self.assertEqual(row["sensitivity_weight_025"], 0.0)
                self.assertEqual(row["sensitivity_weight_085"], 0.0)

    def test_menu_reconstructs_original_pair_costs(self):
        menu = build_candidate_menu(_source_bytes(self.root))
        self.assertEqual(len(menu), 4)
        cost = next(
            r["landed_cost_usd"] for r in menu
            if r["order_id"] == "PO-A" and r["supplier_id"] == "S1"
        )
        self.assertEqual(cost, "1200.00")

    def test_explicit_output_cannot_replace_previous_results(self):
        result = run_experiment(self.root, scenarios=2)
        output = self.root / "results"
        export_experiment(result, output)
        self.assertTrue((output / "audit_report.json").is_file())
        self.assertTrue((output / "paired_exposures.csv").is_file())
        with self.assertRaises(FileExistsError):
            export_experiment(result, output)

    def test_input_and_source_integrity_guards(self):
        with self.assertRaises(ValueError):
            run_experiment(self.root, scenarios=1)
        with self.assertRaises(ValueError):
            run_experiment(self.root, scenarios=10001)
        broken = dict(_source_bytes(self.root))
        broken["purchase_orders.csv"] = broken["purchase_orders.csv"].replace(
            b"PO-B,2025-07-14", b"PO-A,2025-07-14"
        )
        with self.assertRaisesRegex(ValueError, "Duplicate purchase order"):
            build_candidate_menu(broken)


if __name__ == "__main__":
    unittest.main()
