"""Combined, read-only validation report preserves empirical limitations."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validation_suite import main, run_all


class ValidationSuiteTests(unittest.TestCase):
    def test_all_software_gates_and_limits(self):
        report = run_all()
        self.assertTrue(report["all_software_fixtures_pass"])
        self.assertEqual(report["software_gate_checks_passed"], 34)
        self.assertTrue(all(v["all_pass"] for v in report["other_steps"].values()))
        self.assertEqual(report["step_191_synthetic_pair_coverage"]["status"], "NOT_RUN")
        self.assertEqual(report["operational_approval"], "NOT_GRANTED")
        self.assertEqual(report["automatic_procurement"], "DISABLED")
        self.assertEqual(report["limitations"]["supplier_causality"], "NOT_ESTABLISHED")
        self.assertEqual(report["limitations"]["calibrated_operational_probabilities"],
                         "NOT_ESTABLISHED")

    def test_combined_main_report_is_new_and_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "first_report.json"
            self.assertEqual(main(["--report", str(output)]), 0)
            self.assertTrue(output.is_file())
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--report", str(output)])


if __name__ == "__main__":
    unittest.main()
