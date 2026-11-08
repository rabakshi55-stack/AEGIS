"""AEGIS local research application — standard library, localhost only.

Run: python app.py
Research data is imported once using export_from_notebook.py in the original
Jupyter environment. This server never trains models or executes procurement.
"""

from collections import Counter
from datetime import datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
from urllib.parse import parse_qs, unquote, urlsplit
import json
import mimetypes
import math
import os
import re
import sys
import urllib.error
import urllib.request
import webbrowser

from connectors import enterprise_connections_status
from conversation import (LocalModelUnavailable, is_social_chat, model_status,
                          natural_answer, social_fallback, social_with_local_qwen,
                          general_with_local_qwen, general_fallback,
                          is_dataset_question_with_local_qwen, plan_chart_with_local_qwen)
from copilot_sessions import SESSIONS
from chart_copilot import answer_for_charts, is_chart_question
from chart_recommendations import recommend_for_question, is_recommendation_question
from historical_outcomes import OUTCOMES, MAX_OUTCOME_UPLOAD_BYTES
from intake import INTAKE, MAX_UPLOAD_BYTES
from dataset_overview import asks_for_overview, is_adequate_overview_reply
from joint_capacity import run as run_synthetic_joint_capacity
from joint_copilot import (SOURCE as JOINT_SOURCE, answer_joint, determine_context,
                          safe_facts as joint_safe_facts, validate_report)
from model_validation import get_evidence
from model_registry import (collect_report as collect_algorithm_benchmark, score_research_snapshot,
                            benchmark_copilot_answer, is_model_selection_question)


ROOT = Path(__file__).resolve().parent
BUNDLE_PATH = ROOT / "data" / "aegis_bundle.json"
WEB_ROOT = ROOT / "web"
HOST = "127.0.0.1"
PORT = int(os.environ.get("AEGIS_PORT", "8787"))
MAX_REQUEST_BYTES = 16_384

EVIDENCE = {
    "historical_order": "REAL_OLIST_HISTORICAL_RESEARCH",
    "headroom": "SYNTHETIC_CAPACITY_FRONTIER_STEPS_155_156",
    "legacy_policy": "SYNTHETIC_SOURCING_PILOT_STEPS_126_139",
    "readiness": "BUSINESS_DATA_CONTRACT_STEP_182",
    "joint_capacity": JOINT_SOURCE,
}

LIMITATIONS = [
    ("Prospective validation", "Not established on future, genuinely unseen orders"),
    ("Probability calibration", "Historical research scores are not reliable probabilities"),
    ("Decision-time provenance", "Original availability of every model feature is not certified"),
    ("Delivery-promise semantics", "Calendar-day interpretation still needs business confirmation"),
    ("Supplier causality", "A delivery score cannot identify a responsible supplier"),
    ("Intervention effectiveness", "Supplier-switching and disruption reduction have not been established"),
    ("Actual operational inputs", "Verified quotes, capacity, eligibility and baseline decisions are missing"),
]


def _canonical_digest(bundle):
    payload = {key: value for key, value in bundle.items() if key != "content_sha256"}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def valid_research_score(value):
    """Reject malformed/non-finite frozen scores before display or sorting."""
    return (type(value) in (int, float) and math.isfinite(value)
            and 0.0 <= value <= 1.0)


