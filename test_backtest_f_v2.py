import unittest
import numpy as np
import pandas as pd
import backtest_f_v2 as f
class TestSignals(unittest.TestCase):
    def test_strict_order(self):
        x=pd.DataFrame(False,index=range(300),columns=['stage1','stage2','cloud','cloud_vp'])
        x.loc[200,'stage1']=True
        x.loc[201,'cloud']=True
        x.loc[202,'stage2']=True
        x.loc[203,'cloud']=True
        x.loc[204,'cloud_vp']=True
        a=f.stage_events(x,0,299)
        self.assertEqual(len(a),1)
        self.assertEqual(a[0][2]['F_cloud'],(200,202,203))
        self.assertEqual(a[0][2]['F_cloud_vp'],(200,202,204))
    def test_missing_macd_blocks_stage3(self):
        x=pd.DataFrame(False,index=range(300),columns=['stage1','stage2','cloud','cloud_vp'])
        x.loc[200,'stage1']=True;x.loc[201,'cloud_vp']=True
        a=f.stage_events(x,0,299)
        self.assertIsNone(a[0][2]['F_cloud_vp'][2])
    def test_ichimoku_no_future(self):
        n=350;idx=pd.date_range('2020-01-01',periods=n,freq='B')
        close=np.linspace(100,200,n)
        p=pd.DataFrame({'open':close,'high':close+2,'low':close-2,'close':close,'volume':np.full(n,1000)},index=idx)
        original=f.indicators(p)
        q=p.copy();q.iloc[-1,q.columns.get_loc('close')]=5000
        modified=f.indicators(q)
        pd.testing.assert_frame_equal(original.iloc[:-1],modified.iloc[:-1])
if __name__=='__main__':unittest.main()
