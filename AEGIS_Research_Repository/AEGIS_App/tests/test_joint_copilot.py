"""Autodetection, reference-based joint answers, and action-safety regression tests."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from threading import Thread
import urllib.request

APP_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
from joint_copilot import (SOURCE, answer_joint, determine_context, joint_requested,
                          safe_facts, validate_report)

SPEC=importlib.util.spec_from_file_location("aegis_jc_app", APP_ROOT / "app.py")
app=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def fixture():
    return {
        "experiment":"SYNTHETIC_COMPONENT_MONTH_JOINT_CAPACITY",
        "scope":{"component":"CMP-007","month":"2025-07","orders":16,"total_order_units":13900,
                 "eligible_pairs":176,"suppliers":5},
        "status":"EXACT_MIN_COST_MONTHLY_SYNTHETIC",
        "exact_cost_optimum_certified_for_synthetic_problem":True,
        "automatic_procurement":"DISABLED","operational_approval":"NOT_GRANTED",
        "baseline_landed_cost_usd":1928061.0,
        "result_landed_cost_usd":1698024.0,
        "hypothetical_cost_difference_usd":230037.0,
        "checks":{"all_order_assignments":True,"only_eligible_source_candidates":True,
                  "all_monthly_capacities_respected":True,"candidate_cost_reconciles":True,
                  "baseline_joint_capacity_feasible":False},
        "independent_exact_reference":{"method":"INDEPENDENT_EXACT_0_1_KNAPSACK","matches_solver":True},
        "capacity_by_supplier":{"SUP-014":{"monthly_capacity_units":9425,"assigned_units":9225,"remaining_units":200},
                                "SUP-045":{"monthly_capacity_units":18523,"assigned_units":4675,"remaining_units":13848}},
    }


class JointCopilotTests(unittest.TestCase):
    def test_joint_recognition(self):
        self.assertTrue(joint_requested("Explain the July 2025 synthetic joint-capacity optimization"))
        self.assertTrue(joint_requested("How was the 2025-07 allocation made?"))
        self.assertFalse(joint_requested("Explain Scenario 9 and its headroom"))

    def test_auto_chooses_joint_over_wrong_dropdown(self):
        q="Explain the July 2025 joint-capacity optimization"
        self.assertEqual(determine_context(q,"historical_order",has_order=True),"joint_capacity")
        self.assertEqual(determine_context(q,"headroom"),"joint_capacity")
        self.assertEqual(determine_context(q,"auto"),"joint_capacity")

    def test_legacy_scenario_stays_separate(self):
        self.assertEqual(determine_context("Explain Scenario 9","auto",last_context="joint_capacity"),"headroom")
        self.assertEqual(determine_context("Explain Scenario 9","joint_capacity"),"headroom")

    def test_followup_stays_in_verified_joint_source(self):
        self.assertEqual(determine_context("How much capacity is left?","auto",last_context="joint_capacity"),"joint_capacity")
        self.assertEqual(determine_context("Which suppliers were selected?","auto",last_context="joint_capacity"),"joint_capacity")

    def test_uploaded_data_manual_context_isolation(self):
        self.assertEqual(determine_context("Explain joint-capacity", "local_dataset"),"local_dataset")

    def test_matched_costs_and_qualifiers(self):
        result=answer_joint("How many orders and units and costs and limitations?",fixture())
        for token in ("16 whole orders","13,900 units","$1,928,061.00","$1,698,024.00",
                      "$230,037.00","synthetic","not verified real savings","No business action"):
            self.assertIn(token,result)
        self.assertNotIn("Scenario 9 ranked",result)

    def test_supplier_followup_grounded(self):
        result=answer_joint("Which suppliers were used and how much capacity is left?",fixture())
        for token in ("SUP-014", "9,225", "200 remaining", "SUP-045", "4,675", "13,848 remaining"):
            self.assertIn(token,result)

    def test_counterfactual_does_not_invent(self):
        result=answer_joint("What if we reduce supplier capacity by 20%?",fixture())
        self.assertIn("does not contain a recomputed result",result)
        self.assertNotIn("$46,007",result)

    def test_decision_followup_answer_is_different_and_actionable_as_a_checklist(self):
        report=fixture()
        prior=answer_joint("What does joint-capacity evidence show, and what are its limitations?",report)
        question=("If the optimized cost is lower by $230,037, why shouldn't we "
                  "immediately switch suppliers? What exactly needs to be verified first?")
        answer=answer_joint(question,report)
        self.assertNotEqual(prior,answer)
        self.assertIn("time-valid quotations",answer)
        self.assertIn("existing commitments",answer)
        self.assertIn("transport routes",answer)
        self.assertIn("human-reviewed pilot",answer)
        self.assertIn("Business actions remain disabled",answer)
        self.assertNotIn("we should switch",answer.lower())

    def test_short_decision_followup_retains_question_specific_verification(self):
        r=fixture()
        for question in ("Why not switch suppliers yet?", "What must be verified first?",
                         "Should we change suppliers now?", "What evidence is missing before a decision?"):
            answer=answer_joint(question,r)
            self.assertIn("existing commitments",answer,question)
            self.assertIn("synthetic",answer,question)
            self.assertNotIn("guaranteed",answer.lower(),question)

    def test_proposed_new_scenario_is_not_computed_by_chat(self):
        result=answer_joint("What if available capacity drops tomorrow?",fixture())
        self.assertIn("does not contain a recomputed result",result)
        self.assertNotIn("$230,037.00",result)

    def test_report_rejects_unreconciled_metrics(self):
        f=fixture(); f["hypothetical_cost_difference_usd"]=300000
        with self.assertRaises(ValueError):validate_report(f)
        f=fixture(); f["checks"]["all_monthly_capacities_respected"]=False
        with self.assertRaises(ValueError):validate_report(f)
        f=fixture();f["operational_approval"]="GRANTED"
        with self.assertRaises(ValueError):validate_report(f)

    def test_safe_facts_do_not_expose_raw_order_ids(self):
        facts=safe_facts(fixture())
        self.assertEqual(facts["whole_orders"],16)
        self.assertFalse(facts["real_quote_or_supplier_benefit_proven"])
        self.assertNotIn("assignment_details",facts)

    def test_http_automatic_routing_and_followup(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),app.AegisHandler)
        thread=Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True)
        old=app.STORE
        app.STORE.ready=True
        thread.start()
        base=f"http://127.0.0.1:{server.server_address[1]}"
        def ask(question, **kwargs):
            body=json.dumps({"question":question,"context":"historical_order",**kwargs}).encode()
            req=urllib.request.Request(base+"/api/copilot",data=body,
                headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=5) as response:
                return json.load(response)
        try:
            with patch.object(app,"get_joint_evidence",side_effect=lambda: fixture()):
                answer=ask("Explain July 2025 joint-capacity optimization. Costs and limitations?",order_id="76a948cd")
                self.assertEqual(answer["context"],"joint_capacity")
                self.assertEqual(answer["evidence_source"],SOURCE)
                self.assertIn("$230,037.00",answer["answer"])
                self.assertEqual(answer["permitted_action"],"NONE")
                follow=ask("Which suppliers were used and how much capacity remains?",
                           context="auto",last_context="joint_capacity",order_id="76a948cd")
                self.assertEqual(follow["context"],"joint_capacity")
                self.assertIn("SUP-014", follow["answer"])
                blocked=ask("Can we switch suppliers to reduce this Olist order's risk using joint-capacity?",
                            context="auto",order_id="76a948cd")
                self.assertEqual(blocked["routing_mode"],"SAFETY_GATE")
                self.assertNotIn("$230,037.00", blocked["answer"])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)
            app.STORE=old

    def test_unavailable_source_not_fabricated(self):
        with patch.object(app,"get_joint_evidence",side_effect=OSError("missing source")):
            answer=app.research_answer("Explain joint-capacity costs",context="auto")
        self.assertEqual(answer["context"],"joint_capacity")
        self.assertEqual(answer["routing_mode"],"JOINT_SOURCE_UNAVAILABLE_SAFE_FALLBACK")
        self.assertNotIn("$230,037",answer["answer"])
        self.assertEqual(answer["permitted_action"],"NONE")


if __name__=="__main__":unittest.main()
