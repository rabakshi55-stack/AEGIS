import json
import unittest
from decimal import Decimal
from intake import LocalDataset, IntakeStore
from dataset_queries import numeric, date_key, basic_plan, execute
from dataset_overview import asks_for_overview
from hosted_copilot import ReadOnlyDataset, ask_hosted
from cohort_analysis import checked_cohort

class Fake:
    def __init__(self,*answers): self.answers=iter(answers)
    def complete(self,messages): return json.dumps(next(self.answers))

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.ds=LocalDataset('audit.csv',b'group,quantity,date\nA,"1,000",2026-01-01\nA,"1,2",2026-02-30\nB,0,2026-02-01\nC,bad,2026-02-02\n')
    def test_numeric(self):
        self.assertEqual(numeric('1,234.50'),Decimal('1234.50'))
        self.assertEqual(numeric(0),Decimal(0))
        for bad in ('1,2','1,23,456','NaN','Infinity','1e99','bad'):
            self.assertIsNone(numeric(bad),bad)
    def test_strict_calendar(self):
        self.assertEqual(date_key('2026-02-01','month'),'2026-02')
        for bad in ('2026-02-30','01/02/2026','2026-13-01','2026-01-01 junk'):
            self.assertIsNone(date_key(bad),bad)
    def test_scope_not_silently_lost(self):
        self.assertIsNone(basic_plan('total quantity in West',self.ds))
        self.assertEqual(basic_plan('total quantity',self.ds)['operation'],'sum')
        self.assertFalse(asks_for_overview('Analyze the dataset excluding group A'))
        self.assertFalse(asks_for_overview('Explain predictive analytics'))
        self.assertTrue(asks_for_overview('What is happening in the data?'))
    def test_missing_group_sum_not_zero(self):
        e=execute(self.ds,{'operation':'group_sum','group_by':['group'],'column':'quantity'})
        g={x['group']['group']:x for x in e['result']}
        self.assertEqual(g['A']['value'],1000); self.assertEqual(g['B']['value'],0)
        self.assertIsNone(g['C']['value']); self.assertEqual(g['C']['numeric_rows'],0)
    def test_missing_marker_distinct_from_real_label(self):
        d=LocalDataset('x.csv',b'group,quantity\n[missing/invalid],1\n,2\n')
        e=execute(d,{'operation':'group_count','group_by':['group']})
        self.assertEqual({x['group']['group'] for x in e['result']},{None,'[missing/invalid]'})
    def test_sql_explicit_conversions(self):
        d=ReadOnlyDataset(self.ds)
        try:
            with self.assertRaises(ValueError): d.query('SELECT SUM(c2) AS total FROM dataset')
            self.assertEqual(d.query('SELECT SUM(aegis_num(c2)) AS total, COUNT(aegis_num(c2)) AS valid FROM dataset')['rows'],[[1000,2]])
            self.assertEqual(d.query('SELECT COUNT(date(c3)) AS valid FROM dataset')['rows'],[[3]])
            with self.assertRaises(ValueError): d.query('SELECT c1 AS x,c2 AS x FROM dataset')
        finally: d.close()
    def test_rank_hiding_rejected(self):
        d=ReadOnlyDataset(self.ds)
        try:
            for sql in ('SELECT * FROM (SELECT c1 FROM dataset LIMIT 1)', 'SELECT c1, ROW_NUMBER() OVER (ORDER BY c1) AS rn FROM dataset'):
                with self.assertRaises(ValueError): d.query(sql)
            e=d.query('SELECT c1 AS label, COUNT(*) AS n FROM dataset GROUP BY c1 ORDER BY n ASC LIMIT 1')
            self.assertEqual(len(e['rows']),2)
        finally: d.close()
    def test_scalar_disagrees_with_model(self):
        f=Fake({'kind':'query','sql':'SELECT COUNT(*) AS n FROM dataset WHERE c1 = \'A\''},{'kind':'answer','answer':'There are two rows.','basis':'evidence'})
        r=ask_hosted(self.ds,'How many rows?',[],1,f)
        self.assertEqual(r['checked_scalar'][0]['result'],4)
        self.assertNotIn('There are two rows',r['answer']); self.assertNotIn('analysis_evidence',r)
    def test_mapping_increments_revision(self):
        store=IntakeStore(); store.dataset=self.ds; rev=store.revision
        store.mapping({'required_units':'quantity'})
        self.assertEqual(store.revision,rev+1)
    def test_cohort_coverage(self):
        d=LocalDataset('s.csv',b'order_id,supplier,quantity,unit_cost,promised_delivery_date,actual_delivery_date\na,Gamma,10,23,2026-01-01,2026-01-02\nb,Gamma,9,27,2026-01-01,\n')
        r=checked_cohort(d,'supplier'); g=r['groups'][0]
        self.assertEqual((g['rows'],g['comparable'],g['quantity'],g['cost']),(2,1,'19','473'))
        self.assertEqual(r['currency'],'unspecified')
        self.assertIn('not evidence of a systematic reliability problem',r['answer'])
