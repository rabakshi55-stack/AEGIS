import unittest
from cloud_engine import CloudWorkspace,SAMPLE
from cloud_selfcheck import run_selfcheck
from hosted_copilot import HostedUnavailable

class AuditCloud(unittest.TestCase):
    def test_offline_selfcheck(self):
        self.assertTrue(all(x['Status']=='PASS' for x in run_selfcheck()))
    def test_stale_map_suggestion(self):
        w=CloudWorkspace();w.upload('x.csv',SAMPLE)
        rev=w.store.revision
        w.map({'required_units':'quantity'})
        self.assertGreater(w.store.revision,rev)
        with self.assertRaises(ValueError):w.use_suggestion({'dataset_revision':rev,'kind':'custom'})
    def test_stale_hosted_result_after_remap(self):
        w=CloudWorkspace();w.upload('x.csv',SAMPLE)
        class Changed:
            def complete(self,messages):
                w.map({'required_units':'quantity'})
                return '{"kind":"answer","answer":"Hello","basis":"general"}'
        with self.assertRaisesRegex(ValueError,'changed'):w.ask('Hello',hosted_client=Changed())
        self.assertEqual(w.history,[])
    def test_outage_retains_question(self):
        w=CloudWorkspace();w.upload('x.csv',SAMPLE)
        class Down:
            def complete(self,messages): raise HostedUnavailable('provider unavailable')
        result=w.ask('Which region has most orders?',hosted_client=Down())
        self.assertIn('Standard analytics',result['answer']);self.assertEqual(w.history[-1]['question'],'Which region has most orders?')
