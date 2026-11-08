"""Frozen research score validation: no training or operational execution."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import valid_research_score, ResearchStore

class FrozenScoreGuardTests(unittest.TestCase):
    def test_valid_scores(self):
        for value in (0, 0.0, 0.5, 1, 1.0):
            self.assertTrue(valid_research_score(value))

    def test_malformed_scores(self):
        for value in (None, False, True, -0.01, 1.0001, float('nan'), float('inf'), -float('inf'), '0.4'):
            self.assertFalse(valid_research_score(value), repr(value))

    def test_existing_frozen_bundle_unmodified_and_valid(self):
        store = ResearchStore()
        self.assertTrue(store.ready, store.error)
        self.assertEqual(len(store.orders), 58911)
        self.assertTrue(all(valid_research_score(x['Research_Score_Uncalibrated']) for x in store.orders))

if __name__ == "__main__":
    unittest.main()
