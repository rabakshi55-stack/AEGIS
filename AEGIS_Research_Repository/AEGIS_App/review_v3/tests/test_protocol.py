import unittest
import pandas as pd
from review_v3.research import cohort,features,protocol

class ProtocolTests(unittest.TestCase):
    def test_future_delivery_and_unknown_not_negatives(self):
        df=pd.DataFrame({'order_purchase_timestamp':pd.to_datetime(['2017-12-01']*5),'order_estimated_delivery_date':pd.to_datetime(['2017-12-15','2017-12-15','2017-12-15','2018-01-01','2017-12-15']),'order_delivered_customer_date':pd.to_datetime(['2017-12-16','2018-01-02',None,'2017-12-05','2017-12-15']),'order_status':['delivered','delivered','canceled','delivered','delivered']})
        mask,y,c=cohort(df,protocol()['train']); self.assertEqual(list(y),[1,0]); self.assertEqual(c['all_purchases'],5); self.assertEqual(c['comparable_but_not_mature_at_cutoff'],2); self.assertEqual(c['noncomparable_or_unknown'],1)
    def test_only_purchase_calendar_features(self):
        x=features(pd.Series(pd.to_datetime(['2017-01-01 01:02:03']))); self.assertEqual(list(x.columns),protocol()['features']); self.assertEqual(x.iloc[0]['hour'],1)
