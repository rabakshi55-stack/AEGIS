"""Regression checks for the post-reviewed-release audit; fictional data only."""
import io, json, unittest, warnings, zipfile
from unittest.mock import patch
from intake import LocalDataset, IntakeStore
from dataset_queries import execute, basic_plan, explain, schema
from custom_charts import build_chart
from hosted_copilot import ReadOnlyDataset, ask_hosted
from test_intake import fake_xlsx

class QueryIngestionReview(unittest.TestCase):
    def setUp(self):
        self.ds=LocalDataset('fiction.csv',b'supplier,tracking,quantity,order_id\nA,X,1,001\nA,,2,002\nB,Y,3,003\nB,,4,004\nC,,5,005\n')
    def test_count_nonblank_vs_rows(self):
        r=execute(self.ds,{'operation':'count','column':'tracking'})
        self.assertEqual((r['result'],r['missing_count'],r['matched_rows']),(2,3,5))
        self.assertIn('2 nonblank',explain([r]))
        self.assertEqual(execute(self.ds,{'operation':'count'})['result'],5)
        self.assertEqual(basic_plan('How many nonblank values in tracking?',self.ds),{'operation':'count','column':'tracking'})
    def test_group_nonblank_counts_preserve_zero(self):
        plan=basic_plan('Count nonblank values in tracking by supplier',self.ds)
        r=execute(self.ds,plan)
        self.assertEqual({x['group']['supplier']:x['value'] for x in r['result']},{'A':1,'B':1,'C':0})
    def test_local_rank_ties_both_directions(self):
        for direction,expected in [('desc',{'A','B'}),('asc',{'C'})]:
            r=execute(self.ds,{'operation':'group_count','group_by':['supplier'],'limit':1,'order':direction})
            self.assertEqual({x['group']['supplier'] for x in r['result']},expected)
        self.assertEqual(r['result'][0]['value'],1)
    def test_rank_tie_cap_is_disclosed(self):
        ds=LocalDataset('ties.csv',('supplier,quantity\n'+''.join(f'S{i},1\n' for i in range(45))).encode())
        r=execute(ds,{'operation':'group_sum','column':'quantity','group_by':['supplier'],'limit':1})
        self.assertEqual(len(r['result']),30);self.assertEqual(r['ranking_boundary']['tied_groups'],45);self.assertTrue(r['result_truncated'])
        self.assertIn('45 groups',explain([r]))
    def test_reversed_bounds_rejected(self):
        for filt in [{'column':'quantity','op':'between','value':4,'value2':2}, {'column':'tracking','op':'date_between','value':'2026-02-01','value2':'2026-01-01'}]:
            with self.assertRaisesRegex(ValueError,'ascending'):execute(self.ds,{'operation':'count','filters':[filt]})
    def test_identifier_not_numeric(self):
        self.assertEqual(next(c for c in schema(self.ds)['columns'] if c['name']=='order_id')['kind'],'text')
        with self.assertRaisesRegex(ValueError,'identifier'):execute(self.ds,{'operation':'average','column':'order_id'})
        with self.assertRaisesRegex(ValueError,'identifier'):build_chart(self.ds,{'chart_type':'histogram','x':'order_id'})
        self.assertEqual(execute(self.ds,{'operation':'count_distinct','column':'order_id'})['result'],5)
    def test_mixed_currency_queries(self):
        ds=LocalDataset('money.csv',b'supplier,amount,currency\nA,100,USD\nB,200,EUR\n')
        for op in ('sum','average','group_sum'):
            p={'operation':op,'column':'amount'}
            if op.startswith('group'):p['group_by']=['supplier']
            with self.assertRaisesRegex(ValueError,'currenc'):execute(ds,p)
        db=ReadOnlyDataset(ds)
        try:
            with self.assertRaisesRegex(ValueError,'currenc'):db.query('SELECT SUM(c2) FROM dataset')
            self.assertEqual(db.query('SELECT COUNT(c2) FROM dataset')['rows'],[[2]])
        finally:db.close()
        store=IntakeStore();store.dataset=ds
        self.assertIn('currenc',store.query_analysis('total amount')[0]['answer'])
        self.assertEqual(ask_hosted(ds,'total amount',[],1,None)['routing_mode'],'CHECKED_MEASURE_UNAVAILABLE')
    def test_small_values_not_rounded_to_zero(self):
        ds=LocalDataset('tiny.csv',b'group,quantity\nA,0.0000001\nB,0.0000002\n')
        self.assertAlmostEqual(execute(ds,{'operation':'sum','column':'quantity'})['result'],3e-7)
        r=execute(ds,{'operation':'group_sum','column':'quantity','group_by':['group'],'limit':1})
        self.assertEqual(r['result'][0]['group']['group'],'B');self.assertNotIn('ranking_boundary',r)
    def test_qwen_cannot_swap_understood_measure(self):
        s=IntakeStore();s.dataset=self.ds
        with patch('conversation.plan_dataset_with_local_qwen') as model:
            r=s.query_analysis('average quantity',use_local_llm=True)[0]
            model.assert_not_called();self.assertEqual(r['analysis'][0]['result'],3)
    def test_hosted_direct_text_arithmetic_and_id_conversion(self):
        ds=LocalDataset('mixed.csv',b'amount,order_id\n12,001\ninvalid,002\n')
        db=ReadOnlyDataset(ds)
        try:
            for sql in ('SELECT SUM((c1)) FROM dataset','SELECT SUM(c1*2) FROM dataset','SELECT SUM((c1)+2) FROM dataset','SELECT SUM(aegis_num(c2)) FROM dataset'):
                with self.subTest(sql=sql),self.assertRaises(ValueError):db.query(sql)
            self.assertEqual(db.query('SELECT SUM(aegis_num(c1)*2) FROM dataset')['rows'],[[24]])
            self.assertEqual(db.query('SELECT SUM(LENGTH(c1)+1) FROM dataset')['rows'],[[11]])
        finally:db.close()
    def test_timezone_overflow_does_not_crash(self):
        from hosted_copilot import _safe_julianday
        self.assertIsNone(_safe_julianday('0001-01-01T00:00:00+01:00'))
        self.assertIsNotNone(_safe_julianday('2026-01-01T00:00:00+01:00'))
    def _workbook(self, change):
        src=io.BytesIO(fake_xlsx());out=io.BytesIO()
        with zipfile.ZipFile(src) as zin,zipfile.ZipFile(out,'w') as zout:
            for n in zin.namelist():
                data=zin.read(n)
                if n.endswith('sheet1.xml'):data=change(data.decode()).encode()
                zout.writestr(n,data)
        return out.getvalue()
    def test_cached_formula_warning_and_excel_error(self):
        raw=self._workbook(lambda t:t.replace('<c r="A2" t="inlineStr"><is><t>Fictional-1</t></is></c>','<c r="A2"><f>1+2</f><v>3</v></c>').replace('<c r="B2" t="inlineStr"><is><t>Fake-Supplier</t></is></c>','<c r="B2" t="e"><v>#DIV/0!</v></c>'))
        ds=LocalDataset('formula.xlsx',raw)
        self.assertEqual(ds.rows,[['3','']]);self.assertTrue(any('may be stale' in s for s in ds.warnings));self.assertTrue(any('Excel error cells' in s for s in ds.warnings))
    def test_empty_formula_cache_reported(self):
        raw=self._workbook(lambda t:t.replace('<c r="B2" t="inlineStr"><is><t>Fake-Supplier</t></is></c>','<c r="B2"><f>1+2</f><v></v></c>'))
        ds=LocalDataset('formula.xlsx',raw);self.assertTrue(any('no cached value' in s for s in ds.warnings))
    def test_malformed_boolean_rejected(self):
        raw=self._workbook(lambda t:t.replace('<c r="B2" t="inlineStr"><is><t>Fake-Supplier</t></is></c>','<c r="B2" t="b"><v>2</v></c>'))
        with self.assertRaisesRegex(ValueError,'Boolean'):LocalDataset('bad.xlsx',raw)
    def test_duplicate_zip_names_rejected(self):
        b=io.BytesIO(fake_xlsx())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(b,'a') as z:z.writestr('xl/workbook.xml','invalid')
        with self.assertRaisesRegex(ValueError,'duplicate archive'):LocalDataset('bad.xlsx',b.getvalue())
if __name__=='__main__':unittest.main()
