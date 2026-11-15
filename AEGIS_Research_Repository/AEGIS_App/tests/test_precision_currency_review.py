"""Additional regression checks on exact Integrity Edition defects."""
import io
import zipfile
import unittest
from decimal import Decimal
from intake import LocalDataset, _formatted_excel_date
from dataset_queries import execute
from custom_charts import build_chart
from adaptive_charts import recommend, _top_counts, _source
from focused_analysis import _field
from chart_copilot import answer_for_charts
from hosted_copilot import ReadOnlyDataset
from dataset_overview import build_overview

class PrecisionCurrencyReview(unittest.TestCase):
    def ds(self, text): return LocalDataset('fiction.csv',text.encode())
    def chart(self,ds,**opts):
        return build_chart(ds,{'chart_type':'bar','x':'supplier','y':'quantity','aggregation':'sum',**opts})
    def test_tiny_custom_chart_values_and_copilot(self):
        ds=self.ds('supplier,quantity\nA,0.000000001\nB,0.000000002\n')
        c=self.chart(ds)
        self.assertEqual([v['value'] for v in c['values']],[2e-9,1e-9])
        result=answer_for_charts(ds,'Explain this chart',[{'kind':'custom','key':'c:1','options':{'x':'supplier','y':'quantity','aggregation':'sum'}}],'c:1',dataset_revision=1,current_revision=1)
        self.assertIn('2E-9',result[0]['answer']); self.assertNotIn('tie for highest',result[0]['answer'])
    def test_exact_group_ranking_before_float_conversion(self):
        ds=self.ds('supplier,quantity\nA,999999999999999.01\nB,999999999999999.02\n')
        r=execute(ds,{'operation':'group_sum','group_by':['supplier'],'column':'quantity','limit':1})
        self.assertEqual(r['result'][0]['group']['supplier'],'B');self.assertEqual(Decimal(str(r['result'][0]['value'])),Decimal('999999999999999.02'));self.assertNotIn('ranking_boundary',r)
    def test_chart_rejects_unrepresentable_rank_tie(self):
        ds=self.ds('supplier,quantity\nA,999999999999999.01\nB,999999999999999.02\n')
        with self.assertRaisesRegex(ValueError,'precision'):self.chart(ds)
    def test_scatter_rejects_precision_collision(self):
        ds=self.ds('quantity,score\n999999999999999.01,1\n999999999999999.02,2\n')
        with self.assertRaisesRegex(ValueError,'precision'):build_chart(ds,{'chart_type':'scatter','x':'quantity','y':'score'})
    def test_automatic_tiny_values_and_overview(self):
        ds=self.ds('supplier,quantity\nA,0.000000001\nA,0.000000001\nB,0.000000001\nB,0.000000002\n')
        chart=next(c for c in recommend(ds)['charts'] if c['id']=='units_by_group')
        self.assertEqual([v['count'] for v in chart['values']],[3e-9,2e-9])
        self.assertIn('3E-9',build_overview(ds)['answer'])
    def test_automatic_currency_guard_all_paths(self):
        ds=self.ds('supplier,unit_cost,order_date,total_amount,currency\nA,10,2026-01-01,100,USD\nA,20,2026-01-02,200,EUR\nB,30,2026-02-01,300,USD\nB,40,2026-02-02,400,EUR\nB,50,2026-02-03,500,USD\n')
        ids={c['id'] for c in recommend(ds)['charts']}
        self.assertFalse(ids & {'recorded_amount_by_group','recorded_amount_trend','numeric_distribution'})
        self.assertIn('records_by_group',ids)
        self.assertIn('currenc',_field(ds,'total_amount')['answer']);self.assertNotIn('mean',_field(ds,'total_amount')['answer'])
    def test_focused_identifier_not_averaged(self):
        ds=self.ds('account,quantity\n001,1\n002,2\n')
        self.assertIn('distinct',_field(ds,'account')['answer']);self.assertNotIn('mean',_field(ds,'account')['answer'])
    def test_remainder_label_does_not_collide(self):
        labels=['Other categories']+['group'+str(i) for i in range(9)]
        values,_,_= _top_counts([[v] for v in labels],0)
        self.assertEqual(len({v['label'] for v in values}),len(values));self.assertTrue(values[-1]['remainder']);self.assertNotEqual(values[-1]['label'],'Other categories')
    def test_combined_remainder_not_named_leader(self):
        ds=self.ds('supplier,quantity\n'+''.join(f'S{i},1\n' for i in range(12) for _ in range(2)))
        chart=next(c for c in recommend(ds)['charts'] if c['id']=='records_by_group')
        self.assertGreater(chart['values'][-1]['count'],chart['values'][0]['count'])
        result=answer_for_charts(ds,'Which group is highest in this chart?',[{'kind':'automatic','key':'a','id':'records_by_group'}],'a',dataset_revision=1,current_revision=1)
        self.assertIn('remainder bar combines',result[0]['answer']);self.assertNotIn('**Other categories** is highest',result[0]['answer'])
    def test_ambiguous_header_candidates_not_arbitrarily_selected(self):
        self.assertEqual(_source(['unit_cost','price'],{},'unit_cost',['unit_cost','price']),(None,None))
        self.assertEqual(_source(['unit_cost','price'],{'unit_cost':'price'},'unit_cost',['unit_cost','price']),('price','manager-mapped'))
    def test_nested_identifier_and_text_coercion_blocked(self):
        ds=self.ds('amount,order_id\n12,001\ninvalid,002\n')
        db=ReadOnlyDataset(ds)
        try:
            for sql in ['SELECT SUM(COALESCE(c1,0)) FROM dataset','SELECT AVG(TRIM(c1)) FROM dataset','SELECT SUM(aegis_num((c2))) FROM dataset','SELECT SUM(aegis_num(c1+1)) FROM dataset']:
                with self.subTest(sql=sql),self.assertRaises(ValueError):db.query(sql)
            self.assertEqual(db.query('SELECT SUM(aegis_num((c1))) FROM dataset')['rows'],[[12]])
        finally:db.close()
    def test_excel_fractional_fictitious_date(self):
        self.assertEqual(_formatted_excel_date('60.5',False),'60.5')
        self.assertEqual(_formatted_excel_date('59.5',False),'1900-02-28T12:00:00')
        self.assertEqual(_formatted_excel_date('61.5',False),'1900-03-01T12:00:00')
    def test_invalid_styled_excel_date_is_blank_and_reported(self):
        from test_intake import fake_xlsx
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(fake_xlsx())) as source, zipfile.ZipFile(out,'w') as dest:
            for name in source.namelist():
                content=source.read(name)
                if name.endswith('sheet1.xml'):
                    content=content.replace(b'<c r="B2" t="inlineStr"><is><t>Fake-Supplier</t></is></c>',b'<c r="B2" s="1"><v>60.5</v></c>')
                dest.writestr(name,content)
            dest.writestr('xl/styles.xml','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        ds=LocalDataset('fiction.xlsx',out.getvalue())
        self.assertEqual(ds.rows,[['Fictional-1','']]);self.assertTrue(any('invalid styled Excel date' in w for w in ds.warnings))
    def test_year_labels_are_zero_padded(self):
        ds=self.ds('date,quantity\n0001-01-01,1\n2026-01-01,2\n')
        c=build_chart(ds,{'x':'date','chart_type':'line','date_grain':'year','sort':'x_asc'})
        self.assertEqual([v['label'] for v in c['values']],['0001','2026'])
    def test_histogram_small_values_have_distinct_labels(self):
        ds=self.ds('quantity\n0.000000001\n0.000000002\n0.000000003\n0.000000004\n0.000000005\n')
        c=build_chart(ds,{'x':'quantity','chart_type':'histogram'})
        self.assertEqual(len({v['label'] for v in c['values']}),len(c['values']));self.assertEqual(sum(v['value'] for v in c['values']),5)
if __name__=='__main__':unittest.main()