class ResearchStore:
    """Read-only validated snapshot of exported notebook research outputs."""

    def __init__(self, path=BUNDLE_PATH):
        self.path = Path(path)
        self.ready = False
        self.error = "Research export not loaded. Run the one-time notebook export."
        self.bundle = {}
        self.orders = []
        self.scenarios = []
        self.policies = []
        self.readiness = []
        self.by_raw = {}
        self.by_short = {}
        self.short_by_raw = {}
        self.summary = {}
        if self.path.is_file():
            self.load()

    def load(self):
        try:
            bundle = json.loads(self.path.read_text(encoding="utf-8"))
            if bundle.get("schema_version") != 1 or bundle.get("product") != "AEGIS":
                raise ValueError("Unsupported AEGIS research bundle schema.")
            if _canonical_digest(bundle) != bundle.get("content_sha256"):
                raise ValueError("Research export integrity check failed.")
            if bundle.get("safety", {}).get("permitted_action") != "NONE":
                raise ValueError("The research-only safety contract is missing.")
            if bundle.get("safety", {}).get("operational_approval") != "NOT_GRANTED":
                raise ValueError("The operational safety contract is missing.")

            raw_ids = bundle["original_order_ids"]
            orders = bundle["research_orders"]
            scenarios = bundle["scenarios"]
            if len(raw_ids) != 99441 or len(set(raw_ids)) != len(raw_ids):
                raise ValueError("Original source-order reconciliation failed.")
            if len(orders) != 58911 or len(scenarios) != 10:
                raise ValueError("Frozen research population reconciliation failed.")

            all_source_ids = set(raw_ids)
            by_raw = {}
            by_short = {}
            short_by_raw = {}
            for item in orders:
                raw = str(item["order_id"])
                short = str(item["Short_Reference"])
                score = item.get("Research_Score_Uncalibrated")
                if raw in by_raw or raw not in all_source_ids:
                    raise ValueError("Research IDs are duplicated or not in the source registry.")
                if short in by_short or not valid_research_score(score):
                    raise ValueError("Invalid unique display reference or score.")
                by_raw[raw] = item
                by_short[short] = raw
                short_by_raw[raw] = short

            self.bundle = bundle
            self.orders = orders
            self.scenarios = sorted(scenarios, key=lambda row: row["Rank"])
            self.policies = bundle["policies"]
            self.readiness = bundle["readiness"]
            self.by_raw = by_raw
            self.by_short = by_short
            self.short_by_raw = short_by_raw
            phases = Counter(str(row["Phase"]) for row in orders)
            states = Counter(str(row["Destination_State"]) for row in orders)
            scores = [float(row["Research_Score_Uncalibrated"]) for row in orders]
            max_score = max(scores)
            min_score = min(scores)
            span = max(max_score - min_score, 1e-10)
            bars = [0] * 12
            for score in scores:
                bars[min(11, int((score - min_score) / span * 12))] += 1
            self.summary = {
                "source_orders": len(raw_ids),
                "scored_orders": len(orders),
                "scenarios": len(scenarios),
                "policies": len(self.policies),
                "phase_counts": dict(phases),
                "top_states": [{"name": key, "count": value} for key, value in states.most_common(8)],
                "score_histogram": bars,
                "score_min": min_score,
                "score_max": max_score,
                "coverage_pct": round(len(orders) / len(raw_ids) * 100, 2),
            }
            self.ready = True
            self.error = None
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            self.ready = False
            self.error = f"Research export unavailable: {error}"

    def status(self):
        return {
            "ready": self.ready,
            "message": self.error,
            "app": "AEGIS",
            "mode": "Retrospective research only",
            "summary": self.summary if self.ready else None,
            "exported_at": self.bundle.get("exported_at_utc") if self.ready else None,
            "safety": {
                "operational_approval": "NOT_GRANTED",
                "permitted_action": "NONE",
                "human_review": "REQUIRED",
            },
            "limitations": [{"title": a, "detail": b} for a, b in LIMITATIONS],
        }

    def resolve(self, reference):
        text = str(reference or "").strip()
        if text.lower().startswith("order "):
            text = text[6:].strip()
        if text in self.by_raw:
            return text
        return self.by_short.get(text.lower())

    def public_order(self, item, full=False):
        row = {
            "reference": item["Short_Reference"],
            "phase": item["Phase"],
            "purchase_time": item["Purchase_Time"],
            "state": item["Destination_State"],
            "promise_days": item["Promise_Days"],
            "promise_band": item["Promise_Band"],
            "score": item["Research_Score_Uncalibrated"],
        }
        if full:
            row.update({
                "original_order_id": item["order_id"],
                "source": EVIDENCE["historical_order"],
                "score_meaning": "Relative historical ranking, not a calibrated probability.",
                "delivery_outcome": "NOT_INCLUDED_IN_PREDICTION_PACKET",
                "decision_time_certified": False,
                "supplier_causality": "NOT_ESTABLISHED",
                "operational_approval": "NOT_GRANTED",
                "permitted_action": "NONE",
            })
        return row

    def search_orders(self, query):
        needle = str(query.get("q", [""])[0]).strip().lower()[:100]
        if needle.startswith("order "):
            needle = needle[6:].strip()
        phase = str(query.get("phase", ["all"])[0]).upper()
        state = str(query.get("state", ["all"])[0]).upper()
        sort = str(query.get("sort", ["score_desc"])[0])
        try:
            page = max(1, min(10000, int(query.get("page", [1])[0])))
        except (ValueError, TypeError):
            page = 1

        rows = self.orders
        if needle:
            rows = [r for r in rows if needle in r["order_id"] or needle in r["Short_Reference"]]
        if phase != "ALL":
            rows = [r for r in rows if str(r["Phase"]).upper() == phase]
        if state != "ALL":
            rows = [r for r in rows if str(r["Destination_State"]).upper() == state]

        sort_keys = {
            "score_desc": (lambda r: float(r["Research_Score_Uncalibrated"]), True),
            "score_asc": (lambda r: float(r["Research_Score_Uncalibrated"]), False),
            "date_desc": (lambda r: str(r["Purchase_Time"]), True),
            "date_asc": (lambda r: str(r["Purchase_Time"]), False),
        }
        key, descending = sort_keys.get(sort, sort_keys["score_desc"])
        rows = sorted(rows, key=key, reverse=descending)
        total = len(rows)
        page_size = 12
        selected = rows[(page - 1) * page_size : page * page_size]
        return {
            "items": [self.public_order(row) for row in selected],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }


STORE = ResearchStore()


def rule_intent(question):
    text = question.lower()
    if any(t in text for t in ("switch", "reallocat", "purchase", "recommend supplier", "procure", "execute")):
        return "ACTION"
    if any(t in text for t in ("why", "caus", "responsib", "seller", "carrier")):
        return "CAUSE"
    if any(t in text for t in ("delivered", "actually late", "outcome", "arrive")):
        return "OUTCOME"
    if any(t in text for t in ("reliable", "valid", "accurac", "trust", "production", "real world")):
        return "VALIDITY"
    if any(t in text for t in ("feature", "input", "which state", "information", "used")):
        return "FEATURES"
    if any(t in text for t in ("order detail", "purchase time", "purchase date", "record")):
        return "ORDER"
    if any(t in text for t in ("score", "risk", "rank", "predict")):
        return "SCORE"
    return "GENERAL"


