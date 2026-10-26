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

    def test_cannot_publish_future_dummy_trade(self):
        x=f.empty_record(self.meta())
        self.assertEqual(x['status'],'UNAVAILABLE')
        self.assertIsNone(x['close'])

if __name__=='__main__':
    import unittest
    unittest.main()
