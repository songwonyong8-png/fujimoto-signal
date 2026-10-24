import unittest
import numpy as np
import pandas as pd
import backtest_f_v3 as f
class TestSignals(unittest.TestCase):
    def test_ranked_top50_is_offline_frozen_and_complete(self):
        # Must not invoke Yahoo metadata (the exact source of the reported crash).
        import unittest.mock as mock
        with mock.patch.object(f.yf, 'Ticker', side_effect=AssertionError('metadata API invoked')):
            selected, ranked = f.top50_candidates()
        self.assertEqual(len(selected), 50)
        self.assertEqual(len({r['symbol'] for r in selected}), 50)
        self.assertEqual(selected, ranked)
        self.assertEqual(selected[0]['symbol'], 'NVDA')
        self.assertTrue(all(x['market_cap'] >= y['market_cap']
                            for x, y in zip(selected, selected[1:])))
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
    def test_short_history_enters_after_cloud_warmup(self):
        # An ETF with fewer than 198 bars must not be excluded by the
        # unrelated Volume Profile 120 + Ichimoku 78 double-warmup.
        x = pd.DataFrame(False, index=range(170),
                         columns=['stage1', 'stage2', 'cloud', 'cloud_vp'])
        x.loc[90, 'stage1'] = True
        x.loc[93, 'stage2'] = True
        x.loc[99, 'cloud'] = True
        x.loc[100, 'cloud_vp'] = True
        anchors = f.stage_events(x, 0, 169)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0][2]['F_cloud'], (90,93,99))
        self.assertEqual(anchors[0][2]['F_cloud_vp'], (90,93,100))

    def test_fills_use_1_2_6_and_cash_waits_for_confirmation(self):
        n=175; idx=pd.date_range('2026-01-01', periods=n, freq='B')
        p=pd.DataFrame({'open':np.full(n,100.), 'high':np.full(n,101.),
                        'low':np.full(n,99.), 'close':np.full(n,100.),
                        'volume':np.full(n,1000.)}, index=idx)
        x=pd.DataFrame(False,index=idx,columns=['stage1','stage2','cloud','cloud_vp'])
        x.loc[idx[90], 'stage1'] = True
        x.loc[idx[93], 'stage2'] = True
        x.loc[idx[99], 'cloud'] = True
        x.loc[idx[100], 'cloud_vp'] = True
        summaries,trades,fills=f.simulate(p,x,'test',idx[0],idx[-1],'TEST')
        cloud=[q for q in fills if q['variant']=='F_cloud']
        self.assertEqual([q['stage'] for q in cloud],[1,2,3])
        self.assertTrue(np.allclose([q['weight'] for q in cloud],[1/9,2/9,6/9]))
        self.assertEqual([q['stage'] for q in fills if q['variant']=='F_lump'],[1])
        self.assertEqual(len(trades),3)
        self.assertAlmostEqual(next(q for q in summaries if q['variant']=='F_cloud')['avg_capital_used'],1.)

if __name__=='__main__':unittest.main()