def classify_with_local_qwen(question):
    if os.environ.get("AEGIS_OFFLINE_TEST_MODE") == "1":
        return rule_intent(question), "RULE_BASED_TEST_MODE"
    instruction = (
        "Classify the user's question about an order risk research model. "
        "Reply with EXACTLY ONE uppercase word from: SCORE, FEATURES, CAUSE, "
        "OUTCOME, ACTION, VALIDITY, ORDER, GENERAL. No extra words."
    )
    payload = {
        "model": "qwen3.5:4b",
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": question[:800]},
        ],
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 24},
    }
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read(32768))
        content = str(data.get("message", {}).get("content", "")).strip().upper()
        if content in {"SCORE", "FEATURES", "CAUSE", "OUTCOME", "ACTION", "VALIDITY", "ORDER", "GENERAL"}:
            return content, "LOCAL_QWEN_ROUTING"
    except (OSError, TimeoutError, ValueError, KeyError, urllib.error.URLError):
        pass
    return rule_intent(question), "RULE_BASED_FALLBACK"


def block_cross_source(question):
    text = question.lower()
    refers_to_real = any(t in text for t in ("olist", "historical order", "this order", "order's risk"))
    intervention = any(t in text for t in (
        "switch supplier", "switching suppliers", "change supplier", "reallocate",
        "supplier scenario", "capacity scenario", "sourcing policy", "headroom scenario",
        "joint capacity", "joint-capacity", "joint allocation", "synthetic savings",
    ))
    return refers_to_real and intervention


def block_execution(question):
    text = question.lower()
    return any(t in text for t in (
        "execute procurement", "place purchase order", "automatically purchase",
        "approve supplier change", "execute supplier switch", "automatically switch",
        "place an order", "buy now", "make the purchase", "execute this decision",
    ))


def get_joint_evidence():
    """Live source-derived result shared between Scenario Lab and Copilot.

    No alternate figures, fabricated fallback or source modifications.
    """
    return validate_report(run_synthetic_joint_capacity(ROOT.parent / "Research" / "Integrated_v02", max_nodes=2_000_000))


