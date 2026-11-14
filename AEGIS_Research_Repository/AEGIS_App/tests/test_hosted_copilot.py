import json, os, unittest
from unittest.mock import patch
from intake import LocalDataset
from hosted_copilot import ReadOnlyDataset, ask_hosted, GroqClient, HostedUnavailable

SAMPLE=b'supplier,region,quantity,unit_cost,actual_delivery_date,promised_delivery_date\nAlpha,North,12,25,2026-01-04,2026-01-05\nBeta,South,20,21,2026-01-08,2026-01-06\nAlpha,North,8,24,2026-02-05,2026-02-05\nGamma,West,10,23,2026-02-09,2026-02-08\nBeta,South,14,22,2026-03-04,2026-03-05\nGamma,West,9,27,,2026-03-09\n'
class Fake:
    def __init__(self,*replies):self.replies=iter(replies);self.messages=[]
    def complete(self,messages):self.messages.append(list(messages));return json.dumps(next(self.replies))
def q(sql): return {'kind':'query','sql':sql}
def a(text,basis='evidence'):return {'kind':'answer','answer':text,'basis':basis}
class AgentTests(unittest.TestCase):
    def setUp(self): self.ds=LocalDataset('sample.csv',SAMPLE)
    def test_distinct(self):
        f=Fake(q('SELECT COUNT(DISTINCT c1) AS suppliers FROM dataset'),a('Three suppliers.'))
        r=ask_hosted(self.ds,'How many suppliers are there?',[],1,f)
        self.assertEqual(r['analysis_evidence'][0]['rows'],[[3]])
        self.assertIn('Calculated evidence',r['answer']);self.assertIn('suppliers',r['answer'])
    def test_filter(self):
        r=ask_hosted(self.ds,'How many unique suppliers in North?',[],1,Fake(q("SELECT COUNT(DISTINCT c1) AS suppliers FROM dataset WHERE c2='North'"),a('One.')))
        self.assertEqual(r['analysis_evidence'][0]['rows'],[[1]])
    def test_multistep(self):
        f=Fake(q('SELECT c1, SUM(c3*c4) AS spend FROM dataset GROUP BY c1 ORDER BY spend DESC'),q('SELECT COUNT(*) AS late FROM dataset WHERE julianday(c5)>julianday(c6)'),a('Compare spend and delays.'))
        r=ask_hosted(self.ds,'Compare spending and late deliveries.',[],1,f)
        self.assertEqual(r['analysis_evidence'][0]['rows'][0],['Beta',728]);self.assertEqual(r['analysis_evidence'][1]['rows'],[[2]])
    def test_chart(self):
        conf=dict(chart_type='bar',x='supplier',y='quantity',aggregation='sum',date_grain='none',sort='value_desc',limit=20)
        r=ask_hosted(self.ds,'What chart should I use?',[],7,Fake({'kind':'chart','options':conf},a('Use this chart.')))
        self.assertEqual(r['chart_suggestion']['dataset_revision'],7)
        self.assertEqual(r['chart_suggestion']['options'],conf)
    def test_general(self):
        r=ask_hosted(None,'Explain safety stock.',[],0,Fake(a('Safety stock buffers uncertainty.','general')))
        self.assertEqual(r['context'],'general');self.assertIn('General knowledge',r['answer'])
    def test_followup(self):
        f=Fake(q('SELECT c1, COUNT(*) AS n FROM dataset GROUP BY c1'),a('Here they are.'))
        r=ask_hosted(self.ds,'List them.',[{'question':'How many suppliers?','answer':'3'}],1,f)
        self.assertTrue(any(x['content']=='How many suppliers?' for x in f.messages[0]));self.assertEqual(len(r['analysis_evidence'][0]['rows']),3)
    def test_security(self):
        d=ReadOnlyDataset(self.ds)
        try:
            for sql in ('DELETE FROM dataset','SELECT * FROM sqlite_master','SELECT load_extension(\'x\')','SELECT 1; DROP TABLE dataset','WITH x AS (SELECT * FROM dataset) DELETE FROM dataset','SELECT * FROM pragma_table_info(\'dataset\')','ATTACH DATABASE \'x\' AS other','SELECT randomblob(1000000000)','SELECT 123 AS fake_count'):
                with self.subTest(sql=sql),self.assertRaises(ValueError):d.query(sql)
            self.assertEqual(d.query('SELECT COUNT(*) FROM dataset')['rows'],[[6]])
        finally:d.close()
    def test_model_repair(self):
        r=ask_hosted(self.ds,'Count',[],1,Fake(q('SELECT * FROM nonexistent'),q('SELECT COUNT(*) AS n FROM dataset'),a('Six.')))
        self.assertEqual(r['analysis_evidence'][0]['rows'],[[6]]);self.assertTrue(r['tool_errors'])
    def test_missing(self):
        d=ReadOnlyDataset(self.ds)
        try:self.assertEqual(d.query('SELECT COUNT(c5),COUNT(*) FROM dataset')['rows'],[[5,6]])
        finally:d.close()
    def test_zero_preserved(self):
        d=ReadOnlyDataset(LocalDataset('x.csv',b'vendor_id,quantity\n001,0\n002,3\n'))
        try:self.assertEqual(d.query('SELECT c1,c2 FROM dataset ORDER BY c1')['rows'],[['001',0],['002',3]])
        finally:d.close()
    def test_full_data_and_truncation(self):
        ds=LocalDataset('big.csv',('supplier,quantity\n'+''.join(f'Vendor{i},1\n' for i in range(1000))).encode());d=ReadOnlyDataset(ds)
        try:
            self.assertEqual(d.query('SELECT COUNT(*) FROM dataset')['rows'],[[1000]])
            self.assertTrue(d.query('SELECT c1 FROM dataset')['truncated'])
        finally:d.close()
    def test_session_isolation(self):
        d=ReadOnlyDataset(LocalDataset('new.csv',b'supplier\nZ\n'))
        try:self.assertEqual(d.query('SELECT c1 FROM dataset')['rows'],[['Z']])
        finally:d.close()
    def test_no_fabricated_evidence_without_tools(self):
        with self.assertRaises(HostedUnavailable):ask_hosted(self.ds,'Count suppliers',[],1,Fake(*[a('123')]*4))
    def test_offline_does_not_contact_provider(self):
        with patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'1'}),patch('urllib.request.build_opener') as opener:
            with self.assertRaises(HostedUnavailable):GroqClient('fake').complete([])
            opener.assert_not_called()
    def test_bad_chart(self):
        r=ask_hosted(self.ds,'Chart',[],1,Fake({'kind':'chart','options':{'x':'missing'}},a('Field not present.','clarification')))
        self.assertNotIn('chart_suggestion',r)
    def test_general_not_dataset(self):
        f=Fake(a('General advice','general'));r=ask_hosted(self.ds,'What is safety stock?',[],1,f)
        self.assertEqual(r['evidence_source'],'HOSTED_AI_GENERAL_KNOWLEDGE')
    def test_schema_not_raw(self):
        f=Fake(a('I can help.','general'));ask_hosted(self.ds,'Hello',[],1,f)
        self.assertNotIn('Alpha',f.messages[0][1]['content'])
    def test_partial_evidence_after_provider_quota(self):
        class Partial:
            def __init__(self): self.n=0
            def complete(self,messages):
                self.n+=1
                if self.n==1: return json.dumps(q('SELECT COUNT(*) AS n FROM dataset'))
                raise HostedUnavailable('quota')
        r=ask_hosted(self.ds,'How many rows?',[],1,Partial())
        self.assertEqual(r['analysis_evidence'][0]['rows'],[[6]])
        self.assertEqual(r['routing_mode'],'HOSTED_LLM_PARTIAL_EVIDENCE')
    def test_invalid_plan(self):
        class Broken:
            def complete(self,messages):return 'not json'
        with self.assertRaises(HostedUnavailable):ask_hosted(self.ds,'Hello',[],1,Broken())
if __name__=='__main__':unittest.main()
