import json, unittest
from cloud_engine import CloudWorkspace, SAMPLE
from hosted_copilot import ReadOnlyDataset, HostedUnavailable, ask_hosted
from intake import LocalDataset

class Fake:
    def __init__(self,*responses): self.responses=iter(responses); self.messages=[]
    def complete(self,messages):
        self.messages.append(list(messages))
        r=next(self.responses)
        if isinstance(r,Exception): raise r
        return json.dumps(r)

def query(sql): return {'kind':'query','sql':sql}
def answer(s): return {'kind':'answer','answer':s,'basis':'evidence'}

class RankingTests(unittest.TestCase):
    def setUp(self): self.ds=LocalDataset('example.csv',SAMPLE)
    def calculate(self,sql,ds=None):
        db=ReadOnlyDataset(ds or self.ds)
        try: return db.query(sql)
        finally: db.close()
    def test_original_wrong_answer(self):
        client=Fake(query('SELECT c2 AS supplier, COUNT(*) AS order_count FROM dataset GROUP BY c2 ORDER BY order_count DESC LIMIT 1'),answer('Gamma is the most recurring supplier.'))
        r=ask_hosted(self.ds,'which is the most recurring supplier ?',[],1,client)
        self.assertIn('There is no unique first-place',r['answer'])
        self.assertNotIn('Gamma is the most recurring supplier',r['answer'])
        self.assertEqual(set(tuple(row) for row in r['analysis_evidence'][0]['rows']),{('Alpha',2),('Beta',2),('Gamma',2)})
        self.assertIn('Tied results:',r['answer'])
    def test_unique_winner(self):
        r=self.calculate('SELECT c2 AS supplier, SUM(c4) AS units FROM dataset GROUP BY c2 ORDER BY units DESC LIMIT 1')
        self.assertEqual(r['rows'],[['Beta',34]])
        self.assertFalse(r['ranking']['expanded_for_ties'])
    def test_secondary_sort_not_tiebreak(self):
        r=self.calculate('SELECT c2 AS supplier, COUNT(*) AS n FROM dataset GROUP BY c2 ORDER BY n DESC,supplier ASC LIMIT 1')
        self.assertEqual(r['rows'],[['Alpha',2],['Beta',2],['Gamma',2]])
    def test_ascending_and_top_two(self):
        ds=LocalDataset('other.csv',b'category,value\nA,1\nB,2\nC,2\nD,4\n')
        r=self.calculate('SELECT c1 AS category,c2 AS metric FROM dataset ORDER BY metric ASC LIMIT 2',ds)
        self.assertEqual(r['rows'],[['A',1],['B',2],['C',2]])
        self.assertEqual(r['ranking']['boundary_tie_count'],2)
    def test_large_tie_bounded(self):
        ds=LocalDataset('other.csv',('category,value\n'+''.join(f'V{i:03},1\n' for i in range(60))).encode())
        r=self.calculate('SELECT c1,c2 AS metric FROM dataset ORDER BY metric DESC LIMIT 1',ds)
        self.assertEqual(r['ranking']['boundary_tie_count'],60)
        self.assertEqual(len(r['rows']),25)
        self.assertTrue(r['truncated'])
    def test_hidden_metric_refused(self):
        with self.assertRaisesRegex(ValueError,'alias'):
            self.calculate('SELECT c2 FROM dataset GROUP BY c2 ORDER BY COUNT(*) DESC LIMIT 1')
    def test_provider_failure_keeps_tie(self):
        client=Fake(query('SELECT c2 AS supplier, COUNT(*) AS n FROM dataset GROUP BY c2 ORDER BY n DESC LIMIT 1'),HostedUnavailable('provider unavailable'))
        r=ask_hosted(self.ds,'Top supplier?',[],1,client)
        self.assertIn('There is no unique first-place',r['answer'])
    def test_quoted_alias_and_filtered(self):
        r=self.calculate('SELECT c2 AS supplier,COUNT(*) AS "order count" FROM dataset WHERE c3 != \'West\' GROUP BY c2 ORDER BY "order count" DESC LIMIT 1;')
        self.assertEqual(set(tuple(x) for x in r['rows']),{('Alpha',2),('Beta',2)})
    def test_plain_limit_unchanged(self):
        r=self.calculate('SELECT c2 FROM dataset LIMIT 1')
        self.assertEqual(r['rows'],[['Alpha']]);self.assertNotIn('ranking',r)
    def test_cte_order(self):
        r=self.calculate('WITH counts AS (SELECT c2 AS supplier,COUNT(*) AS n FROM dataset GROUP BY c2) SELECT supplier,n FROM counts ORDER BY n DESC LIMIT 1')
        self.assertEqual(len(r['rows']),3)
    def test_no_offset(self):
        with self.assertRaisesRegex(ValueError,'OFFSET'):
            self.calculate('SELECT c2,COUNT(*) AS n FROM dataset GROUP BY c2 ORDER BY n DESC LIMIT 1 OFFSET 1')
    def test_cloud_workspace(self):
        w=CloudWorkspace(); w.upload('sample.csv',SAMPLE)
        client=Fake(query('SELECT c2 AS supplier,COUNT(*) AS n FROM dataset GROUP BY c2 ORDER BY n DESC LIMIT 1'),answer('Gamma is the sole winner.'))
        r=w.ask('Most recurring supplier?',hosted_client=client)
        self.assertIn('no unique first-place',r['answer'])

if __name__=='__main__':unittest.main()