def research_answer(question, context="historical_order", order_id=None, scenario_id=None,
                    use_local_llm=False, history=None):
    question = str(question or "").strip()
    if not question or len(question) > 1500:
        raise ValueError("Enter a question of 1–1,500 characters.")
    history = history or []
    if not isinstance(history, list) or len(history) > 6 or any(
        not isinstance(item, dict) or not isinstance(item.get("question"), str)
        or len(item["question"]) > 1500 for item in history
    ):
        raise ValueError("Conversation history is invalid or too long.")
    if context not in {"historical_order", "headroom", "legacy_policy", "readiness", "joint_capacity", "auto"}:
        raise ValueError("Unsupported research area.")
    # The same deterministic resolver governs direct calls and the HTTP endpoint.
    # Explicit research terms override stale dropdown context, not the safety gate.
    context = determine_context(question, context, has_order=bool(order_id))

    source = EVIDENCE[context]
    routing = "FROZEN_RESEARCH_RULES"
    if block_cross_source(question) or block_execution(question):
        answer = (
            "I can't make that operational recommendation. The historical Olist "
            "research model and synthetic supplier scenarios do not establish "
            "a causal link or a real-world supplier-switching benefit. "
            "No purchase or business action is authorized."
        )
        source = "CROSS_EVIDENCE_REQUEST_BLOCKED"
        routing = "SAFETY_GATE"
    elif context == "joint_capacity":
        try:
            report = get_joint_evidence()
            answer = answer_joint(question, report, history=history)
            routing = "VERIFIED_SYNTHETIC_JOINT_CAPACITY_EVIDENCE"
        except (OSError, ValueError, KeyError, AssertionError, TypeError, OverflowError) as error:
            answer = ("The synthetic joint-capacity report is unavailable or has failed verification, "
                      "so I cannot provide allocation figures. Check that the original synthetic "
                      "source files are available to Scenario Lab. No business action is authorized.")
            routing = "JOINT_SOURCE_UNAVAILABLE_SAFE_FALLBACK"
            source = "JOINT_CAPACITY_SOURCE_UNAVAILABLE"
    elif context == "historical_order":
        raw = STORE.resolve(order_id)
        if not raw:
            raise ValueError("Select a scored historical order before asking about it.")
        row = STORE.by_raw[raw]
        reference = row["Short_Reference"]
        score = float(row["Research_Score_Uncalibrated"])
        state = row["Destination_State"]
        promise = float(row["Promise_Days"])
        timestamp = row["Purchase_Time"]
        intent, routing = classify_with_local_qwen(question) if use_local_llm else (rule_intent(question), "RULE_BASED_ROUTING")
        previous = history[-1]["question"].lower() if history else ""
        question_lower = question.lower()
        followup_on_outcomes = any(token in previous for token in (
            "delivered", "delivery outcome", "before", "after", "promised date", "estimated date"
        )) and any(token in question_lower for token in (
            "how many", "before", "after", "on time", "late", "what about", "are you sure", "double check"
        ))
        if followup_on_outcomes and not any(token in question_lower for token in (
            "supplier", "switch", "cause", "why", "procure", "purchase"
        )):
            intent = "OUTCOME"
        if any(token in question_lower for token in ("promised date", "estimated date", "early", "before", "after")) \
                and any(token in question_lower for token in ("how many", "orders", "delivery", "delivered", "on time")):
            intent = "OUTCOME"
        answers = {
            "SCORE": f"Order {reference} received a frozen historical research score of {score:.4f}. A higher score means the model ranked it higher relative to other historical orders. The score is not reliably calibrated, so it is not a verified percentage probability of late delivery.",
            "FEATURES": f"For order {reference}, the recorded research inputs include purchase-calendar information, destination state {state}, and a delivery-promise window of {promise:.1f} days. Independent proof that every feature was available at decision time is still missing.",
            "CAUSE": "This model cannot identify which seller, carrier or supplier caused a delay. Calendar, location and promise information do not establish causality. Separate operational evidence is required.",
            "OUTCOME": (
                "The frozen research-score packet doesn't contain actual delivery timestamps, "
                "so I cannot calculate how many original orders arrived before or after their dates from that packet. "
                "To investigate this properly, attach the original 'olist_orders_dataset.csv' under "
                "Historical Order Outcomes in this Copilot. AEGIS will reconcile every source order ID "
                "before counting deliveries against Olist's *estimated* delivery dates."
            ),
            "ACTION": "I cannot recommend switching suppliers, changing allocations or making a purchase from this order's research score. Verified supplier eligibility, capacity, terms, costs and intervention effects would be required. Automatic procurement remains disabled.",
            "VALIDITY": "This is a retrospective research model, not a certified operational forecaster. Its historical performance varied over time, score calibration was inadequate, and prospective performance is unverified. It cannot yet support real supplier decisions.",
            "ORDER": f"Order {reference} is a real historical Olist research record. Recorded purchase timestamp: {timestamp}; destination state: {state}; recorded promise window: {promise:.1f} days. This is not a live order system.",
            "GENERAL": "I can explain the historical score, prediction inputs, order details, model reliability and limitations. I won't invent delivery outcomes, supplier causes or operational recommendations.",
        }
        answer = answers[intent]
        if intent == "OUTCOME":
            source_answer = OUTCOMES.explain(question, order_id=raw, history=history)
            if source_answer is not None:
                answer = source_answer
                source = "REAL_OLIST_ORIGINAL_OUTCOMES_SEPARATE"
                routing = "SOURCE_OUTCOME_CALENDAR_DATE_AUDIT"
    elif context == "headroom":
        selection = None
        if (scenario_id is None or not str(scenario_id).strip()):
            mentioned = re.search(r"\bscenario\s*#?\s*(\d{1,2})\b", question, re.I)
            if mentioned:
                scenario_id = int(mentioned.group(1))
        if scenario_id is not None and str(scenario_id).strip():
            selection = next((r for r in STORE.scenarios if int(r["Scenario"]) == int(scenario_id)), None)
            if selection is None:
                raise ValueError("Scenario not present in the frozen research frontier.")
        else:
            selection = STORE.scenarios[0]
        row = selection
        answer = (
            f"In the synthetic 16-order capacity experiment, Scenario {int(row['Scenario'])} "
            f"ranked {int(row['Rank'])}. Minimum remaining capacity was "
            f"{float(row['Actual_Reserve_Pct']):.2f}%, and the maximum daily quoted-cost "
            f"allowance required was {float(row['Minimum_Allowance_Pct']):.2f}%. "
            f"Estimated synthetic landed cost: ${float(row['Landed_Cost']):,.2f}; "
            f"supplier concentration HHI: {float(row['Supplier_HHI']):.4f}. "
            "These figures do not establish real supplier availability, procurement costs or disruption reduction."
        )
    elif context == "legacy_policy":
        answer = (
            "This section contains the original synthetic sourcing-policy comparisons. "
            "Use the policy evidence table to inspect the measured model outputs for that experiment. "
            "The AI +5% label describes a quoted-cost allowance, not a capacity allocation. "
            "The results cannot be applied directly to historical Olist orders or treated as actual supplier-switching benefits."
        )
    else:
        missing = [str(item["Table"]) for item in STORE.readiness if item.get("Status") != "SCHEMA_PASS"]
        answer = (
            "AEGIS is a research decision-support prototype, not an approved production system. "
            "The current public-data audit does not establish verified operational records for: "
            + (", ".join(missing) if missing else "the required business decision process")
            + ". We still need genuine decision-time inputs, qualified supplier capacity and quotations, "
            "baseline decisions, observed outcomes and an independently evaluated business pilot. "
            "Another generic public dataset is not a substitute for these records."
        )

    return {
        "answer": answer,
        "context": context,
        "evidence_source": source,
        "routing_mode": routing,
        "operational_approval": "NOT_GRANTED",
        "permitted_action": "NONE",
        "human_review": "REQUIRED",
    }


