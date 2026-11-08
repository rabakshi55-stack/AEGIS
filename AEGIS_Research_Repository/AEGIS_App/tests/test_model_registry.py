"""Research benchmark selection & explicit score safety tests."""
import copy, json, unittest
from unittest.mock import patch
import model_registry

class TestModelRegistry(unittest.TestCase):
    def test_benchmark_record(self):
        r=model_registry.collect_report()
        self.assertGreaterEqual(r['models_tested_successfully'],20)
        self.assertEqual(r['business_execution'],'DISABLED')
        self.assertFalse(r['prospective_performance_certified'])
        self.assertEqual(r['sorted_candidates'][0],r['selected_algorithm'])
        self.assertTrue(any('svm' in x['name'] for x in r['sorted_candidates']))
    def test_missing_acknowledgment(self):
        with self.assertRaises(ValueError):model_registry.score_research_snapshot({'snapshot':{}})
    def test_no_implicit_deployment(self):
        self.assertFalse(model_registry.collect_report()['model_used_for_production_predictions'])
    def test_invalid_scoring_snapshot(self):
        if model_registry.collect_report()['frozen_shadow_score_available']:
            with self.assertRaises(ValueError):model_registry.score_research_snapshot({'research_acknowledgement':'RESEARCH_ONLY_NO_BUSINESS_ACTION','snapshot':{'outcome':'delivered'}})
    def test_copilot_benchmark_answer(self):
        r=model_registry.benchmark_copilot_answer('How did SVM perform compared with the best algorithm?')
        self.assertIn('SVM',r['answer'])
        self.assertIn('38 historical classifier',r['answer'])
        self.assertIn('not evidence of a reliably better live predictor',r['answer'])
        self.assertEqual(r['permitted_action'],'NONE')
    def test_unrelated_chat_does_not_get_model_route(self):
        self.assertFalse(model_registry.is_model_selection_question('How many suppliers are in my uploaded file?'))
        self.assertTrue(model_registry.is_model_selection_question('Which model was best?'))
    def test_source_hash_mismatch_rejected(self):
        broad=model_registry._read_json(model_registry.BROAD)
        extra=model_registry._read_json(model_registry.EXTENDED)
        extra['original_source_hashes']={}
        with patch.object(model_registry,'_read_json',side_effect=[broad,extra]):
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                model_registry.collect_report()

if __name__=='__main__':unittest.main()
