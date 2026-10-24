"""Offline F6 rule and anti-lookahead regression tests (no Yahoo downloads)."""
from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import backtest_f_v6 as f


class F6RulesTests(unittest.TestCase):
    def sample(self, n=260, price=100.):
        idx=pd.date_range('2022-01-03',periods=n,freq='B')
        p=pd.DataFrame({'open':np.full(n,price),
                        'high':np.full(n,price+2),
                        'low':np.full(n,price-2),
                        'close':np.full(n,price),
                        'volume':np.full(n,1000.)},index=idx)
        sig=pd.DataFrame(False,index=idx,columns=[
            'f6_s1','f6_s2','f6_s3_breakout','f6_s3_trend',
            'f6_s3_breakout_vp','f6_s3_trend_vp','macd_death',
            'rsi_failure','rsi_overbought_entry','f6_cloud_failed',
            'stage1','stage2','cloud','cloud_vp',
            'cloud_breakdown','cloud_top_breakdown'])
        return p,sig

    def full_entries(self,s):
        s.loc[s.index[90],'f6_s1']=True
        s.loc[s.index[93],'f6_s2']=True
        s.loc[s.index[98],['f6_s3_breakout','f6_s3_trend',
                           'f6_s3_breakout_vp','f6_s3_trend_vp']]=True

    def runit(self,p,s,mode='breakout',profile='cloud',last=None):
        return f.run_f6(p,s,'unit',p.index[0],p.index[-1] if last is None else p.index[last],
                        'MOCK',mode,profile)

    def test_buy_weights_and_next_open(self):
        p,s=self.sample();self.full_entries(s)
        _,_,fills=self.runit(p,s)
        buys=[x for x in fills if x['side']=='BUY']
        self.assertEqual([x['stage'] for x in buys],[1,2,3])
        self.assertEqual([x['date'] for x in buys],[str(p.index[i].date()) for i in [91,94,99]])
        np.testing.assert_allclose([x['initial_capital_weight'] for x in buys],[1/9,2/9,6/9])
        self.assertAlmostEqual(buys[-1]['cash_after'],0.,places=9)

    def test_independent_exits_cloud_macd_rsi_in_any_order(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[104],'macd_death']=True
        s.loc[p.index[109],'rsi_overbought_entry']=True
        s.loc[p.index[114],'f6_cloud_failed']=True
        row,t,fills=self.runit(p,s)
        sells=[x for x in fills if x['side']=='SELL']
        self.assertEqual([x['stage'] for x in sells],[2,1,3])
        self.assertEqual([x['date'] for x in sells],[str(p.index[i].date()) for i in [105,110,115]])
        self.assertEqual([x['reason'] for x in sells],['MACD_DEAD_CROSS','RSI_70_PROFIT_TAKE','CLOUD_BOTTOM_BREAK'])
        self.assertEqual(row['completed_trades'],1)

    def test_rsi_70_only_sells_lot1(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[104],'rsi_overbought_entry']=True
        row,trades,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in fills if x['side']=='SELL'],[1])
        self.assertEqual(row['open_trades'],1)
        self.assertEqual(row['stage3_sells'],0)

    def test_rsi_30_sells_lot1_not_other_lots(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[104],'rsi_failure']=True
        row,trades,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in fills if x['side']=='SELL'],[1])
        self.assertEqual(row['stage2_sells'],0)
        self.assertEqual(row['stage3_sells'],0)

    def test_macd_death_only_sells_lot2(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[104],'macd_death']=True
        row,trades,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in fills if x['side']=='SELL'],[2])
        self.assertEqual(row['stage3_sells'],0)

    def test_three_simultaneous_sell_next_open(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[104],['rsi_failure','macd_death','f6_cloud_failed']]=True
        row,trades,fills=self.runit(p,s)
        sells=[x for x in fills if x['side']=='SELL']
        self.assertEqual([x['stage'] for x in sells],[3,2,1])
        self.assertEqual(len({x['date'] for x in sells}),1)
        self.assertEqual(row['completed_trades'],1)

    def test_rsi_profit_taking_prevents_further_scale_in(self):
        p,s=self.sample();s.loc[p.index[90],'f6_s1']=True
        s.loc[p.index[92],'rsi_overbought_entry']=True
        s.loc[p.index[94],'f6_s2']=True
        row,_,fills=self.runit(p,s)
        self.assertEqual([(x['side'],x['stage']) for x in fills],[('BUY',1),('SELL',1)])

    def test_20day_macd_window(self):
        p,s=self.sample();s.loc[p.index[90],'f6_s1']=True
        s.loc[p.index[111],'f6_s2']=True
        row,t,fills=self.runit(p,s)
        self.assertEqual(row['stage2_buys'],0)

    def test_no_stage3_without_stage2_and_order(self):
        p,s=self.sample();s.loc[p.index[90],'f6_s1']=True
        s.loc[p.index[94],'f6_s3_breakout']=True
        row,t,fills=self.runit(p,s)
        self.assertEqual(row['stage3_buys'],0)

    def test_no_lot_repurchase_after_sale(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[104],'f6_cloud_failed']=True
        s.loc[p.index[110],'f6_s3_breakout']=True
        row,t,fills=self.runit(p,s)
        self.assertEqual(row['stage3_buys'],1)
        self.assertEqual(row['stage3_sells'],1)

    def test_no_time_based_sale(self):
        p,s=self.sample(n=290);self.full_entries(s)
        row,t,fills=self.runit(p,s)
        self.assertEqual(len([x for x in fills if x['side']=='SELL']),0)
        self.assertEqual(row['open_trades'],1)
        self.assertEqual(row['completed_trades'],0)
        self.assertGreater(int(t[0]['calendar_bars_held']),120)

    def test_short_end_prevents_next_day_fill(self):
        p,s=self.sample();s.loc[p.index[90],'f6_s1']=True
        row,t,fills=self.runit(p,s,last=90)
        self.assertEqual(row['stage1_buys'],0)
        self.assertEqual(len(fills),0)

    def test_cloud_profile_requires_volume_confirmation(self):
        p,s=self.sample();self.full_entries(s)
        s.loc[p.index[98],'f6_s3_breakout_vp']=False
        row,_,fills=self.runit(p,s,profile='cloud_vp')
        self.assertEqual([x['stage'] for x in fills if x['side']=='BUY'],[1,2])

    def test_price_gap_uses_next_open(self):
        p,s=self.sample();s.loc[p.index[90],'f6_s1']=True
        p.loc[p.index[91],'open']=120.
        _,_,fills=self.runit(p,s)
        self.assertEqual(fills[0]['price'],120.)
        self.assertAlmostEqual(fills[0]['shares'],(1/9)/(120*1.001))

    def test_rsi_candle_requires_green_day(self):
        p,s=self.sample(n=150)
        s.loc[p.index[100],'stage1']=True
        with mock.patch.object(f.v5,'extended_indicators',return_value=s.assign(
            cloud_top=pd.Series(100.,index=p.index),
            cloud_bottom=pd.Series(95.,index=p.index),
            vp_poc=pd.Series(100.,index=p.index),
            rsi=pd.Series(45.,index=p.index))):
            actual=f.indicators(p)
        self.assertFalse(bool(actual.f6_s1.iloc[100]))
        p.loc[p.index[100],'close']=101.
        with mock.patch.object(f.v5,'extended_indicators',return_value=s.assign(
            cloud_top=pd.Series(100.,index=p.index),
            cloud_bottom=pd.Series(95.,index=p.index),
            vp_poc=pd.Series(100.,index=p.index),
            rsi=pd.Series(45.,index=p.index))):
            actual=f.indicators(p)
        self.assertTrue(bool(actual.f6_s1.iloc[100]))

    def test_chikou_uses_current_close_against_26day_old_high(self):
        p,s=self.sample(n=150)
        with mock.patch.object(f.v5,'extended_indicators',return_value=s.assign(
            cloud_top=pd.Series(90.,index=p.index),cloud_bottom=pd.Series(80.,index=p.index),
            vp_poc=pd.Series(90.,index=p.index),rsi=pd.Series(50.,index=p.index))):
            output=f.indicators(p)
        self.assertFalse(bool(output.chikou_bullish.iloc[100]))
        p.loc[p.index[100],'close']=103.
        with mock.patch.object(f.v5,'extended_indicators',return_value=s.assign(
            cloud_top=pd.Series(90.,index=p.index),cloud_bottom=pd.Series(80.,index=p.index),
            vp_poc=pd.Series(90.,index=p.index),rsi=pd.Series(50.,index=p.index))):
            output=f.indicators(p)
        self.assertTrue(bool(output.chikou_bullish.iloc[100]))

    def test_future_bars_do_not_change_old_signals(self):
        np.random.seed(7)
        p,s=self.sample(n=300)
        c=100+np.cumsum(np.random.normal(0,2,len(p)))
        p['close']=c;p['open']=c*.998;p['high']=c+2;p['low']=c-2
        a=f.indicators(p.iloc[:220].copy())
        b=f.indicators(p.copy()).iloc[:220]
        columns=['f6_s1','f6_s2','f6_s3_breakout','f6_s3_trend',
                 'f6_s3_breakout_vp','f6_s3_trend_vp','rsi_overbought_entry',
                 'chikou_bullish','cloud_up_cross']
        for col in columns:
            pd.testing.assert_series_equal(a[col],b[col],check_names=True)

    def test_profit_take_cross_not_always_above70(self):
        p,s=self.sample(n=110)
        s=s.assign(cloud_top=100.,cloud_bottom=90.,vp_poc=100.,rsi=pd.Series(50.,index=p.index))
        s.loc[p.index[90:],'rsi']=75.
        with mock.patch.object(f.v5,'extended_indicators',return_value=s):
            output=f.indicators(p)
        self.assertTrue(bool(output.rsi_overbought_entry.iloc[90]))
        self.assertFalse(bool(output.rsi_overbought_entry.iloc[91]))

    def test_matched_cohorts_identical_entry_anchor_and_end(self):
        p,s=self.sample(n=260);s.loc[p.index[90],'f6_s1']=True
        s.loc[p.index[90],'stage1']=True
        with mock.patch.object(f,'HORIZONS',(40,)):
            pairs=f.compare_matched(p,s,'unit',p.index[0],p.index[-1],'MOCK',{})
        self.assertEqual(len(pairs),4)
        self.assertEqual({x['entry'] for x in pairs},{str(p.index[91].date())})
        self.assertEqual({x['evaluation_date'] for x in pairs},{str(p.index[130].date())})
        self.assertTrue(all(x['f6_3rd_buys']==0 for x in pairs))

    def test_no_fundamental_lookahead(self):
        records={'MOCK':[dict(date=pd.Timestamp('2023-05-01'),growth=[.2,.3,.1]),
                         dict(date=pd.Timestamp('2024-06-01'),growth=[-.1,.3,.1])]}
        with mock.patch.object(f,'FUNDAMENTAL_GATE','strict'):
            self.assertFalse(f.eligible_fundamental('MOCK',pd.Timestamp('2023-04-30'),records))
            self.assertTrue(f.eligible_fundamental('MOCK',pd.Timestamp('2023-05-02'),records))
            self.assertFalse(f.eligible_fundamental('MOCK',pd.Timestamp('2024-06-02'),records))
            self.assertFalse(f.eligible_fundamental('OTHER',pd.Timestamp('2023-05-02'),records))
            self.assertFalse(f.eligible_fundamental('MOCK',pd.Timestamp('2026-10-22'),records))

    def test_fundamentals_require_sources_and_publication_date(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'data.csv'
            path.write_text('symbol,available_date,revenue_yoy,net_income_yoy,dividend_yoy,source_url\n'
                            'MOCK,2023-01-01,0.1,0.2,0.3,https://example.com\n')
            with mock.patch.object(f,'FUNDAMENTAL_GATE','strict'):
                records=f.load_fundamentals(path)
                self.assertTrue(f.eligible_fundamental('MOCK',pd.Timestamp('2023-02-01'),records))
            path.write_text('symbol,available_date,revenue_yoy,net_income_yoy,dividend_yoy,source_url\n'
                            'MOCK,2023-01-01,0.1,0.2,0.3,\n')
            with mock.patch.object(f,'FUNDAMENTAL_GATE','strict'):
                with self.assertRaises(ValueError):f.load_fundamentals(path)

    def test_required_fundamental_file_missing_fails_closed(self):
        with mock.patch.object(f,'FUNDAMENTAL_GATE','strict'):
            with self.assertRaises(RuntimeError):
                f.load_fundamentals(Path('/this_file_does_not_exist_f6.csv'))

    def test_synthetic_f5_comparison_preserves_original_entry_rules(self):
        p,s=self.sample();s.loc[p.index[90],'stage1']=True
        s.loc[p.index[90],'f6_s1']=False
        old,_,old_fills=f.v5.run_signal_lot_variant(p,s,'unit',p.index[0],p.index[-1],'MOCK','A','cloud')
        new,_,new_fills=self.runit(p,s)
        self.assertEqual(old['stage1_buys'],1)
        self.assertEqual(new['stage1_buys'],0)

if __name__=='__main__':unittest.main()
