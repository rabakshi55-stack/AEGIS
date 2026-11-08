"""Verification must be deterministic even when Ollama is running on Windows."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import conversation


class OfflineIsolationTests(unittest.TestCase):
    def test_no_live_ollama_when_test_mode_is_enabled(self):
        with patch.dict(os.environ, {"AEGIS_OFFLINE_TEST_MODE": "1"}):
            with patch.object(conversation, "urlopen", side_effect=AssertionError("live Ollama call")):
                self.assertFalse(conversation.model_status()["available"])
            self.assertFalse(conversation.is_dataset_question_with_local_qwen(
                "What does the data show?", ["amount", "date"]))
            with self.assertRaises(conversation.LocalModelUnavailable):
                conversation.plan_dataset_with_local_qwen("sum amounts", {"columns": []}, [])
            with self.assertRaises(conversation.LocalModelUnavailable):
                conversation.plan_chart_with_local_qwen("chart amount", {"columns": []}, [])
            with self.assertRaises(conversation.LocalModelUnavailable):
                conversation.general_with_local_qwen("Hello", [])
            with self.assertRaises(conversation.LocalModelUnavailable):
                conversation.natural_answer("Explain", "Three orders", {}, [])

    def test_explicit_mock_opener_remains_usable_in_test_mode(self):
        class FakeReply:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args):
                return b'{"message":{"content":"DATA"}}'
        def fake_open(*args, **kwargs):
            return FakeReply()
        with patch.dict(os.environ, {"AEGIS_OFFLINE_TEST_MODE": "1"}):
            self.assertTrue(conversation.is_dataset_question_with_local_qwen(
                "my dataset", ["amount"], http_open=fake_open))

if __name__ == "__main__":
    unittest.main()