def research_safe_facts(context, order_id=None):
    """Tiny aggregate/selected-research packet for opt-in local wording only."""
    result = {"evidence_context": context, "permitted_business_action": "NONE",
              "operational_approval": "NOT_GRANTED", "certified_operational_forecast": False}
    if context == "joint_capacity":
        try:
            return joint_safe_facts(get_joint_evidence())
        except (OSError, ValueError, KeyError, AssertionError, TypeError, OverflowError):
            return {"evidence_context": "joint_capacity", "source_verified": False,
                    "permitted_business_action": "NONE"}
    if context == "historical_order":
        outcome_counts = OUTCOMES.facts()
        result["source_outcome_counts"] = outcome_counts
        raw = STORE.resolve(order_id)
        if raw:
            selected = STORE.by_raw[raw]
            result["selected_research_score"] = float(selected["Research_Score_Uncalibrated"])
            result["historical_prediction_not_calibrated"] = True
    return result


def copilot_scope(data):
    """Scope session memory to a source; NEVER share it across company uploads."""
    requested = str(data.get("context", "historical_order"))
    if requested == "general" and (INTAKE.question_is_about_upload(data.get("question", ""))
                                  or is_recommendation_question(data.get("question", ""))
                                  or (data.get("chart_catalog") and is_chart_question(
                                      data.get("question", ""), data.get("chart_focus")))):
        requested = "local_dataset"
    if requested == "general":
        return ("general",)
    if is_social_chat(data.get("question", "")):
        return ("social",)
    if requested == "local_dataset":
        dataset = INTAKE.dataset
        return ("local_dataset", id(dataset),
                tuple(sorted(dataset.mapping.items())) if dataset else ())
    resolved = determine_context(str(data.get("question", "")), requested,
                                 last_context=data.get("last_context"),
                                 has_order=bool(data.get("order_id")))
    return (resolved, str(data.get("order_id") or "") if resolved == "historical_order" else "",
            str(data.get("scenario_id") or "") if resolved == "headroom" else "")


