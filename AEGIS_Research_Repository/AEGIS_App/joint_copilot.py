"""Grounded conversation routing for the *synthetic* joint-capacity experiment.

No predictions, source writes, supplier actions, or external network calls.
The reported figures must come from the same verified solver as Scenario Lab.
"""
import re

SOURCE = "SYNTHETIC_JOINT_MONTHLY_CAPACITY_CMP_007_2025_07"

_JOINT = (
    "joint capacity", "joint-capacity", "joint allocation", "whole-order allocation",
    "whole order allocation", "whole-order", "jointly feasible", "joint optimizer",
    "joint optimisation", "joint optimization", "monthly component capacity",
    "capacity-constrained allocation", "capacity constrained allocation",
    "16-order capacity", "16 order capacity", "cmp-007",
)
_LEGACY = ("scenario 9", "scenario 1", "scenario 2", "scenario 3", "scenario 4",
           "scenario 5", "scenario 6", "scenario 7", "scenario 8", "scenario 10",
           "headroom", "capacity frontier", "reserve target", "rank 1")


def joint_requested(question):
    text = str(question or "").lower()
    if any(term in text for term in _JOINT):
        return True
    return (("july 2025" in text or "2025-07" in text)
            and any(term in text for term in ("allocat", "optim", "suppl", "capacit")))


def legacy_scenario_requested(question):
    text = str(question or "").lower()
    return any(term in text for term in _LEGACY) or bool(re.search(r"\bscenario\s*#?\s*\d+\b", text))


def explicit_subject(question):
    """Only unambiguous mentions override the user's selected context."""
    text = str(question or "").lower()
    joint = joint_requested(text)
    old = legacy_scenario_requested(text)
    # A comparison asks for joint evidence with explicit non-comparability.
    if joint:
        return "joint_capacity"
    if old:
        return "headroom"
    if any(s in text for s in ("olist", "historical order", "order's risk", "order score")):
        return "historical_order"
    if any(s in text for s in ("uploaded dataset", "my dataset", "uploaded csv")):
        return "local_dataset"
    if any(s in text for s in ("sourcing policy", "policy research", "ai +5%", "ai + 5%")):
        return "legacy_policy"
    if any(s in text for s in ("data readiness", "deployment readiness", "production readiness")):
        return "readiness"
    return None


def determine_context(question, selected, last_context=None, has_order=False):
    """Explicit topic beats dropdown; otherwise preserve explicit area or safe follow-ups.

    Uploaded data never leaks into other contexts automatically. A cross-source
    business action is blocked separately by the app's safety gate.
    """
    subject = explicit_subject(question)
    if selected == "local_dataset":
        return "local_dataset"
    # Historical order ID is not evidence of permission to use its score for sourcing.
    if subject == "local_dataset":
        return "local_dataset" if selected == "auto" else selected
    if subject:
        return subject
    if selected != "auto":
        return selected
    if last_context in {"joint_capacity", "headroom", "legacy_policy", "readiness", "historical_order"}:
        return last_context
    return "historical_order" if has_order else "readiness"


def validate_report(report):
    """Reject incomplete or non-reconciled source reports; never invent figures."""
    if not isinstance(report, dict) or report.get("experiment") != "SYNTHETIC_COMPONENT_MONTH_JOINT_CAPACITY":
        raise ValueError("Joint-capacity source evidence missing or wrong experiment.")
    scope = report.get("scope")
    if not isinstance(scope, dict) or scope.get("component") != "CMP-007" or scope.get("month") != "2025-07":
        raise ValueError("Unexpected joint-capacity experiment scope.")
    if report.get("automatic_procurement") != "DISABLED" or report.get("operational_approval") != "NOT_GRANTED":
        raise ValueError("Synthetic safety contract is missing.")
    if report.get("status") != "EXACT_MIN_COST_MONTHLY_SYNTHETIC" or report.get("exact_cost_optimum_certified_for_synthetic_problem") is not True:
        raise ValueError("An exact synthetic joint-capacity result has not been certified.")
    checks = report.get("checks", {})
    if not all(checks.get(k) is True for k in ("all_order_assignments", "only_eligible_source_candidates",
                                                "all_monthly_capacities_respected", "candidate_cost_reconciles")):
        raise ValueError("Joint-capacity evidence failed its source consistency checks.")
    reference = report.get("independent_exact_reference", {})
    if reference.get("matches_solver") is not True:
        raise ValueError("Independent reference does not verify the synthetic optimum.")
    for key in ("baseline_landed_cost_usd", "result_landed_cost_usd", "hypothetical_cost_difference_usd"):
        if type(report.get(key)) not in (int, float) or not (0 <= report[key] < 1e15):
            raise ValueError("Invalid synthetic financial evidence.")
    if abs(report["baseline_landed_cost_usd"] - report["result_landed_cost_usd"]
           - report["hypothetical_cost_difference_usd"]) > 0.011:
        raise ValueError("Synthetic cost difference does not reconcile.")
    caps = report.get("capacity_by_supplier")
    if not isinstance(caps, dict) or not caps:
        raise ValueError("Supplier capacity evidence is missing.")
    if sum(v["assigned_units"] for v in caps.values()) != scope.get("total_order_units"):
        raise ValueError("Joint allocation units do not reconcile.")
    if any(v["assigned_units"] < 0 or v["remaining_units"] < 0 or
           v["monthly_capacity_units"] != v["assigned_units"] + v["remaining_units"]
           for v in caps.values()):
        raise ValueError("Monthly capacity evidence is inconsistent.")
    return report


