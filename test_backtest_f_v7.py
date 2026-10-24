"""F7 offline ablation, baseline parity, isolated cohort and integrity tests."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import csv
import unittest

import numpy as np
import pandas as pd

import backtest_f_v7 as f


class F7FactorialTests(unittest.TestCase):
    def market(self,n=280):
        idx=pd.date_range('2022-01-03',periods=n,freq='B')
        p=pd.DataFrame(dict(open=np.full(n,100.),high=np.full(n,102.),
                            low=np.full(n,98.),close=np.full(n,100.),
                            volume=np.full(n,1000.)),index=idx)
        keys=['stage1','f6_s1','stage2','f6_s2','cloud','cloud_vp',
              'f6_s3_breakout','f6_s3_trend','f6_s3_breakout_vp','f6_s3_trend_vp',
              'rsi_overbought_entry','rsi_failure','macd_death','f6_cloud_failed',
              'cloud_breakdown','cloud_top_breakdown']
        sig=pd.DataFrame(False,index=idx,columns=keys)
        return p,sig

    def entries(self,s,candle=True):
        s.loc[s.index[90],'stage1']=True
        s.loc[s.index[90],'f6_s1']=candle
        s.loc[s.index[93],['stage2','f6_s2']]=True
        s.loc[s.index[98],['cloud','cloud_vp']]=True
        s.loc[s.index[99],['f6_s3_breakout','f6_s3_breakout_vp']]=True
        s.loc[s.index[100],['f6_s3_trend','f6_s3_trend_vp']]=True

    def execute(self,p,s,candle=False,ichi='base',tp=False,profile='cloud',only_anchor=None,
                first=None,last=None):
        cfg=f.Config(candle,ichi,tp,profile)
        return f.run_config(p,s,'synthetic',p.index[0] if first is None else first,
                            p.index[-1] if last is None else last,'SYN',cfg,
                            only_anchor=only_anchor)

    def test_24_unique_pre_registered_profiles(self):
        cfg=f.all_configs()
        self.assertEqual(len(cfg),24)
        self.assertEqual(len({z.name for z in cfg}),24)
        self.assertEqual(sum(c.profile=='cloud' for c in cfg),12)
        self.assertEqual(sum(c.profile=='cloud_vp' for c in cfg),12)

    def test_config_guardrails(self):
        with self.assertRaises(ValueError):f.Config(True,'nonexistent',False,'cloud')
        with self.assertRaises(ValueError):f.Config(True,'base',False,'other')

    def test_stage3_column_selection(self):
        p,s=self.market();self.entries(s)
        for profile in f.PROFILES:
            for mode in f.ICHIMOKU:
                column=('cloud' if profile=='cloud' else 'cloud_vp') if mode=='base' else ('f6_s3_'+('breakout' if mode=='strict' else 'trend')+('_vp' if profile=='cloud_vp' else ''))
                got=f.chosen_stage3(s,f.Config(False,mode,False,profile))
                self.assertTrue(got.equals(s[column]),(mode,profile))

    def test_buy_stages_all_variants_sequential(self):
        p,s=self.market();self.entries(s)
        for cfg in f.all_configs():
            row,_,fills=f.run_config(p,s,'unit',p.index[0],p.index[-1],'SYN',cfg)
            buys=[x for x in fills if x['side']=='BUY']
            self.assertEqual([x['stage'] for x in buys],[1,2,3],cfg.name)
            self.assertTrue(np.allclose([x['initial_capital_weight'] for x in buys],[1/9,2/9,6/9]))
            self.assertEqual(buys[0]['date'],str(p.index[91].date()))

    def test_baseline_bit_equivalence_F5_A(self):
        p,s=self.market();self.entries(s)
        s.loc[s.index[105],'rsi_overbought_entry']=True
        s.loc[s.index[110],'macd_death']=True
        s.loc[s.index[115],['cloud_breakdown','f6_cloud_failed']]=True
        for profile in f.PROFILES:
            cfg=f.baseline(profile)
            a,at,af=f.run_config(p,s,'unit',p.index[0],p.index[-1],'SYN',cfg)
            b,bt,bf=f.v5.run_signal_lot_variant(p,s,'unit',p.index[0],p.index[-1],'SYN','A',profile)
            for key in ['cumulative_return','mdd','avg_actual_exposure','completed_trades','open_trades',
                        'stage1_buys','stage2_buys','stage3_buys']:
                self.assertAlmostEqual(a[key],b[key],places=12,msg=key)
            self.assertEqual([(x['side'],x['stage']) for x in af],[(x['side'],x['stage']) for x in bf])
            self.assertFalse(any(x['reason']=='RSI_70_PROFIT_TAKE' for x in af))

    def test_f6_strict_and_trend_parity(self):
        p,s=self.market();self.entries(s)
        s.loc[s.index[106],'rsi_overbought_entry']=True
        for profile in f.PROFILES:
            for mode in ('strict','trend'):
                cfg=f.f6_equivalent(profile,mode)
                a,_,af=f.run_config(p,s,'unit',p.index[0],p.index[-1],'SYN',cfg)
                b,_,bf=f.v6.run_f6(p,s,'unit',p.index[0],p.index[-1],'SYN','breakout' if mode=='strict' else 'trend',profile)
                for key in ('cumulative_return','mdd','stage1_buys','stage3_buys','stage1_sells'):
                    self.assertAlmostEqual(a[key],b[key],places=12)
                self.assertEqual([(x['side'],x['stage']) for x in af],[(x['side'],x['stage']) for x in bf])

    def test_candle_switch_isolates_first_entry(self):
        p,s=self.market();self.entries(s,candle=False)
        a,_,af=self.execute(p,s,candle=False)
        b,_,bf=self.execute(p,s,candle=True)
        self.assertEqual(a['stage1_buys'],1)
        self.assertEqual(b['stage1_buys'],0)
        self.assertEqual(b['cumulative_return'],0)
        self.assertFalse(bf)

    def test_rsi70_exit_only_when_switch_on(self):
        p,s=self.market();self.entries(s)
        s.loc[s.index[105],'rsi_overbought_entry']=True
        off,_,off_f=self.execute(p,s,tp=False)
        on,_,on_f=self.execute(p,s,tp=True)
        self.assertFalse(any(x['reason']=='RSI_70_PROFIT_TAKE' for x in off_f))
        self.assertEqual([(x['side'],x['stage']) for x in on_f if x['reason']=='RSI_70_PROFIT_TAKE'],[('SELL',1)])
        self.assertEqual(on['stage3_buys'],off['stage3_buys'])

    def test_ichimoku_switch_changes_only_third_buy_bar(self):
        p,s=self.market();self.entries(s)
        expected={'base':99,'strict':100,'trend':101}
        for k,v in expected.items():
            _,_,o=self.execute(p,s,ichi=k)
            buys=[x for x in o if x['side']=='BUY']
            self.assertEqual([x['date'] for x in buys][:2],[str(p.index[91].date()),str(p.index[94].date())])
            self.assertEqual(buys[2]['date'],str(p.index[v].date()))

    def test_independent_exit_no_cascade(self):
        p,s=self.market();self.entries(s)
        s.loc[s.index[105],'macd_death']=True
        s.loc[s.index[110],'rsi_failure']=True
        s.loc[s.index[115],['f6_cloud_failed','cloud_breakdown']]=True
        a,t,o=self.execute(p,s)
        sales=[x['stage'] for x in o if x['side']=='SELL']
        self.assertEqual(sales,[2,1,3])
        self.assertEqual(a['completed_trades'],1)

    def test_no_force_sell_at_40_days(self):
        p,s=self.market();self.entries(s)
        a,t,o=self.execute(p,s,last=p.index[180])
        self.assertEqual(a['completed_trades'],0)
        self.assertEqual(a['open_trades'],1)
        self.assertFalse([x for x in o if x['side']=='SELL'])

    def test_base_anchor_nonoverlap(self):
        p,s=self.market();self.entries(s)
        s.loc[s.index[95],'stage1']=True
        s.loc[s.index[140],'stage1']=True
        s.loc[s.index[215],'stage1']=True
        self.assertEqual(f.select_anchors(s,0,260,40),[90,140,215])
        self.assertEqual(f.select_anchors(s,0,260,80),[90])

    def test_common_base_anchors_even_if_candle_does_not_match(self):
        p,s=self.market();self.entries(s,candle=False)
        cfg=(f.baseline('cloud'),f.Config(True,'base',False,'cloud'))
        rows=f.matched_results(p,s,'SYN',p.index[0],p.index[150],horizons=(40,),configs=cfg)
        self.assertEqual(len(rows),2)
        self.assertEqual({r['first_signal'] for r in rows},{str(p.index[90].date())})
        self.assertEqual({r['evaluation_date'] for r in rows},{str(p.index[130].date())})
        second=next(x for x in rows if x['candle'])
        self.assertEqual(second['account_return'],0)
        self.assertEqual(second['initial_entry'],0)

    def test_nonzero_relative_return_in_paired_cash_vs_buy(self):
        p,s=self.market();self.entries(s,candle=False)
        p.iloc[91:,p.columns.get_loc('close')]=103.
        cfg=(f.baseline('cloud'),f.Config(True,'base',False,'cloud'))
        rows=f.matched_results(p,s,'SYN',p.index[0],p.index[150],horizons=(40,),configs=cfg)
        cash=next(x for x in rows if x['candle'])
        self.assertEqual(cash['account_return'],0.)
        self.assertLess(cash['excess_return'],0.)

    def test_bootstrap_reproducible_and_contains_effect(self):
        x=[-0.03,-0.01,0.01,0.03,0.05,0.07]
        a=f.bootstrap_symbol_ci(x,seed=1,n=200)
        b=f.bootstrap_symbol_ci(x,seed=1,n=200)
        self.assertEqual(a,b)
        self.assertLess(a[0],np.mean(x))
        self.assertGreater(a[1],np.mean(x))

    def test_mdd_is_drawdown_not_closed_trade_loss(self):
        p,s=self.market();self.entries(s)
        p.iloc[102:132,p.columns.get_loc('close')]=80.
        p.iloc[132:,p.columns.get_loc('close')]=120.
        row,_,_=self.execute(p,s)
        self.assertLess(row['mdd'],0)
        self.assertGreater(row['cumulative_return'],0)

    def test_statistic_pair_tie_accounted_correctly(self):
        rows=[dict(phase='validation_2024_2025',symbol='A',profile='cloud',
                   horizon_bars=40,variant='x',excess_return=0.,initial_entry=1,stage3_buys=0),
              dict(phase='validation_2024_2025',symbol='B',profile='cloud',
                   horizon_bars=40,variant='x',excess_return=.10,initial_entry=1,stage3_buys=1),
              dict(phase='validation_2024_2025',symbol='B',profile='cloud',
                   horizon_bars=40,variant='x',excess_return=-.10,initial_entry=0,stage3_buys=0)]
        res=f.paired_statistics(rows)[0]
        self.assertEqual((res['beat_baseline'],res['equal_baseline'],res['worse_than_baseline']),(1,1,1))
        self.assertAlmostEqual(res['equal_symbol_mean_difference'],0)
        self.assertEqual(res['candle_rejected'],1)

    def test_marginal_factor_effects_exact(self):
        rows=[]
        for sym in ['A','B']:
            for c in f.all_configs():
                ret=0.01+(.04 if c.candle else 0)+(.02 if c.profit70 else 0)+(.03 if c.ichimoku=='strict' else .01 if c.ichimoku=='trend' else 0)
                rows.append(dict(phase='validation_2024_2025',symbol=sym,
                                 variant=c.name,cumulative_return=ret,
                                 mdd=-.15+(.02 if c.candle else 0),
                                 avg_actual_exposure=.10+(.03 if c.profit70 else 0)))
        by={x['rule']:x for x in f.per_symbol_ablation(rows)}
        self.assertAlmostEqual(by['candle']['mean_return_effect'],.04)
        self.assertAlmostEqual(by['RSI70']['mean_return_effect'],.02)
        self.assertAlmostEqual(by['ichi_strict']['mean_return_effect'],.03)
        self.assertAlmostEqual(by['ichi_trend']['mean_return_effect'],.01)
        self.assertAlmostEqual(by['candle']['mean_mdd_effect'],.02)
        self.assertAlmostEqual(by['RSI70']['mean_exposure_effect'],.03)

    def test_24_return_cells_covered_by_effects(self):
        a=f.all_configs()
        self.assertEqual({c.ichimoku for c in a},set(f.ICHIMOKU))
        self.assertEqual({c.candle for c in a},{True,False})
        self.assertEqual({c.profit70 for c in a},{True,False})
        self.assertEqual({c.profile for c in a},set(f.PROFILES))

    def test_daily_indicator_no_future_data(self):
        rng=np.random.default_rng(8)
        p,s=self.market(n=310)
        daily=100+np.cumsum(rng.normal(0,1,310))
        p['close']=daily;p['open']=daily-0.2
        p['high']=daily+1;p['low']=daily-1
        full=f.v6.indicators(p)
        prefix=f.v6.indicators(p.iloc[:250])
        cols=['stage1','f6_s1','cloud','f6_s3_breakout','f6_s3_trend',
              'rsi_overbought_entry','f6_cloud_failed']
        for col in cols:
            self.assertTrue(full[col].iloc[:250].equals(prefix[col]),col)

    def test_build_report_mentions_selection_bias(self):
        report=f.write_report([],[],[],[],58,57)
        self.assertIn('NOT an untouched holdout',report)
        self.assertIn('MDD',report)
        self.assertIn('24 strategies',report)

    def test_error_if_fundamental_mode_turns_on_unfairly(self):
        p,s=self.market();self.entries(s)
        with mock.patch.object(f.v6,'FUNDAMENTAL_GATE','strict'):
            with self.assertRaises(RuntimeError):self.execute(p,s)

    def test_recent_etf_with_no_2024_2025_prices_does_not_fail_audit(self):
        # Regression for GitHub run 40073917479: DRAM first traded in 2026.
        p,s=self.market(n=260)
        p.index=pd.bdate_range('2026-01-02',periods=260)
        s.index=p.index
        self.entries(s)
        with TemporaryDirectory() as tmp:
            with mock.patch.object(f,'OUT',Path(tmp)),\
                 mock.patch.object(f.base,'UNIVERSE',[('DRAM','DRAM','Unit','SPY')]),\
                 mock.patch.object(f.base,'REQUIRED',{'DRAM'}),\
                 mock.patch.object(f.v3,'top50_candidates',return_value=([],[])),\
                 mock.patch.object(f.base,'fetch_prices',return_value=p),\
                 mock.patch.object(f.v6,'indicators',return_value=s),\
                 mock.patch.object(f.base,'PHASES',[
                     ('validation_2024_2025',pd.Timestamp('2024-01-01'),pd.Timestamp('2025-12-31')),
                     ('exploratory_2026',p.index[0],p.index[-1])]):
                f.main()
            data=__import__('json').loads((Path(tmp)/'run_metadata.json').read_text())
            self.assertEqual(data['status'],'success')
            self.assertEqual(data['downloaded'],1)
            self.assertFalse(data['failures'])

    def test_synthetic_end_to_end_report_generation(self):
        p,s=self.market(n=260);self.entries(s)
        s.loc[s.index[111],'rsi_failure']=True
        with TemporaryDirectory() as tmp:
            with mock.patch.object(f,'OUT',Path(tmp)),\
                 mock.patch.object(f.base,'UNIVERSE',[('SYN','Synthetic','Unit','SPY')]),\
                 mock.patch.object(f.base,'REQUIRED',{'SYN'}),\
                 mock.patch.object(f.v3,'top50_candidates',return_value=([],[])),\
                 mock.patch.object(f.base,'fetch_prices',return_value=p),\
                 mock.patch.object(f.v6,'indicators',return_value=s),\
                 mock.patch.object(f.base,'PHASES',[
                     ('validation_2024_2025',p.index[0],p.index[-1]),
                     ('development_2021_2023',p.index[0],p.index[-1]),
                     ('exploratory_2026',p.index[0],p.index[-1])]):
                f.main()
            md=(Path(tmp)/'run_metadata.json').read_text()
            self.assertIn('"status": "success"',md)
            report=(Path(tmp)/'report.md').read_text()
            self.assertIn('F7',report)
            with (Path(tmp)/'ablation_effects.csv').open(encoding='utf-8-sig') as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),4)
            with (Path(tmp)/'matched_cohorts.csv').open(encoding='utf-8-sig') as handle:
                self.assertGreater(len(list(csv.DictReader(handle))),0)
            self.assertTrue((Path(tmp)/'paired_statistics.csv').is_file())


if __name__ == '__main__':
    unittest.main()
