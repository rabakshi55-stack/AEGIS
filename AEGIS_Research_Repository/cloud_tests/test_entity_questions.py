import unittest
from cloud_engine import CloudWorkspace, SAMPLE

class EntityQuestions(unittest.TestCase):
    def setUp(self):
        self.w = CloudWorkspace()
        self.w.upload('example.csv', SAMPLE)
    def test_exact_reported_failure(self):
        r=self.w.ask('how many suppliers are there ?')
        self.assertEqual(r['analysis'][0]['result'],3)
        self.assertIn('3 distinct',r['answer'])
        r=self.w.ask('supplier')
        self.assertEqual({x['group']['supplier']:x['value'] for x in r['analysis'][1]['result']},{'Alpha':2,'Beta':2,'Gamma':2})
        self.assertIn('Alpha: 2 rows',r['answer'])
        self.assertIn('Gamma: 2 rows',self.w.ask('list them')['answer'])
    def test_variations(self):
        for q in ('How many unique suppliers are there?', 'How many suppliers do we have?', 'Number of suppliers', 'Count distinct suppliers', 'How many different regions in this dataset?', 'How many unique values in supplier?'):
            with self.subTest(q=q):
                self.assertEqual(self.w.ask(q)['analysis'][0]['result'],3)
        self.assertEqual(self.w.ask('How many rows are there?')['analysis'][0]['result'],6)
    def test_missing_and_full_dataset(self):
        raw='vendor_id,category\n'+''.join(f'V{i%31},C{i%4}\n' for i in range(4000)) + ',C0\n'
        self.w.upload('new.csv',raw.encode())
        r=self.w.ask('How many vendors are there?')['analysis'][0]
        self.assertEqual(r['result'],31);self.assertEqual(r['missing_count'],1);self.assertEqual(r['matched_rows'],4001)
        self.assertEqual(self.w.ask('How many categories are there?')['analysis'][0]['result'],4)
        r=self.w.ask('list vendors')['analysis'][1]
        self.assertTrue(r['result_truncated']); self.assertEqual(r['distinct_groups'],31)
    def test_filter_not_ignored(self):
        for q in ('How many suppliers in North?', 'How many unique suppliers in North?'):
            self.assertNotIn('analysis',self.w.ask(q))
    def test_ambiguous_field_not_invented(self):
        self.w.upload('x.csv',b'supplier_id,supplier_name\nS1,Alpha\nS2,Alpha\n')
        self.assertNotIn('analysis',self.w.ask('How many suppliers are there?'))
        self.assertEqual(self.w.ask('How many supplier IDs are there?')['analysis'][0]['result'],2)
    def test_session_and_replacement(self):
        self.w.ask('how many suppliers are there?')
        w=CloudWorkspace();w.upload('other.csv',b'supplier\nX\n')
        self.assertNotIn('analysis',w.ask('list them'))
        self.w.upload('new.csv',b'supplier\nX\nY\nZ\nW\n')
        self.assertNotIn('analysis',self.w.ask('list them'))
        self.assertEqual(self.w.ask('how many suppliers are there?')['analysis'][0]['result'],4)
