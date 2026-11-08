"""Privacy-first local conversational continuity for AEGIS.

Only in memory, never logs, cookies, disk, or external services. Conversations
are isolated by the selected source/loaded dataset/mapping. A token is an
opaque session locator, not authorization for business actions.
"""
from collections import OrderedDict
from threading import RLock
from time import monotonic
import secrets


class SessionStore:
    def __init__(self, ttl=3600, maximum=32, turns=6):
        self.lock = RLock()
        self.sessions = OrderedDict()
        self.ttl = ttl
        self.maximum = maximum
        self.turns = turns

    def _purge(self):
        now = monotonic()
        for token in list(self.sessions):
            if now - self.sessions[token]["updated"] > self.ttl:
                self.sessions.pop(token, None)
        while len(self.sessions) >= self.maximum:
            self.sessions.popitem(last=False)

    def open(self, token, scope):
        with self.lock:
            self._purge()
            if isinstance(token, str) and len(token) <= 96:
                entry = self.sessions.get(token)
                if entry and entry["scope"] == scope:
                    entry["updated"] = monotonic()
                    self.sessions.move_to_end(token)
                    return token, [dict(item) for item in entry["history"]]
            token = secrets.token_urlsafe(24)
            self.sessions[token] = {"scope": scope, "updated": monotonic(), "history": []}
            return token, []

    def remember(self, token, scope, question, checked_answer, context):
        with self.lock:
            entry = self.sessions.get(token)
            if not entry or entry["scope"] != scope:
                return
            entry["history"].append({
                "question": str(question)[:1500],
                # A previous answer is never used as new factual evidence.
                "verified_answer": str(checked_answer)[:1600],
                "context": context,
                "trusted": True,
            })
            entry["history"] = entry["history"][-self.turns:]
            entry["updated"] = monotonic()
            self.sessions.move_to_end(token)

    def clear(self, token):
        if not isinstance(token, str) or len(token) > 96:
            return False
        with self.lock:
            return self.sessions.pop(token, None) is not None


SESSIONS = SessionStore()
