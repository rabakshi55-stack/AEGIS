"""Local conversation tests are mocked; they never call Ollama or a cloud API."""

from io import BytesIO
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import conversation


class GroundedConversationTests(unittest.TestCase):
    def setUp(self):
        self.facts = {"file_rows":4,"file_columns":6,"date_pairs":3,"after_promise":2,
                      "supplier_causality_certified":False,"permitted_business_action":"NONE"}
        self.original = "Of 3 comparable delivery pairs, 2 are recorded after the promise date. Not a certified KPI."

    def mock_reply(self, reply, spy=None):
        def run(request, timeout):
            if spy is not None:
                spy.append(json.loads(request.data))
            return BytesIO(json.dumps({"message":{"content":reply}}).encode())
        return run

    def test_natural_reply_uses_only_derived_packet_and_short_memory(self):
        captured=[]
        reply=conversation.natural_answer(
            "Are you sure?",self.original,self.facts,
            [{"question":"How many were after their promise?", "answer":"SOURCE ROW: SECRET-ABC"}],
            http_open=self.mock_reply("Yes. The source dates show 2 of 3 comparable rows after the promise, but that is not certified.", captured),
        )
        self.assertIn("2 of 3",reply)
        payload=captured[0]
        self.assertEqual(payload["model"],"qwen3.5:4b")
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["messages"][-2]["role"],"user")
        self.assertNotIn("TEST-001",json.dumps(payload))
        self.assertNotIn("SECRET-ABC",json.dumps(payload))

    def test_unverified_new_number_forces_fallback(self):
        with self.assertRaisesRegex(conversation.LocalModelUnavailable,"unsupported numbers"):
            conversation.natural_answer("How late?",self.original,self.facts,[],
                http_open=self.mock_reply("There is a 87% probability the supplier caused it."))

    def test_action_recommendation_is_rejected(self):
        with self.assertRaisesRegex(conversation.LocalModelUnavailable,"action-safety"):
            conversation.natural_answer("What should we do?",self.original,self.facts,[],
                http_open=self.mock_reply("I recommend switching suppliers immediately."))

    def test_empty_model_reply_falls_back(self):
        with self.assertRaisesRegex(conversation.LocalModelUnavailable,"no usable reply"):
            conversation.natural_answer("Explain?",self.original,self.facts,[],
                http_open=self.mock_reply(""))

    def test_casual_chat_is_not_misread_as_data_analysis(self):
        self.assertTrue(conversation.is_social_chat("bruh"))
        self.assertTrue(conversation.is_social_chat("Why are you so robotic?"))
        self.assertFalse(conversation.is_social_chat("Should we switch suppliers?"))
        self.assertFalse(conversation.is_social_chat("How many orders were late?"))
        self.assertIn("robotic",conversation.social_fallback("bruh"))
        packet=[]
        reply=conversation.social_with_local_qwen("bruh",[{"question":"How many were late?",
                 "answer":"Sensitive source outcome: SECRET-123"}],
            http_open=self.mock_reply("Fair 😅, I sounded like a spreadsheet. What's up?",packet))
        self.assertIn("Fair",reply)
        self.assertNotIn("SECRET-123",json.dumps(packet))
        self.assertEqual(packet[0]["messages"][-1]["content"],"bruh")


if __name__ == "__main__":
    unittest.main()
