import unittest
from cloud_engine import CloudWorkspace, SAMPLE

class TestCloud(unittest.TestCase):
    def test_session_isolation(self):
        a,b=CloudWorkspace(),CloudWorkspace()
        a.upload('a.csv',SAMPLE)
        b.upload('b.csv',b'region,quantity\nElsewhere,99\n')
        self.assertEqual(a.store.status()['rows'],6)
        self.assertEqual(b.store.status()['rows'],1)
        a.ask('What does the uploaded dataset say?')
        self.assertEqual(b.history,[])
        a.clear();self.assertIsNotNone(b.store.dataset)
    def test_summary(self):
        a=CloudWorkspace();a.upload('example.csv',SAMPLE)
        self.assertIn('6 rows',a.ask('What does the uploaded dataset say?')['answer'])
    def test_chart(self):
        a=CloudWorkspace();a.upload('example.csv',SAMPLE)
        c=a.add_chart(dict(chart_type='bar',x='supplier',y='quantity',aggregation='sum',date_grain='none',sort='value_desc',limit=20))
        self.assertEqual(sum(x['value'] for x in c['values']),73)
        self.assertTrue(a.ask('What does this chart show?',focus='c:0')['answer'])
    def test_recommendation_revision(self):
        a=CloudWorkspace();a.upload('example.csv',SAMPLE)
        r=a.ask('Which chart should I use to compare quantity by supplier?')
        self.assertIn('chart_suggestion',r)
        a.use_suggestion(r['chart_suggestion'])
        a.upload('another.csv',SAMPLE)
        with self.assertRaises(ValueError):a.use_suggestion(r['chart_suggestion'])
    def test_upload_limit(self):
        a=CloudWorkspace()
        with self.assertRaises(ValueError): a.upload('a.csv',b'x'*(5*1024*1024+1))
    def test_actions_blocked(self):
        a=CloudWorkspace();a.upload('example.csv',SAMPLE)
        r=a.ask('execute procurement')
        self.assertEqual(r['permitted_action'],'NONE')
