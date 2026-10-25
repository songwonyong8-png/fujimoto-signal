"""Checks the iPhone F9-A projection against the backtest engine, using synthetic daily data."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
import pandas as pd

# Offline unit tests do not need the remote yfinance service.
try:
    import yfinance  # noqa: F401
except ImportError:
    _yf_stub = types.ModuleType('yfinance')
    _yf_stub.Ticker = lambda *a, **k: None
    _yf_stub.download = lambda *a, **k: None
    sys.modules['yfinance'] = _yf_stub

import backtest_f_v9 as f9
from signal_snapshot import build_strategy_snapshot
from update_data import normalize, update_all


class PwaF9SnapshotTests(TestCase):
    def price(self, n=285):
        ix=pd.date_range('2024-01-02',periods=n,freq='B')
        return pd.DataFrame({'open':np.full(n,100.),'high':np.full(n,105.),
                             'low':np.full(n,95.),'close':np.full(n,101.),
                             'volume':np.full(n,100000.)},index=ix)

    def signals(self, prices):
        ix=prices.index;n=len(prices)
        sig=pd.DataFrame(index=ix)
        for key in ('stage1','stage2','f6_s3_breakout','rsi_failure',
                    'macd_death','tk_bullish','chikou_bullish','cloud_up_cross'):
            sig[key]=False
        sig['cloud_top']=np.full(n,103.)
        sig['cloud_bottom']=np.full(n,92.)
        sig['rsi']=np.full(n,43.)
        return sig

    def test_no_signal_is_waiting(self):
        p=self.price();s=self.signals(p)
        d=build_strategy_snapshot(p,'NVDA',s)
        self.assertEqual(d['state'],'WAIT_RSI')
        self.assertEqual(d['next_open_orders'],[])
        self.assertFalse(d['virtual_campaign_open'])

    def test_stage1_last_close_is_pending_not_filled(self):
        p=self.price();s=self.signals(p);s.loc[p.index[-1],'stage1']=True
        d=build_strategy_snapshot(p,'NVDA',s)
        self.assertEqual([(x['side'],x['stage']) for x in d['next_open_orders']],[('BUY',1)])
        self.assertFalse(d['positions']['1']['held'])
        self.assertEqual(d['state'],'BUY_SIGNAL')

    def test_stage2_last_close_eligible(self):
        p=self.price();s=self.signals(p);s.loc[p.index[-13],'stage1']=True;s.loc[p.index[-1],'stage2']=True
        d=build_strategy_snapshot(p,'DRAM',s)
        self.assertTrue(d['positions']['1']['held'])
        self.assertFalse(d['positions']['2']['held'])
        self.assertEqual(d['next_open_orders'][0]['stage'],2)
        self.assertEqual(d['stage2_days_remaining'],8)

    def test_stage2_late_signal_rejected(self):
        p=self.price();s=self.signals(p);s.loc[p.index[90],'stage1']=True;s.loc[p.index[-1],'stage2']=True
        d=build_strategy_snapshot(p,'MU',s)
        self.assertEqual(d['next_open_orders'],[])
        self.assertEqual(d['stage2_days_remaining'],0)

    def test_stage3_strict_confirm_on_last_close(self):
        p=self.price();s=self.signals(p);s.loc[p.index[-28],'stage1']=True
        s.loc[p.index[-16],'stage2']=True;s.loc[p.index[-1],'f6_s3_breakout']=True
        d=build_strategy_snapshot(p,'AMD',s)
        self.assertTrue(d['positions']['1']['held'])
        self.assertTrue(d['positions']['2']['held'])
        self.assertFalse(d['positions']['3']['held'])
        self.assertEqual(d['next_open_orders'][0]['stage'],3)
        self.assertEqual(d['next_open_orders'][0]['reason'],'ICHI_STRICT_CROSS')

    def test_only_strict_not_simple_cloud_triggers_buy3(self):
        p=self.price();s=self.signals(p);s.loc[p.index[-28],'stage1']=True;s.loc[p.index[-16],'stage2']=True
        d=build_strategy_snapshot(p,'AMD',s)
        self.assertEqual(d['next_open_orders'],[])
        self.assertEqual(d['state'],'HOLD_2')

    def test_stage3_a_bottom_not_top(self):
        p=self.price();s=self.signals(p);s.loc[p.index[90],'stage1']=True
        s.loc[p.index[95],'stage2']=True;s.loc[p.index[101],'f6_s3_breakout']=True
        # Below cloud TOP only. Should NOT sell stage 3 under adopted A model.
        p.loc[p.index[-1],'close']=102.0
        d=build_strategy_snapshot(p,'NVDA',s)
        self.assertTrue(d['positions']['3']['held'])
        self.assertTrue(d['signals_today']['cloud_top_break_comparison_only'])
        self.assertFalse(d['signals_today']['cloud_bottom_break'])
        self.assertEqual(d['next_open_orders'],[])

    def test_stage3_cloud_bottom_sell_next_open_only(self):
        p=self.price();s=self.signals(p);s.loc[p.index[90],'stage1']=True
        s.loc[p.index[95],'stage2']=True;s.loc[p.index[101],'f6_s3_breakout']=True
        p.loc[p.index[-1],'close']=90.
        d=build_strategy_snapshot(p,'NVDA',s)
        self.assertTrue(d['positions']['3']['held'])
        self.assertEqual([(x['side'],x['stage']) for x in d['next_open_orders']],[('SELL',3)])
        self.assertEqual(d['state'],'SELL_SIGNAL')

    def test_independent_sell_signals_can_coexist(self):
        p=self.price();s=self.signals(p);s.loc[p.index[90],'stage1']=True
        s.loc[p.index[95],'stage2']=True;s.loc[p.index[101],'f6_s3_breakout']=True
        s.loc[p.index[-1],['rsi_failure','macd_death']]=True
        p.loc[p.index[-1],'close']=90.
        d=build_strategy_snapshot(p,'NVDA',s)
        self.assertEqual({(x['side'],x['stage']) for x in d['next_open_orders']},
                         {('SELL',1),('SELL',2),('SELL',3)})

    def test_no_reentry_same_day_last_position_exits_at_open(self):
        p=self.price();s=self.signals(p);s.loc[p.index[90],'stage1']=True
        s.loc[p.index[-2],'rsi_failure']=True;s.loc[p.index[-1],'stage1']=True
        d=build_strategy_snapshot(p,'MU',s)
        self.assertFalse(d['virtual_campaign_open'])
        self.assertEqual(d['next_open_orders'],[])

    def test_partial_lot_sale_not_rebought_in_campaign(self):
        p=self.price();s=self.signals(p);s.loc[p.index[90],'stage1']=True
        s.loc[p.index[95],'stage2']=True;s.loc[p.index[101],'f6_s3_breakout']=True
        s.loc[p.index[160],'macd_death']=True
        s.loc[p.index[-1],'stage2']=True
        d=build_strategy_snapshot(p,'NVDA',s)
        self.assertTrue(d['positions']['3']['held'])
        self.assertFalse(d['positions']['2']['held'])
        self.assertTrue(d['positions']['2']['ever_bought_in_campaign'])
        self.assertEqual(d['next_open_orders'],[])

    def test_snapshot_serializes_strict_json(self):
        p=self.price();s=self.signals(p)
        value=build_strategy_snapshot(p,'DRAM',s)
        text=json.dumps(value,allow_nan=False,ensure_ascii=False)
        self.assertEqual(json.loads(text)['version'],'F9-A')
        self.assertEqual(value['lot3_exit'],'A / cloud-bottom close break')

    def test_normalizer_rejects_too_few_days(self):
        p=self.price(115);p.columns=[x.title() for x in p.columns]
        with self.assertRaisesRegex(ValueError,'at least 120'):
            normalize(p)

    def test_updater_emits_verified_strategy_json(self):
        p=self.price(165)
        with TemporaryDirectory() as tmp:
            out=update_all(fetcher=lambda ticker:p,root=Path(tmp))
            self.assertEqual(len(out['updated']),4)
            json_path=Path(tmp)/'NVDA.json'
            data=json.loads(json_path.read_text())
            self.assertEqual(data['strategy']['version'],'F9-A')
            self.assertEqual(data['strategy']['asof'],data['rows'][-1]['date'])
            self.assertEqual(len(data['rows']),165)
            self.assertTrue((Path(tmp)/'update_status.json').exists())


if __name__=='__main__':
    import unittest
    unittest.main()
