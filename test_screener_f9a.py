"""200-stock scanner test, including F9 indicator parity and failure safety."""
from __future__ import annotations
import json
import sys
import types
from pathlib import Path
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

import numpy as np
import pandas as pd

try:
    import yfinance
except ImportError:
    sys.modules['yfinance']=types.ModuleType('yfinance')

import update_screener as f

class F9ScreenerTests(TestCase):
    def prices(self,n=150):
        i=pd.date_range('2024-01-01',periods=n,freq='B');close=np.full(n,102.)
        return pd.DataFrame({'open':close-1,'high':close+2,'low':close-2,
             'close':close,'volume':np.full(n,10000.)},index=i)

    def meta(self):
        return {'symbol':'NVDA','name':'엔비디아','market':'NASDAQ100','rank':1,'currency':'USD'}

    def signals(self,p):
        n=len(p);s=pd.DataFrame(index=p.index)
        for key in ['stage1','stage2','f6_s3_breakout','rsi_failure','macd_death']:
            s[key]=False
        s['rsi']=40.
        s['cloud_top']=110.
        s['cloud_bottom']=100.
        return s

    def test_universe_is_exactly_two_hundreds(self):
        rows=f.read_universe()
        self.assertEqual(len(rows),201)
        self.assertEqual(sum(x['market']=='KOSPI' for x in rows),100)
        self.assertEqual(sum(x['market']=='NASDAQ100' for x in rows),100)
        self.assertEqual(len(set(x['symbol'] for x in rows)),201)
        self.assertEqual(rows[0]['symbol'],'DRAM')

    def test_F9_buy_signals_and_sells_match_indicators(self):
        p=self.prices();s=self.signals(p)
        s.iloc[-1,s.columns.get_loc('stage1')]=True
        s.iloc[-1,s.columns.get_loc('stage2')]=True
        s.iloc[-1,s.columns.get_loc('f6_s3_breakout')]=True
        s.iloc[-1,s.columns.get_loc('rsi_failure')]=True
        s.iloc[-1,s.columns.get_loc('macd_death')]=True
        s.iloc[-1,s.columns.get_loc('cloud_bottom')]=103
        with mock.patch.object(f.v6,'indicators',return_value=s):
            z=f.indicator_snapshot(p,self.meta())
        self.assertTrue(all(z['signals'].values()))
        self.assertEqual(z['asof'],str(p.index[-1].date()))
        self.assertEqual(z['close'],102.)

    def test_cloud_top_breach_without_bottom_breach_is_not_A_sell(self):
        p=self.prices();s=self.signals(p)
        s.iloc[-1,s.columns.get_loc('cloud_top')]=105
        s.iloc[-1,s.columns.get_loc('cloud_bottom')]=98
        with mock.patch.object(f.v6,'indicators',return_value=s):
            z=f.indicator_snapshot(p,self.meta())
        self.assertFalse(z['signals']['sell3'])

    def test_cloud_bottom_close_breach_is_A_sell(self):
        p=self.prices();s=self.signals(p)
        s.iloc[-1,s.columns.get_loc('cloud_bottom')]=103
        with mock.patch.object(f.v6,'indicators',return_value=s):
            z=f.indicator_snapshot(p,self.meta())
        self.assertTrue(z['signals']['sell3'])

    def test_kospi_intraday_bar_not_used(self):
        p=self.prices();p.index=p.index[:-1].append(pd.DatetimeIndex(['2026-10-26']))
        cut=f.completed_daily_bars(p,'KOSPI',datetime(2026,10,26,3,25,tzinfo=timezone.utc))
        self.assertEqual(len(cut),len(p)-1)
        after=f.completed_daily_bars(p,'KOSPI',datetime(2026,10,26,7,20,tzinfo=timezone.utc))
        self.assertEqual(len(after),len(p))

    def test_us_regular_session_unfinished_not_used(self):
        p=self.prices();p.index=p.index[:-1].append(pd.DatetimeIndex(['2026-10-26']))
        # October 26 EDT: 18:00 UTC = 14:00 ET. Not yet a completed bar.
        cut=f.completed_daily_bars(p,'NASDAQ100',datetime(2026,10,26,18,0,tzinfo=timezone.utc))
        self.assertEqual(len(cut),len(p)-1)
        after=f.completed_daily_bars(p,'NASDAQ100',datetime(2026,10,26,22,0,tzinfo=timezone.utc))
        self.assertEqual(len(after),len(p))

    def test_empty_has_no_false_triggers(self):
        item=f.empty_record(self.meta(),'No prices')
        self.assertEqual(item['status'],'UNAVAILABLE')
        self.assertFalse(any(item['signals'].values()))
        self.assertIsNone(item['asof'])

    def test_multi_ticker_batch_extract(self):
        p=self.prices()
        both=pd.concat({'NVDA':p.rename(columns=str.capitalize),'MU':p.rename(columns=str.capitalize)},axis=1)
        extracted=f.extract_prices(both,'NVDA',2)
        self.assertEqual(len(extracted),len(p))
        self.assertEqual(extracted.close.iloc[-1],102.)

    def test_failed_batch_produces_explicit_missing_and_atomic_file(self):
        # Every symbol fails; status JSON remains parseable, but run is marked
        # failed rather than inventing a buy or sell signal.
        with TemporaryDirectory() as d:
            target=Path(d)/'data'/'screener_f9a.json'
            with self.assertRaisesRegex(RuntimeError,'only refreshed 0/201'):
                f.update_all(fetcher=lambda tickers: None,output_path=target)
            z=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(len(z['stocks']),201)
            self.assertEqual(z['fresh_count'],0)
            self.assertFalse(any(any(row['signals'].values()) for row in z['stocks']))

    def test_all_100_kospi_stocks_have_real_display_names(self):
        rows=f.read_universe()
        kr=[r for r in rows if r['market']=='KOSPI']
        self.assertEqual(len(kr),100)
        self.assertTrue(all(r['name']!=r['symbol'] for r in kr))
        self.assertEqual(next(r['name'] for r in kr if r['symbol']=='0126Z0.KS'), '삼성에피스홀딩스')
        self.assertEqual(next(r['name'] for r in kr if r['symbol']=='028260.KS'), '삼성물산')
        self.assertEqual(next(r['name'] for r in kr if r['symbol']=='034220.KS'), 'LG디스플레이')

    def test_volume_profile_poc_and_seventy_percent_value_area(self):
        p=self.prices(120)
        p['low']=99.;p['high']=101.;p['close']=100.
        # Known HLC3 concentrations: 96 candles at 100, 24 at 110
        p.loc[p.index[-24:],'low']=109.
        p.loc[p.index[-24:],'high']=111.
        p.loc[p.index[-24:],'close']=110.
        x=f.volume_profile(p)
        self.assertEqual(x['period_bars'],120)
        self.assertEqual(len(x['histogram']),32)
        self.assertGreaterEqual(x['actual_coverage'],.70)
        self.assertLessEqual(x['actual_coverage'],1.)
        self.assertTrue(x['val']<=x['poc']<=x['vah'])
        self.assertLess(abs(x['poc']-100),1.)

    def test_volume_profile_today_only_and_no_future_lookahead(self):
        p=self.prices(150)
        p['low']=97.;p['high']=103.;p['close']=100.
        baseline=f.volume_profile(p)
        altered=p.copy()
        altered.iloc[0,altered.columns.get_loc('volume')]=1_000_000_000
        # Older than most recent 120: must NOT influence volume profile.
        self.assertEqual(baseline,f.volume_profile(altered))
        altered=p.copy()
        altered.iloc[-1,altered.columns.get_loc('volume')]=100_000_000
        altered.iloc[-1,altered.columns.get_loc('high')]=180.
        altered.iloc[-1,altered.columns.get_loc('low')]=160.
        altered.iloc[-1,altered.columns.get_loc('close')]=170.
        self.assertNotEqual(baseline['poc'],f.volume_profile(altered)['poc'])

    def test_flat_price_profile_and_invalid_volume(self):
        p=self.prices(120)
        p['high']=100.;p['low']=100.;p['close']=100.
        self.assertEqual(f.volume_profile(p)['poc'],100.)
        p['volume']=0.
        with self.assertRaisesRegex(ValueError,'positive volume'):
            f.volume_profile(p)

    def test_macd_chart_exact_parity_and_price_levels(self):
        p=self.prices(150)
        s=self.signals(p)
        with mock.patch.object(f.v6,'indicators',return_value=s):
            record=f.indicator_snapshot(p,self.meta())
        self.assertEqual(len(record['macd_chart']['macd']),40)
        self.assertEqual(len(record['macd_chart']['signal']),40)
        self.assertEqual(len(record['macd_chart']['histogram']),40)
        self.assertEqual(len(record['recent_closes']),120)
        self.assertEqual(record['macd'],record['macd_chart']['macd'][-1])
        self.assertEqual(record['macd_signal'],record['macd_chart']['signal'][-1])
        self.assertGreaterEqual(record['volume_profile']['actual_coverage'],.7)
        self.assertTrue(record['volume_profile']['val']<=record['volume_profile']['poc']<=record['volume_profile']['vah'])

    def test_rsi_rebound_evidence_explains_real_three_part_rule(self):
        p=self.prices(150)
        sig=self.signals(p)
        sig['rsi']=42.
        sig.iloc[-4,sig.columns.get_loc('rsi')]=28.42
        sig.iloc[-2,sig.columns.get_loc('rsi')]=31.40
        sig.iloc[-1,sig.columns.get_loc('rsi')]=35.11
        # Test one positive closing candle without retroactively changing indicators.
        p.iloc[-2,p.columns.get_loc('close')]=99
        p.iloc[-1,p.columns.get_loc('close')]=102
        sig.iloc[-1,sig.columns.get_loc('stage1')]=True
        with mock.patch.object(f.v6,'indicators',return_value=sig):
            record=f.indicator_snapshot(p,self.meta())
        ev=record['rsi_rebound']
        self.assertTrue(ev['eligible_today'])
        self.assertEqual(ev['oversold_date'],p.index[-4].date().isoformat())
        self.assertEqual(ev['oversold_rsi'],28.42)
        self.assertEqual(ev['yesterday_rsi'],31.4)
        self.assertEqual(ev['today_rsi'],35.11)
        self.assertEqual(ev['rsi_change'],3.71)
        self.assertEqual(len(ev['history']),14)
        self.assertEqual(record['signals']['buy1'],ev['eligible_today'])

    def test_rsi_oversold_today_not_counted_as_prior_five(self):
        p=self.prices(150); sig=self.signals(p)
        sig['rsi']=40.
        sig.iloc[-1,sig.columns.get_loc('rsi')]=28.
        evidence=f.rsi_rebound_evidence(p,sig)
        self.assertIsNone(evidence['oversold_date'])
        self.assertFalse(evidence['checks']['oversold_in_prior_5'])
        self.assertFalse(evidence['eligible_today'])

    def test_rsi_oversold_six_days_ago_is_out_of_window(self):
        p=self.prices(150); sig=self.signals(p)
        sig['rsi']=36.
        sig.iloc[-7,sig.columns.get_loc('rsi')]=24.
        p.iloc[-1,p.columns.get_loc('close')]=103.
        evidence=f.rsi_rebound_evidence(p,sig)
        self.assertFalse(evidence['checks']['oversold_in_prior_5'])
        self.assertFalse(evidence['eligible_today'])

    def test_rsi_price_down_prevents_stage1_even_after_oversold(self):
        p=self.prices(150); sig=self.signals(p)
        sig['rsi']=35.
        sig.iloc[-5,sig.columns.get_loc('rsi')]=27.
        p.iloc[-1,p.columns.get_loc('close')]=100.
        p.iloc[-2,p.columns.get_loc('close')]=102.
        evidence=f.rsi_rebound_evidence(p,sig)
        self.assertTrue(evidence['checks']['oversold_in_prior_5'])
        self.assertTrue(evidence['checks']['current_rsi_30_to_48'])
        self.assertFalse(evidence['checks']['close_higher_than_yesterday'])
        self.assertFalse(evidence['eligible_today'])

    def test_rsi_true_signal_matches_reference_indicators(self):
        # No duplicate RSI formula. This is compared against original F9 code.
        p=self.prices(180)
        arr=p.close.to_numpy(copy=True)
        arr[-55:-25]=np.linspace(110.,70.,30)
        arr[-25:-7]=np.linspace(70.,85.,18)
        arr[-7:-2]=np.linspace(85.,74.,5)
        arr[-2:]=[72.,75.]
        p['close']=arr
        p['open']=arr
        p['high']=arr+4
        p['low']=arr-4
        sig=f.v6.indicators(p)
        ev=f.rsi_rebound_evidence(p,sig)
        self.assertEqual(bool(sig.stage1.iloc[-1]),ev['eligible_today'])
        self.assertEqual(ev['today_rsi'],f.safe_number(sig.rsi.iloc[-1],2))

    def test_missing_data_never_has_fictitious_support_price(self):
        result=f.empty_record(self.meta(),'No price history')
        self.assertIsNone(result['volume_profile'])
        self.assertIsNone(result['macd_chart'])
        self.assertIsNone(result['rsi_rebound'])

    def test_cannot_publish_future_dummy_trade(self):
        x=f.empty_record(self.meta())
        self.assertEqual(x['status'],'UNAVAILABLE')
        self.assertIsNone(x['close'])

if __name__=='__main__':
    import unittest
    unittest.main()