def safe_facts(report):
    """Only aggregate checked evidence for optional local LLM wording."""
    r = validate_report(report)
    return {
        "research_context": "synthetic_joint_capacity_not_real_savings",
        "component": r["scope"]["component"], "month": r["scope"]["month"],
        "whole_orders": r["scope"]["orders"], "total_units": r["scope"]["total_order_units"],
        "baseline_synthetic_usd": r["baseline_landed_cost_usd"],
        "joint_synthetic_usd": r["result_landed_cost_usd"],
        "hypothetical_difference_usd": r["hypothetical_cost_difference_usd"],
        "monthly_supplier_capacity_checks_passed": True,
        "suppliers": {s: {"allocated_units":v["assigned_units"], "remaining_units":v["remaining_units"],
                           "monthly_capacity_units":v["monthly_capacity_units"]}
                      for s,v in r["capacity_by_supplier"].items()},
        "daily_and_multi_component_capacity_verified": False,
        "real_quote_or_supplier_benefit_proven": False,
        "permitted_business_action": "NONE",
    }


def answer_joint(question, report, history=None):
    """Deterministic factual answer from the same solver used by Scenario Lab."""
    r = validate_report(report)
    q = str(question or "").lower()
    # Last user question is context for elliptical follow-ups; prior answers are
    # untrusted client strings and are never used as evidence.
    previous = ""
    if isinstance(history, list) and history and isinstance(history[-1], dict):
        previous = str(history[-1].get("question", "")).lower()[:1500]
    elliptical = q.strip(" ?!.,") in {"why", "how", "why not", "what next", "and why", "explain", "what about that", "what about them"}
    if elliptical and any(token in previous for token in ("switch", "supplier change", "reallocat")):
        q = "why not switch suppliers? what must be verified first?"
    scope = r["scope"]
    caveat = ("This is a synthetic, component-month optimization—not verified real savings or a supplier "
              "recommendation. Daily commitments, capacity shared with other components, actual supplier "
              "eligibility and quotations, and causal delivery improvements are not established. "
              "No business action is authorized.")
    amounts = (f"The baseline modeled cost was ${r['baseline_landed_cost_usd']:,.2f}; "
               f"the optimized modeled cost was ${r['result_landed_cost_usd']:,.2f}. "
               f"The difference is a hypothetical ${r['hypothetical_cost_difference_usd']:,.2f}.")
    summary = (f"For synthetic component {scope['component']} in {scope['month']} (July 2025), "
               f"AEGIS allocated {scope['orders']} whole orders totaling {scope['total_order_units']:,} units "
               f"within the modeled monthly supplier capacities. {amounts} The exact minimum cost for "
               "this limited synthetic problem was checked against an independent knapsack reference.")
    caps = r["capacity_by_supplier"]
    active = [(supplier, v) for supplier, v in sorted(caps.items()) if v["assigned_units"] > 0]
    capacity_text = "; ".join(
        f"{supplier}: {v['assigned_units']:,} of {v['monthly_capacity_units']:,} units allocated "
        f"({v['remaining_units']:,} remaining)" for supplier,v in active)
    # Decision-focused follow-ups are deliberately separate from cost summaries.
    # These are procedural verification requirements, NOT a real-world supplier action.
    switching = any(t in q for t in (
        "switch supplier", "switching supplier", "change supplier", "reallocat",
        "move to another supplier", "use the cheaper supplier", "should we switch",
        "why shouldn't", "why shouldnt", "why not switch", "why can't we switch",
        "why cant we switch", "act on the saving", "act on the savings",
    ))
    decision_check = any(t in q for t in (
        "verify", "verified first", "before", "risk", "why", "should",
        "require", "prove", "need", "ready", "immediately", "decision",
        "recommend", "is it safe",
    ))
    proof_request = any(t in q for t in (
        "what must be checked", "what needs to be checked", "what must we check",
        "what needs verifying", "what exactly needs", "what must be verified",
        "what should we verify", "what to verify", "next checks",
        "how do we validate", "how to validate", "evidence missing",
        "missing evidence", "evidence is missing", "what do we need", "what is needed",
    ))
    if (switching and decision_check) or proof_request:
        return (
            f"The ${r['hypothetical_cost_difference_usd']:,.2f} difference is a synthetic "
            "cost comparison for one component and one month, not money saved by a business. "
            "That alone is not a reason to change suppliers. Before management could evaluate "
            "a real alternative, it would need to verify: "
            "(1) approved supplier and item eligibility, terms and genuine time-valid quotations; "
            "(2) available daily and shared multi-item capacity after existing commitments; "
            "(3) inventory, transport routes, delivery cutoffs and promised arrival dates; "
            "(4) complete landed and switching costs under the same assumptions; and "
            "(5) independently observed delivery and recovery performance, with a fair comparison "
            "against the current sourcing policy. The existing solver verified modeled monthly "
            "capacity only. None of those real operational conditions or causal benefits are proven. "
            "The next safe step is a source-system evidence audit and a human-reviewed pilot—not "
            "an immediate purchase or supplier switch. Business actions remain disabled."
        )
    if any(x in q for x in ("why is it cheaper", "how did you calculate", "how was it calculated",
                              "how calculated", "break down the cost", "show the maths", "show the math",
                              "where does the difference", "how is the difference")):
        return (
            f"For the synthetic July 2025 component-month assignment, subtract the optimized "
            f"modeled landed cost (${r['result_landed_cost_usd']:,.2f}) from the modeled "
            f"baseline (${r['baseline_landed_cost_usd']:,.2f}). That gives "
            f"${r['hypothetical_cost_difference_usd']:,.2f}. The optimization minimized "
            "declared landed cost subject to eligibility and monthly capacity constraints. "
            "This calculation says nothing about real quotations, switching costs or realized savings. "
            "Business actions remain disabled."
        )
    if any(x in q for x in ("most reliable", "least risky", "lowest risk", "highest risk",
                              "best supplier", "most resilient", "who performs best",
                              "supplier reliability", "quality ranking", "recovery time")):
        return (
            "The checked joint-capacity report does not establish supplier reliability, actual "
            "delivery risk, product quality, or recovery time. It is an exact *cost* solution "
            "for declared synthetic monthly constraints, not a real-world supplier ranking. "
            "To assess resilience, we would need observed delivery and recovery records, "
            "independently verified daily capacities and a comparable prospective pilot. "
            "No business action is authorized."
        )
    if any(x in q for x in ("next step", "what next", "where do we go", "what should we check next",
                              "how to proceed", "what is missing")):
        return (
            "Next, verify current supplier eligibility and quotations in the source system; "
            "confirm daily shared capacities after commitments and eligible transport routes; "
            "then evaluate baseline and candidate policies under the same feasible daily "
            "disruptions. Record decisions before outcomes are known and compare recovery "
            "using an independent pilot. These checks are pending for actual businesses. "
            "Do not make a sourcing change from the fictional monthly result."
        )
    if any(x in q for x in ("scenario 9", "headroom scenario", "older scenario", "frozen scenario", "old scenario")):
        return (summary + " Scenario 9 is a different frozen synthetic frontier experiment with different "
                "decision variables and constraints; its costs must not be substituted for this joint assignment. " + caveat)
    if any(x in q for x in ("what if", "suppose", "reduce capacity", "increase capacity", "change capacity",
                              "another month", "another component", "new allocation", "new scenario")):
        return ("I can explain the verified July 2025 synthetic assignment, but the source report does not "
                "contain a recomputed result for that proposed change. No what-if result or new savings "
                "figure can be claimed without a new, separately verified optimization. " + caveat)
    if any(x in q for x in ("why did", "why these supplier", "supplier chosen", "which supplier", "supplier allocation",
                              "supplier used", "supplier capacity", "remaining capacity", "unused capacity", "allocated where",
                              "allocated to", "capacity left", "remaining units")):
        return (f"The synthetic joint assignment uses {len(active)} suppliers: {capacity_text}. "
                "The solver minimizes modeled landed cost subject to whole-order, eligible-option and "
                "monthly component-capacity constraints. The evidence does not establish why any real "
                "supplier would perform better. " + caveat)
    if any(x in q for x in ("real-world", "real world", "real savings", "actual savings", "causal", "limitations",
                              "limitation", "why not", "certif", "trust", "dependable")) and not any(
         x in q for x in ("how many", "baseline", "optimized costs", "optimised costs", "costs and", "cost difference")):
        return (amounts + " " + caveat +
                " To evaluate a real decision, collect time-valid quotes, capacity net of commitments, "
                "eligible routes, actual delivery outcomes, and independent pilot evidence.")
    if any(x in q for x in ("difference", "cost", "saving", "financial")) and not any(
         x in q for x in ("how many", "order", "units", "allocation")):
        return amounts + " " + caveat
    return summary + " " + caveat
