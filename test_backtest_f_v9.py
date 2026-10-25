"""F9 frozen entry, market-universe integrity, isolated lot3 exits, and next-open checks."""
from __future__ import annotations
import sys, types
if 'yfinance' not in sys.modules:
    try:import yfinance
    except ImportError:sys.modules['yfinance']=types.ModuleType('yfinance')

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import unittest
import numpy as np
import pandas as pd
import backtest_f_v9 as f


class F9Tests(TestCase):
    def price(self,n=260):
        idx=pd.date_range('2024-01-02',periods=n,freq='B')
        df=pd.DataFrame({'open':np.full(n,100.),'high':np.full(n,101.),
            'low':np.full(n,99.),'close':np.full(n,100.),'volume':np.full(n,100000.)},index=idx)
        return df

    def sig(self,p):
        cols=['cloud_top','cloud_bottom','stage1','stage2','f6_s3_breakout',
              'rsi_failure','macd_death']
        sig=pd.DataFrame(False,index=p.index,columns=cols)
        sig['cloud_top']=99.;sig['cloud_bottom']=95.
        sig.iloc[90,sig.columns.get_loc('stage1')]=True
        sig.iloc[93,sig.columns.get_loc('stage2')]=True
        sig.iloc[97,sig.columns.get_loc('f6_s3_breakout')]=True
        return sig

    def setup_exits(self):
        p=self.price();s=self.sig(p)
        p.iloc[105,p.columns.get_loc('close')]=98.5
        p.iloc[106,p.columns.get_loc('close')]=97.5
        p.iloc[108,p.columns.get_loc('close')]=94.
        p.iloc[106,p.columns.get_loc('open')]=98.
        p.iloc[107,p.columns.get_loc('open')]=97.
        p.iloc[109,p.columns.get_loc('open')]=94.
        p['high']=p[['open','close']].max(axis=1)+1
        p['low']=p[['open','close']].min(axis=1)-1
        return p,s

    def run_mode(self,mode,p=None,s=None):
        if p is None:p,s=self.setup_exits()
        return f.simulate(p,s,'synthetic',p.index[0],p.index[-1],'KOSPI','005930.KS',mode)

    def test_selected_list_is_100_plus_100(self):
        rows=f.read_universe(Path(__file__).parent/'universe_f9_snapshot.csv')
        self.assertEqual(len(rows),200)
        self.assertEqual([r['rank'] for r in rows[:4]],['1','2','3','4'])
        self.assertEqual(rows[0]['yahoo_ticker'],'005930.KS')
        self.assertEqual(rows[100]['yahoo_ticker'],'NVDA')

    def test_source_contains_real_links(self):
        rows=f.read_universe(Path(__file__).parent/'universe_f9_snapshot.csv')
        self.assertEqual({x['market'] for x in rows},{'KOSPI','NASDAQ100'})
        self.assertTrue(all(x['source_url'].startswith('https://') for x in rows))

    def test_duplicates_not_silently_accepted(self):
        rows=f.read_universe(Path(__file__).parent/'universe_f9_snapshot.csv')
        rows[1]['yahoo_ticker']=rows[0]['yahoo_ticker']
        with TemporaryDirectory() as d:
            p=Path(d)/'bad.csv'
            with p.open('w',newline='',encoding='utf-8') as io:
                w=csv.DictWriter(io,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
            with self.assertRaises(ValueError):f.read_universe(p)

    def test_invalid_exit_model_rejected(self):
        with self.assertRaises(ValueError):f.stage3_exit('X',3,np.array([100]*5),np.array([99]*5),np.array([95]*5))

    def test_stage3_B_exits_on_first_top_break(self):
        p,s=self.setup_exits()
        _,_,lots,fills,_=self.run_mode('B',p,s)
        self.assertEqual([x['stage'] for x in fills if x['side']=='BUY'],[1,2,3])
        tr=next(x for x in lots if x['stage']==3 and x['status']=='CLOSED')
        self.assertEqual(tr['exit_date'],str(p.index[106].date()))
        self.assertEqual(tr['reason'],'CLOUD_TOP_BREAK')
        self.assertEqual(tr['entry_date'],str(p.index[98].date()))

    def test_stage3_C_two_consecutive_breaks(self):
        p,s=self.setup_exits();_,_,lots,_,_=self.run_mode('C',p,s)
        tr=next(x for x in lots if x['stage']==3 and x['status']=='CLOSED')
        self.assertEqual(tr['exit_date'],str(p.index[107].date()))
        self.assertEqual(tr['reason'],'CLOUD_TOP_TWO_CLOSES')

    def test_stage3_A_bottom_break(self):
        p,s=self.setup_exits();_,_,lots,_,_=self.run_mode('A',p,s)
        tr=next(x for x in lots if x['stage']==3 and x['status']=='CLOSED')
        self.assertEqual(tr['exit_date'],str(p.index[109].date()))
        self.assertEqual(tr['reason'],'CLOUD_BOTTOM_BREAK')

    def test_exits_diverge_only_after_common_entries(self):
        p,s=self.setup_exits()
        filled=[]
        for mode in f.STRATEGIES:
            _,_,_,ff,_=self.run_mode(mode,p,s)
            filled.append([(x['stage'],x['date'],x['shares']) for x in ff if x['side']=='BUY'])
        self.assertEqual(filled[0],filled[1]);self.assertEqual(filled[1],filled[2])

    def test_fills_at_NEXT_open_not_same_day(self):
        p,s=self.setup_exits();_,_,_,ff,_=self.run_mode('B',p,s)
        self.assertEqual(ff[0]['signal_date'],str(p.index[90].date()))
        self.assertEqual(ff[0]['date'],str(p.index[91].date()))
        self.assertEqual(ff[1]['signal_date'],str(p.index[93].date()))
        self.assertEqual(ff[1]['date'],str(p.index[94].date()))

    def test_buy_weights_and_both_side_commission(self):
        p,s=self.setup_exits();row,_,lots,ff,_=self.run_mode('B',p,s)
        buyers=[x for x in ff if x['side']=='BUY']
        self.assertEqual(len(buyers),3)
        self.assertAlmostEqual(buyers[0]['shares'],(1/9)/(100*(1+.001)))
        self.assertAlmostEqual(buyers[1]['shares'],(2/9)/(100*(1+.001)))
        self.assertAlmostEqual(buyers[2]['shares'],(6/9)/(100*(1+.001)))
        tr=next(x for x in lots if x['stage']==3 and x['status']=='CLOSED')
        self.assertAlmostEqual(tr['net_return'],f.lot_return(100.,98.))

    def test_sell_stage3_does_not_sell_1_or_2(self):
        p,s=self.setup_exits();row,_,lots,ff,_=self.run_mode('B',p,s)
        sells=[x for x in ff if x['side']=='SELL']
        self.assertEqual(len(sells),1)
        self.assertEqual(sells[0]['stage'],3)
        self.assertEqual(row['open_campaigns'],1)
        self.assertEqual(row['stage1_sells'],0)
        self.assertEqual(row['stage2_sells'],0)

    def test_rsi_macd_independent_of_lot3_mode(self):
        p,s=self.setup_exits()
        s.iloc[112,s.columns.get_loc('rsi_failure')]=True
        s.iloc[113,s.columns.get_loc('macd_death')]=True
        all_modes=[]
        for mode in f.STRATEGIES:
            row,_,_,fills,_=self.run_mode(mode,p,s)
            exit12=[(x['stage'],x['date']) for x in fills if x['side']=='SELL' and x['stage']<3]
            all_modes.append(exit12)
            self.assertEqual(row['open_campaigns'],0)
            self.assertEqual(row['completed_campaigns'],1)
        self.assertEqual(all_modes[0],all_modes[1]);self.assertEqual(all_modes[1],all_modes[2])

    def test_cloud_top_equal_not_break(self):
        c=np.array([100.,99.,99.,98.,98.]);t=np.array([99.]*5);b=np.array([95.]*5)
        self.assertFalse(f.stage3_exit('B',2,c,t,b))
        self.assertTrue(f.stage3_exit('B',3,c,t,b))
        self.assertFalse(f.stage3_exit('C',3,c,t,b))
        self.assertTrue(f.stage3_exit('C',4,c,t,b))

    def test_nan_cloud_never_forces_exit(self):
        c=np.array([100.,90.]);t=np.array([99.,np.nan]);b=np.array([95.,np.nan])
        self.assertFalse(f.stage3_exit('A',1,c,t,b))
        self.assertFalse(f.stage3_exit('B',1,c,t,b))
        self.assertFalse(f.stage3_exit('C',1,c,t,b))

    def test_no_time_based_exit(self):
        p=self.price();s=self.sig(p)
        row,campaigns,lots,fills,_=self.run_mode('A',p,s)
        self.assertEqual(row['open_campaigns'],1)
        self.assertEqual(row['stage3_sells'],0)
        self.assertEqual([x['status'] for x in campaigns],['OPEN_MTM'])
        self.assertTrue(all(x['status']=='OPEN_MTM' for x in lots))

    def test_phase_without_prices_is_skipped(self):
        p=self.price();s=self.sig(p)
        row,*_=f.simulate(p,s,'empty',pd.Timestamp('2021-01-01'),pd.Timestamp('2021-12-31'),
                          'KOSPI','005930.KS','A')
        self.assertIsNone(row)

    def test_market_portfolio_no_history_as_cash(self):
        idx=pd.bdate_range('2024-01-01',periods=4)
        a=pd.Series([1.,1.1],index=idx[2:])
        p=f.equal_weight_portfolio({'ONE':a},idx,100)
        self.assertAlmostEqual(p.iloc[0],1.)
        self.assertAlmostEqual(p.iloc[-1],1.001)
        self.assertAlmostEqual(p.iloc[2],1.)

    def test_outlier_same_names_removed(self):
        rows=[]
        for i in range(8):
            for m,v in [('A',.05*i),('B',.03*i+.04),('C',.06*i-.03)]:
                rows.append(dict(phase='x',market='KOSPI',symbol=f'K{i}',model=m,
                                 cumulative_return=v,mdd=-.04))
        result=f.outlier_sensitivity(rows,'x','KOSPI','B',counts=(0,3))
        self.assertEqual(len(result),4)
        for item in result:self.assertEqual(item['remaining_symbols'],8-item['excluded_top_n'])

    def test_matched_lots_same_entry_only(self):
        entries=[]
        for mode in f.STRATEGIES:
            entries.append(dict(phase='valid',market='KOSPI',symbol='S',model=mode,
                stage=3,status='CLOSED',entry_date='2024-08-09',net_return=.03,
                hold_bars=8,mae=-.01))
        self.assertEqual(len(f.matched_third_lots(entries,'valid')),1)
        entries[0]['status']='OPEN_MTM'
        self.assertEqual(len(f.matched_third_lots(entries,'valid')),0)

    def test_persist_report_and_summary(self):
        row=dict(phase='validation_2024_2025',market='KOSPI',model='A',
            downloaded_with_phase_prices=99,mean_ticker_return=.1,
            median_ticker_return=.02,mean_ticker_mdd=-.12,stage3_buys=10,campaign_win_rate=.4)
        s=f.make_report([row],[],[],[],[],str(f.ASOF))
        self.assertIn('200-stock',s)
        self.assertIn('survivorship',s.lower())
        self.assertIn('cloud TOP',s)

    def test_price_sample_signals_preserve_raw_flags(self):
        p=self.price();s=self.sig(p)
        before=s.copy(deep=True)
        self.run_mode('A',p,s)
        pd.testing.assert_frame_equal(s,before)


if __name__=='__main__':unittest.main()
