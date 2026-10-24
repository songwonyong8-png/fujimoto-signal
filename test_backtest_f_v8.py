"""Offline F8 outlier/indicator precision tests. No data downloads."""
import sys
import types
if 'yfinance' not in sys.modules:
    try:
        import yfinance
    except ImportError:
        sys.modules['yfinance'] = types.ModuleType('yfinance')

import unittest
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd
import backtest_f_v8 as f


class F8Studies(unittest.TestCase):
    def market(self,n=280,price=100):
        idx=pd.date_range('2023-01-02',periods=n,freq='B')
        p=pd.DataFrame({'open':np.full(n,float(price)),
                        'high':np.full(n,float(price+2)),
                        'low':np.full(n,float(price-2)),
                        'close':np.full(n,float(price)),
                        'volume':np.full(n,1200.)},index=idx)
        cols=['stage1','stage2','cloud','f6_s3_breakout','f6_s3_trend',
              'rsi_failure','rsi_overbought_entry','macd_death','cloud_breakdown']
        sig=pd.DataFrame(False,index=idx,columns=cols)
        return p,sig

    def sample_accounts(self):
        rows=[]
        for i in range(12):
            sym=f'SYM{i:02d}'
            base_ret=(12-i)/30
            for j,c in enumerate(f.CONFIGS):
                delta=0.15 if i==0 else (.02 if i in (1,2,3) else -.005)
                if c.ichimoku=='base':delta=0
                if c.ichimoku=='trend':delta*=1.15
                rows.append(dict(phase='validation_2024_2025',symbol=sym,variant=c.name,
                                 cumulative_return=base_ret+delta,mdd=-.11 if not delta else -.12))
        return rows

    def test_exact_fee_calculation(self):
        self.assertAlmostEqual(f.pair_ret(100,100),(1-f.FEE)/(1+f.FEE)-1)
        self.assertAlmostEqual(f.pair_ret(100,110),1.1*(1-f.FEE)/(1+f.FEE)-1)
        self.assertTrue(np.isnan(f.pair_ret(0,100)))

    def test_rank_winners_deterministic_ties(self):
        self.assertEqual(f.rank_winners({'B':.8,'A':.8,'C':.5},2),['A','B'])
        with self.assertRaises(ValueError):f.rank_winners({'A':.5},-1)

    def test_top_winner_removal_recalculates_on_identical_symbols(self):
        sens,rank,loo=f.robust_stats(self.sample_accounts())
        k=f.CONFIGS[1].name
        allrow=next(x for x in sens if x['candidate']==k and x['ranking_method']=='baseline_f5' and x['excluded_top_n']==0)
        removed=next(x for x in sens if x['candidate']==k and x['ranking_method']=='baseline_f5' and x['excluded_top_n']==1)
        self.assertEqual(removed['excluded_symbols'],'SYM00')
        self.assertEqual(removed['remaining_symbols'],11)
        self.assertLess(removed['mean_excess'],allrow['mean_excess'])
        self.assertAlmostEqual(removed['candidate_mean']-removed['base_mean'],removed['mean_excess'])
        self.assertEqual(len(rank),4)
        self.assertEqual(len(loo),4*12)
        self.assertEqual(len(sens),4*2*len(f.EXCLUDE_COUNTS))

    def test_candidate_exclusion_differs_from_baseline_if_rank_changes(self):
        rows=self.sample_accounts()
        alt=f.CONFIGS[1].name
        for row in rows:
            if row['symbol']=='SYM11' and row['variant']==alt:
                row['cumulative_return']=5.0
        sens,_,_=f.robust_stats(rows)
        drop_base=next(x for x in sens if x['candidate']==alt and x['ranking_method']=='baseline_f5' and x['excluded_top_n']==1)
        drop_cand=next(x for x in sens if x['candidate']==alt and x['ranking_method']=='candidate' and x['excluded_top_n']==1)
        self.assertEqual(drop_base['excluded_symbols'],'SYM00')
        self.assertEqual(drop_cand['excluded_symbols'],'SYM11')

    def test_vp_candidates_compare_to_vp_baseline(self):
        rows=self.sample_accounts()
        for row in rows:
            if row['variant']==f.CONFIGS[3].name:
                row['cumulative_return']+=.3
        sens,_,_=f.robust_stats(rows)
        compare=next(x for x in sens if x['candidate']==f.CONFIGS[4].name and x['excluded_top_n']==0)
        self.assertLess(compare['mean_excess'],-.25)
        self.assertAlmostEqual(compare['mean_excess'],-.2858333333333334)

    def test_indicator_signal_maps(self):
        p,s=self.market()
        s.loc[s.index[90],'stage1']=True
        s.loc[s.index[93],'stage2']=True
        s.loc[s.index[95],'f6_s3_breakout']=True
        s.loc[s.index[97],'f6_s3_trend']=True
        x=f.signal_arrays(s)
        self.assertTrue(x['MACD_AFTER_RSI'][93]);self.assertTrue(x['ICHI_AFTER_RSI_MACD'][95])
        self.assertFalse(x['ICHI_AFTER_RSI_MACD'][94])
        self.assertTrue(x['ICHI_TREND'][97])

    def test_sequential_macd_outside_limit_rejected(self):
        p,s=self.market(n=320)
        s.loc[s.index[90],'stage1']=True
        s.loc[s.index[111],'stage2']=True
        s.loc[s.index[113],'f6_s3_breakout']=True
        x=f.signal_arrays(s)
        self.assertFalse(x['MACD_AFTER_RSI'].any())
        self.assertFalse(x['ICHI_AFTER_RSI_MACD'].any())

    def test_nonoverlapping_spacing(self):
        self.assertEqual(f.nonoverlapping_events([10,11,15,16,25],5),[10,16,25])

    def test_forward_uses_next_open_not_current_close_and_two_fees(self):
        p,s=self.market()
        s.loc[s.index[90],'stage1']=True
        p.loc[s.index[90],'close']=4000.
        p.loc[s.index[91],'open']=100.
        p.loc[s.index[96],'open']=110.
        a,e=f.forward_signal_study(p,s,'test',p.index[0],p.index[-1],'TEST')
        r=next(x for x in a if x['signal']=='RSI_REBOUND' and x['horizon_bars']==5)
        self.assertEqual(r['signal_count'],1)
        self.assertEqual(r['positive_count'],1)
        self.assertAlmostEqual(r['average_return'],f.pair_ret(100,110))
        trace=next(x for x in e if x['signal']=='RSI_REBOUND' and x['horizon_bars']==5)
        self.assertEqual(trace['entry_date'],str(p.index[91].date()))
        self.assertEqual(trace['exit_date'],str(p.index[96].date()))

    def test_forward_excludes_event_without_full_horizon(self):
        p,s=self.market(n=130)
        s.loc[s.index[120],'stage1']=True
        a,_=f.forward_signal_study(p,s,'test',p.index[0],p.index[-1],'TEST')
        r=next(x for x in a if x['signal']=='RSI_REBOUND' and x['horizon_bars']==20)
        self.assertEqual(r['signal_count'],0)
        self.assertIsNone(r['win_rate'])

    def test_forward_same_security_baseline_flat_has_fee_loss(self):
        p,s=self.market()
        s.loc[s.index[90],'stage1']=True
        rows,_=f.forward_signal_study(p,s,'test',p.index[0],p.index[-1],'TEST')
        r=next(x for x in rows if x['signal']=='RSI_REBOUND' and x['horizon_bars']==20)
        self.assertEqual(r['win_rate'],0)
        self.assertEqual(r['unconditional_win_rate'],0)
        self.assertLess(r['average_return'],0)

    def test_rsi_signal_specific_roundtrip_uses_later_sell_open(self):
        p,s=self.market()
        s.loc[s.index[90],'stage1']=True
        s.loc[s.index[100],'rsi_overbought_entry']=True
        p.loc[s.index[101],'open']=120.
        row,trade=f.indicator_exit_study(p,s,'test',p.index[0],p.index[-1],'TEST')
        r=next(x for x in row if x['signal']=='RSI_REBOUND')
        self.assertEqual(r['completed_trades'],1)
        self.assertEqual(r['wins'],1)
        self.assertAlmostEqual(r['mean_closed_return'],f.pair_ret(100,120))
        self.assertEqual(next(x for x in trade if x['signal']=='RSI_REBOUND')['exit'],str(p.index[101].date()))

    def test_macd_signal_roundtrip(self):
        p,s=self.market()
        s.loc[s.index[90],'stage2']=True
        s.loc[s.index[94],'macd_death']=True
        p.loc[s.index[95],'open']=110.
        rr,trade=f.indicator_exit_study(p,s,'test',p.index[0],p.index[-1],'TEST')
        r=next(x for x in rr if x['signal']=='MACD_GOLDEN')
        self.assertEqual(r['completed_trades'],1)
        self.assertEqual(r['wins'],1)
        self.assertEqual(r['open_trades'],0)

    def test_ichi_exit_unclosed_is_not_a_win(self):
        p,s=self.market()
        s.loc[s.index[90],'f6_s3_breakout']=True
        rr,trade=f.indicator_exit_study(p,s,'test',p.index[0],p.index[-1],'TEST')
        r=next(x for x in rr if x['signal']=='ICHI_STRICT')
        self.assertEqual(r['completed_trades'],0)
        self.assertEqual(r['open_trades'],1)
        self.assertIsNone(r['win_rate'])
        self.assertTrue(any(x['signal']=='ICHI_STRICT' and x['status']=='OPEN_MTM' for x in trade))

    def test_wilson_sample_size(self):
        self.assertEqual(f.wilson_interval(0,0),(None,None))
        lo,hi=f.wilson_interval(1,1)
        self.assertLess(lo,1);self.assertAlmostEqual(hi,1)
        lo2,hi2=f.wilson_interval(40,100)
        self.assertLess(lo2,.4);self.assertGreater(hi2,.4)

    def test_aggregate_reports_rare_signals_rather_than_hiding(self):
        rows=[dict(phase='validation_2024_2025',symbol='A',signal='ICHI_STRICT',
                   horizon_bars=20,signal_count=2,positive_count=2,win_rate=1.,
                   average_return=.04,unconditional_win_rate=.5,unconditional_avg_return=.01)]
        x=f.signal_aggregate(rows)
        self.assertEqual(len(x),1)
        self.assertEqual(x[0]['trades'],2)
        self.assertEqual(x[0]['tickers_with_at_least_5'],0)
        self.assertIsNone(x[0]['equal_ticker_win_rate'])

    def test_stock_matrix_includes_per_ticker_signal_counts_and_missing_values(self):
        rows=[dict(phase='validation_2024_2025',symbol='NVDA',signal='RSI_REBOUND',
                   horizon_bars=20,signal_count=3,win_rate=2/3,average_return=.03,
                   win_rate_lift=.1)]
        matrix=f.indicator_stock_matrix(rows)
        self.assertEqual(len(matrix),1)
        self.assertEqual(matrix[0]['rsi_rebound_count'],3)
        self.assertEqual(matrix[0]['rsi_rebound_sample_flag'],'1-9 SPARSE')
        self.assertIsNone(matrix[0]['macd_golden_win_rate'])
        self.assertEqual(matrix[0]['ichi_strict_count'],0)

    def test_synthetic_full_pipeline_saves_files(self):
        p,_=self.market(n=360)
        x=np.arange(len(p))
        px=90+15*np.sin(x/9)+x*.03
        for col in ('open','high','low','close'):
            p[col]=px+{'open':-.2,'high':2,'low':-2,'close':.2}[col]
        with TemporaryDirectory() as folder:
            with mock.patch.object(f,'OUT',Path(folder)),\
                 mock.patch.object(f,'PHASES',(('validation_2024_2025',p.index[0],p.index[-1]),)),\
                 mock.patch.object(f.base,'UNIVERSE',[('SYN','SYN','Test','SPY')]),\
                 mock.patch.object(f.base,'REQUIRED',{'SYN'}),\
                 mock.patch.object(f.v3,'top50_candidates',return_value=([],[])),\
                 mock.patch.object(f.base,'fetch_prices',return_value=p):
                f.main()
            report=Path(folder,'report.md').read_text()
            self.assertIn('indicator',report.lower())
            meta=json.loads(Path(folder,'run_metadata.json').read_text())
            self.assertEqual(meta['status'],'success')
            self.assertTrue(Path(folder,'indicator_forward_winrates.csv').exists())
            self.assertTrue(Path(folder,'indicator_stock_matrix_20d.csv').exists())
            self.assertTrue(Path(folder,'outlier_sensitivity.csv').exists())


if __name__=='__main__':
    unittest.main()