class AegisHandler(BaseHTTPRequestHandler):
    server_version = "AEGIS-Local"

    def _copilot_reply(self, result, token, scope, question, checked_answer=None):
        """Only server-generated checked answers enter trusted conversation memory."""
        SESSIONS.remember(token, scope, question, checked_answer or result.get("answer", ""),
                          result.get("context", "general"))
        result["session_id"] = token
        result["conversation_storage"] = "MEMORY_ONLY"
        return self._json(result)

    def log_message(self, fmt, *args):
        # Do not log prompts or order IDs to a file.
        return

    def _discard_rejected_post_body(self):
        """Drain a *small* rejected POST without parsing it.

        HTTP/1.0 closes the connection after a response. On Windows, closing a
        socket with an unread POST body can reset it before clients receive the
        intended 403 status (WinError 10053). This keeps origin/host checks
        first, without giving an untrusted client unlimited read time or size.
        """
        if self.headers.get("Transfer-Encoding"):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return
        if not 0 < length <= MAX_REQUEST_BYTES:
            return
        previous_timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(1.0)
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(remaining, 4096))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (OSError, TimeoutError):
            # Always reject the request, even when its declared body is absent.
            pass
        finally:
            self.connection.settimeout(previous_timeout)

    def _trusted_local_request(self):
        # Reject cross-origin browser requests and DNS-rebinding Host headers.
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin", "")
        return (
            self.headers.get("Host", "") in hosts
            and (not origin or origin in {f"http://{host}" for host in hosts})
            and self.headers.get("Sec-Fetch-Site", "") != "cross-site"
        )

    def _headers(self, status, content_type, size):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _json(self, payload, status=200):
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(content))
        self.wfile.write(content)

    def _static(self, filename):
        if filename not in {"index.html", "styles.css", "app.js", "favicon.ico"}:
            return self._json({"error": "Not found"}, 404)
        path = WEB_ROOT / filename
        try:
            payload = path.read_bytes()
        except OSError:
            return self._json({"error": "Application asset missing"}, 500)
        content_type = mimetypes.guess_type(filename)[0] or "text/plain"
        if filename == "favicon.ico":
            content_type = "image/x-icon"
        else:
            content_type += "; charset=utf-8"
        self._headers(200, content_type, len(payload))
        self.wfile.write(payload)

    def do_GET(self):
        if not self._trusted_local_request():
            return self._json({"error": "Local AEGIS access only."}, 403)
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        args = parse_qs(parsed.query)
        if path in {"/", "/index.html"}:
            return self._static("index.html")
        if path in {"/styles.css", "/app.js", "/favicon.ico"}:
            return self._static(path[1:])
        if path == "/api/status":
            return self._json(STORE.status())
        if path == "/api/connections":
            return self._json(enterprise_connections_status())
        if path == "/api/intake":
            return self._json(INTAKE.status())
        if path == "/api/historical-outcomes":
            return self._json(OUTCOMES.status())
        if path == "/api/local-model":
            return self._json(model_status())
        if path == "/api/model-selection":
            try:
                return self._json(collect_algorithm_benchmark())
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                return self._json({"available": False, "error": "Research benchmark evidence unavailable: " + str(error),
                    "operational_approval":"NOT_GRANTED", "business_execution":"DISABLED"})
        if not STORE.ready:
            if path.startswith("/api/"):
                return self._json({"error": STORE.error, "setup_required": True}, 503)
            return self._json({"error": "Not found"}, 404)
        if path == "/api/model-validation":
            return self._json(get_evidence(expected_count=len(STORE.orders)))
        if path == "/api/joint-capacity":
            # The original synthetic source files are in the parent research folder.
            # Recompute on demand; never mix this with Olist scores or real procurement.
            try:
                report = get_joint_evidence()
                return self._json({"available": True, **report})
            except (OSError, ValueError, KeyError, AssertionError, TypeError) as error:
                return self._json({"available": False, "error": f"Synthetic joint-capacity source not ready: {error}",
                    "operational_approval": "NOT_GRANTED", "automatic_procurement": "DISABLED"})
        if path == "/api/overview":
            return self._json({"summary": STORE.summary, "sources": EVIDENCE})
        if path == "/api/orders":
            return self._json(STORE.search_orders(args))
        if path.startswith("/api/orders/"):
            raw = STORE.resolve(path[len("/api/orders/"):])
            if raw:
                return self._json(STORE.public_order(STORE.by_raw[raw], full=True))
            return self._json({"error": "Not present in the scored research catalog"}, 404)
        if path == "/api/scenarios":
            return self._json({"items": STORE.scenarios, "source": EVIDENCE["headroom"]})
        if path == "/api/policies":
            return self._json({"items": STORE.policies, "source": EVIDENCE["legacy_policy"]})
        if path == "/api/readiness":
            return self._json({"items": STORE.readiness, "source": EVIDENCE["readiness"]})
        return self._json({"error": "Not found"}, 404)

    def do_POST(self):
        endpoint = urlsplit(self.path).path
        if endpoint not in {"/api/copilot", "/api/intake/upload", "/api/intake/mapping", "/api/intake/clear",
                            "/api/historical-outcomes/upload", "/api/historical-outcomes/clear", "/api/intake/sqlite",
                            "/api/research-score", "/api/copilot/reset", "/api/intake/chart"}:
            return self._json({"error": "Actions are not supported"}, 405)
        # Browser attempts from external sites cannot push local data into AEGIS.
        if not self._trusted_local_request():
            self._discard_rejected_post_body()
            return self._json({"error": "Only the local AEGIS interface may submit requests."}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if endpoint in {"/api/intake/upload", "/api/historical-outcomes/upload"}:
                maximum = (MAX_UPLOAD_BYTES if endpoint == "/api/intake/upload" else MAX_OUTCOME_UPLOAD_BYTES)
                if length <= 0 or length > maximum:
                    return self._json({"error": f"File must be non-empty and at most {maximum // (1024 * 1024)} MB."}, 413)
                if self.headers.get("X-AEGIS-Upload") != "1":
                    return self._json({"error": "The protected local upload header is missing."}, 403)
                query = parse_qs(urlsplit(self.path).query)
                filename = query.get("name", [""])[0]
                raw = self.rfile.read(length)
                if endpoint == "/api/intake/upload":
                    return self._json(INTAKE.upload(filename, raw))
                if not STORE.ready:
                    return self._json({"error": "Load your original research bundle first."}, 503)
                return self._json(OUTCOMES.attach(filename, raw, STORE.bundle["original_order_ids"]))
            if not 0 < length <= MAX_REQUEST_BYTES:
                raise ValueError("Request is too large or empty.")
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise ValueError("Expected JSON request.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected an object.")
            if endpoint == "/api/copilot/reset":
                return self._json({"cleared": SESSIONS.clear(data.get("session_id")),
                                   "permitted_action": "NONE"})
            if endpoint == "/api/research-score":
                return self._json(score_research_snapshot(data))
            if endpoint == "/api/intake/sqlite":
                return self._json(INTAKE.sqlite_snapshot(data.get("table")))
            if endpoint == "/api/intake/chart":
                return self._json(INTAKE.chart(data))
            if endpoint == "/api/intake/mapping":
                return self._json(INTAKE.mapping(data.get("mapping")))
            if endpoint == "/api/intake/clear":
                return self._json(INTAKE.clear())
            if endpoint == "/api/historical-outcomes/clear":
                return self._json(OUTCOMES.clear())
            if endpoint == "/api/copilot":
                requested = data.get("context", "historical_order")
                if requested not in {"general", "auto", "historical_order", "headroom", "legacy_policy",
                                     "readiness", "joint_capacity", "local_dataset"}:
                    raise ValueError("Unsupported conversation context.")
                question = data.get("question", "")
                if not isinstance(question, str) or not 0 < len(question.strip()) <= 1500:
                    raise ValueError("Enter a question of 1–1,500 characters.")
                supplied_history = data.get("history", [])
                if not isinstance(supplied_history, list) or len(supplied_history) > 6 or any(
                    not isinstance(item, dict) or not isinstance(item.get("question"), str)
                    or len(item["question"]) > 1500 for item in supplied_history
                ):
                    raise ValueError("Conversation history is invalid or too long.")
                # Dataset-aware routing happens BEFORE choosing a trusted session
                # scope, so company data cannot appear in a general-chat packet.
                if requested == "general" and INTAKE.dataset is not None and not is_social_chat(question):
                    # Prefer obvious data references immediately. Otherwise, an
                    # explicitly enabled local model may recognize unstructured
                    # data questions without relying on a rigid sentence template.
                    refers_to_data = (INTAKE.question_is_about_upload(question) or
                                      is_recommendation_question(question) or
                                      (data.get("chart_catalog") and is_chart_question(
                                          question, data.get("chart_focus"))))
                    if not refers_to_data and data.get("use_local_llm") is True:
                        refers_to_data = is_dataset_question_with_local_qwen(
                            question, list(INTAKE.dataset.columns))
                    if refers_to_data:
                        data["context"] = "local_dataset"
                        requested = "local_dataset"
                scope = copilot_scope(data)
                token, trusted_history = SESSIONS.open(data.get("session_id"), scope)
                # Legacy clients can supply prior questions only on initial turn.
                # Once a token exists, browser-provided history is ignored entirely.
                history = (trusted_history if data.get("session_id") else supplied_history)
                if requested == "general":
                    answer = general_fallback(question)
                    routing = "LOCAL_QWEN_NOT_ENABLED"
                    if data.get("use_local_llm") is True:
                        try:
                            answer = general_with_local_qwen(question, history)
                            routing = "LOCAL_QWEN_GENERAL_CONVERSATION"
                        except LocalModelUnavailable:
                            routing = "LOCAL_QWEN_GENERAL_UNAVAILABLE"
                    result = {"answer": answer, "context": "general",
                              "evidence_source": "GENERAL_KNOWLEDGE_NO_COMPANY_DATA",
                              "routing_mode": routing,
                              "notice": "General chat is not verified supply-chain evidence.",
                              "operational_approval": "NOT_GRANTED", "permitted_action": "NONE",
                              "human_review": "REQUIRED"}
                    return self._copilot_reply(result, token, scope, question)
            else:
                raise ValueError("Unexpected endpoint")
            if endpoint == "/api/copilot" and data.get("context", "auto") not in {"local_dataset", "general"} \
                    and is_model_selection_question(data.get("question", "")):
                if data.get("use_local_llm") is True:
                    # LLM cannot rewrite benchmark figures; deterministic, source-checked response.
                    pass
                result = benchmark_copilot_answer(data.get("question", ""))
                return self._copilot_reply(result, token, scope, question)
            if is_social_chat(data.get("question", "")):
                answer = social_fallback(data.get("question"))
                routing = "FRIENDLY_CONVERSATION_FALLBACK"
                if data.get("use_local_llm") is True:
                    try:
                        answer = social_with_local_qwen(data.get("question"), history)
                        routing = "LOCAL_QWEN_CASUAL_CONVERSATION"
                    except LocalModelUnavailable:
                        routing = "FRIENDLY_CONVERSATION_MODEL_UNAVAILABLE"
                return self._copilot_reply({
                    "answer": answer, "context": data.get("context", "historical_order"),
                    "evidence_source": "SOCIAL_DIALOGUE_NO_BUSINESS_DATA",
                    "routing_mode": routing, "operational_approval": "NOT_GRANTED",
                    "permitted_action": "NONE", "human_review": "REQUIRED",
                }, token, scope, question)
            requested_context = data.get("context", "historical_order")
            if requested_context not in {"auto", "historical_order", "headroom", "legacy_policy",
                                         "readiness", "joint_capacity", "local_dataset"}:
                raise ValueError("Unsupported research area.")
            last_context = data.get("last_context")
            if last_context is not None and last_context not in {"historical_order", "headroom", "legacy_policy",
                                                               "readiness", "joint_capacity", "local_dataset"}:
                raise ValueError("Invalid previous research context.")
            actual_context = determine_context(str(data.get("question", "")), requested_context,
                                               last_context=last_context, has_order=bool(data.get("order_id")))
            if actual_context == "local_dataset":
                # Explicit action requests retain the existing, strict refusal.
                # Otherwise Qwen may plan read-only queries over *all* uploaded
                # records, with execution handled by a bounded trusted engine.
                question_text = str(data.get("question", ""))
                operational_request = block_execution(question_text) or any(
                    phrase in question_text.lower() for phrase in (
                        "switch supplier", "switching suppliers", "recommend supplier",
                        "reallocate suppliers", "approve supplier change", "who caused",
                        "whose fault", "responsible for the delay", "why did the supplier",
                        "field mapping", "map the fields", "mapping based", "which field maps",
                        "what should the mapping"))
                chart_answer = None
                # An objective-driven recommendation is produced from the current
                # authorized dataset, not from browser-supplied measurements.
                if not operational_request and is_recommendation_question(question_text, history):
                    with INTAKE.lock:
                        if INTAKE.dataset is None:
                            raise ValueError("Upload a dataset before requesting a chart recommendation.")
                        selected_dataset = INTAKE.dataset
                        selected_revision = INTAKE.revision
                        if data.get("use_local_llm") is True:
                            from dataset_queries import schema as chart_schema
                            selected_schema = chart_schema(selected_dataset)
                    llm_chart = None
                    # Local inference may take time on a laptop: do not block
                    # upload/clear operations while waiting for Ollama.
                    if data.get("use_local_llm") is True:
                        try:
                            llm_chart = plan_chart_with_local_qwen(
                                question_text, selected_schema, history)
                        except LocalModelUnavailable:
                            pass
                    with INTAKE.lock:
                        if INTAKE.dataset is not selected_dataset or INTAKE.revision != selected_revision:
                            raise ValueError("The active dataset changed while the chart was being planned. Ask again using the new file.")
                        chart_answer = recommend_for_question(
                            selected_dataset, question_text, revision=selected_revision,
                            history=history, llm_proposal=llm_chart)
                    result, facts = chart_answer
                    result["routing_mode"] = (result["routing_mode"] if not data.get("use_local_llm")
                        else result["routing_mode"] + "_QWEN_OPT_IN")
                    return self._copilot_reply(result, token, scope, question, result["answer"])
                if not operational_request and data.get("chart_catalog"):
                    # The browser submits chart *selectors*, never values. All
                    # measurements are recomputed from the current in-memory upload.
                    with INTAKE.lock:
                        if INTAKE.dataset is None:
                            raise ValueError("Upload a dataset before asking about its charts.")
                        chart_answer = answer_for_charts(
                            INTAKE.dataset, question_text, data.get("chart_catalog"),
                            data.get("chart_focus"), dataset_revision=data.get("dataset_revision"),
                            current_revision=INTAKE.revision, history=history)
                queried = (chart_answer if chart_answer is not None else
                           (None if operational_request else INTAKE.query_analysis(
                               question_text, history=history,
                               use_local_llm=data.get("use_local_llm") is True)))
                result, facts = (queried if queried is not None else
                                 INTAKE.explain(data.get("question"), history=history))
                checked_answer = result["answer"]
                if data.get("use_local_llm") is True and not result["safety_gate"]:
                    try:
                        proposed_answer = natural_answer(
                            str(data.get("question")), result["answer"],
                            facts, history,
                        )
                        # A fluent but vague answer is not an adequate answer
                        # to a broad dataset-overview question. Keep the
                        # verified descriptive summary if Qwen omits its facts.
                        if result.get("overview") and not is_adequate_overview_reply(
                                proposed_answer, result["overview"]):
                            raise LocalModelUnavailable("Local reply omitted checked dataset findings.")
                        result["answer"] = proposed_answer
                        result["routing_mode"] = (
                            "LOCAL_QWEN_PLANNED_AND_GROUNDED_ANALYSIS"
                            if result.get("analysis") else "LOCAL_QWEN_GROUNDED_CONVERSATION")
                    except LocalModelUnavailable:
                        result["routing_mode"] = "CONTEXTUAL_RULES_MODEL_UNAVAILABLE"
                        result["notice"] = (
                            "Local Qwen was unavailable or its reply failed grounding checks. "
                            "AEGIS used the checked research explanation instead."
                        )
                return self._copilot_reply(result, token, scope, question, checked_answer)
            if not STORE.ready:
                return self._json({"error": STORE.error}, 503)
            result = research_answer(
                question=data.get("question"),
                context=actual_context,
                order_id=data.get("order_id"),
                scenario_id=data.get("scenario_id"),
                use_local_llm=False,
                history=history,
            )
            checked_answer = result["answer"]
            if data.get("use_local_llm") is True and result["routing_mode"] not in {"SAFETY_GATE", "JOINT_SOURCE_UNAVAILABLE_SAFE_FALLBACK"} \
                    and rule_intent(str(data.get("question", ""))) != "ACTION" \
                    and not block_execution(str(data.get("question", ""))):
                try:
                    suggested = natural_answer(
                        str(data.get("question")), result["answer"],
                        research_safe_facts(result["context"], data.get("order_id")), history,
                    )
                    if result["context"] == "joint_capacity":
                        lowered = suggested.lower()
                        if "synthetic" not in lowered or not any(t in lowered for t in ("not real", "not verified", "not actual", "unproven")):
                            raise LocalModelUnavailable("Local response omitted the synthetic evidence warning.")
                    result["answer"] = suggested
                    result["routing_mode"] = "LOCAL_QWEN_GROUNDED_CONVERSATION"
                except LocalModelUnavailable:
                    result["notice"] = "Local Qwen was unavailable or failed a grounding check; I used the checked explanation."
            return self._copilot_reply(result, token, scope, question, checked_answer)
        except (ValueError, TypeError, json.JSONDecodeError, KeyError) as error:
            return self._json({"error": str(error), "permitted_action": "NONE"}, 400)


def run_server(open_browser=True):
    try:
        server = ThreadingHTTPServer((HOST, PORT), AegisHandler)
    except OSError as error:
        raise SystemExit(f"Cannot open localhost port {PORT}: {error}")
    url = f"http://{HOST}:{PORT}/"
    print("\nAEGIS — LOCAL RESEARCH APPLICATION")
    print("Address:", url)
    print("Research export:", "VERIFIED" if STORE.ready else "NOT LOADED")
    if STORE.error:
        print("Setup:", STORE.error)
    print("External network hosting: DISABLED")
    print("Operational execution: DISABLED")
    print("Press Ctrl+C to close AEGIS.\n")
    if open_browser:
        Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("AEGIS closed.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server(open_browser="--no-browser" not in sys.argv)
