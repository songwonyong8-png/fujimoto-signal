"""Offline deterministic unit tests. Run: python -m unittest test_backtest_d.py -v"""
import unittest
import numpy as np
import pandas as pd
import sys
import types

# Allow local no-network unit tests; GitHub Actions installs real yfinance.
try:
    import yfinance
except ImportError:
    sys.modules["yfinance"] = types.ModuleType("yfinance")

import backtest_d as d


def synthetic_prices(n=160, override=None):
    dt = pd.bdate_range('2024-01-01', periods=n)
    close = 100 + np.arange(n) * .03
    op = close.copy()
    hi = close + 2
    lo = close - 2
    if override:
        for idx, (o, h, l, c) in override.items():
            op[idx], hi[idx], lo[idx], close[idx] = o,h,l,c
    return pd.DataFrame({'open':op,'high':hi,'low':lo,'close':close,
                         'volume':np.full(n, 1e6)},index=dt)


def sig_frame(prices, locs):
    s = pd.DataFrame(index=prices.index)
    s['A'] = False
    s.iloc[locs, 0] = True
    return s


def run(p,s,variant,first=None,last=None):
    return d.simulate(p,s,'TEST','Test','Semiconductor',None,'test',
                      first or p.index[70], last or p.index[135],variant)


class DExitChecks(unittest.TestCase):
    def test_D0_matches_legacy_A_entry_trades_and_equity(self):
        p=synthetic_prices()
        s=sig_frame(p,[74,79,99,115,129])
        new,tr,_=run(p,s,'D0_hold20')
        old, ot, _=d.expansion.build_one(p,s,'TEST','Test','Semiconductor',None,
                                         'test', p.index[70], p.index[135],'A')
        self.assertEqual([r['entry_date'] for r in tr],[r['entry_date'] for r in ot])
        self.assertEqual(new['closed_trades'], old['closed_trades'])
        self.assertAlmostEqual(new['cumulative_return'],old['cumulative_return'],places=12)
        self.assertAlmostEqual(new['max_drawdown'],old['max_drawdown'],places=12)
        d.compare_a_baseline(p,s,'TEST','Test','Semiconductor',None,'test',
                             p.index[70],p.index[135],new,tr)

    def test_fixed_stop_gap_fills_at_bad_open(self):
        p=synthetic_prices(160,{75:(100,102,99,100), 76:(90,92,85,89)})
        s=sig_frame(p,[74]); summary,tr,_=run(p,s,'D1_stop5')
        self.assertEqual(tr[0]['exit_reason'],'stop_gap_open')
        self.assertEqual(tr[0]['exit_price'],90)
        self.assertLess(tr[0]['return'],-.10)

    def test_fixed_stop_intraday_fills_at_stop(self):
        p=synthetic_prices(160,{75:(100,102,99,100), 76:(100,101,94,96)})
        s=sig_frame(p,[74]); _,tr,_=run(p,s,'D1_stop5')
        self.assertEqual(tr[0]['exit_reason'],'stop_intraday')
        self.assertAlmostEqual(tr[0]['exit_price'],95.0)

    def test_trailing_stop_not_tightened_on_same_bar(self):
        p=synthetic_prices(160,{75:(100,120,95,118), 76:(109,110,107,108)})
        s=sig_frame(p,[74]); arr=np.full(len(p),4.0)
        _,tr,_=d.simulate(p,s,'TEST','Test','Semiconductor',None,'test',p.index[70],p.index[135],
                          'D3_trail2p5atr',atr_values=arr)
        self.assertEqual(tr[0]['exit_reason'],'stop_gap_open')
        self.assertEqual(tr[0]['exit_date'],str(p.index[76].date()))
        self.assertEqual(tr[0]['exit_price'],109)

    def test_intraday_low_wins_over_same_bar_high_for_trailing(self):
        # Initial stop 90, on entry day intraday low 89 even if high 130.
        p=synthetic_prices(160,{75:(100,130,89,125)})
        s=sig_frame(p,[74]); arr=np.full(len(p),4.0)
        _,tr,_=d.simulate(p,s,'TEST','Test','Semiconductor',None,'test',p.index[70],p.index[135],
                          'D3_trail2p5atr',atr_values=arr)
        self.assertEqual(tr[0]['exit_reason'],'stop_intraday')
        self.assertEqual(tr[0]['exit_price'],90)

    def test_phase_end_open_position_not_closed_or_win(self):
        p=synthetic_prices()
        s=sig_frame(p,[132]); row,tr,_=run(p,s,'D0_hold20')
        self.assertEqual(row['closed_trades'],0)
        self.assertEqual(row['open_positions'],1)
        self.assertIsNone(row['win_rate'])
        self.assertEqual(tr[0]['status'],'OPEN_MTM')

    def test_time_exit_at_open_ignores_same_day_low(self):
        p=synthetic_prices(160,{75:(100,102,99,100),85:(100,102,80,100)})
        s=sig_frame(p,[74]); row,tr,_=run(p,s,'D4_hold10')
        self.assertEqual(tr[0]['exit_reason'],'time_open')
        self.assertEqual(tr[0]['exit_price'],100)

    def test_atr_uses_only_completed_sessions(self):
        p=synthetic_prices()
        a=d.wilder_atr(p)
        p2=p.copy(); p2.iloc[100,p2.columns.get_loc('high')]=500
        b=d.wilder_atr(p2)
        np.testing.assert_array_equal(a[:100],b[:100])
        self.assertTrue(np.isnan(a[0]))
        self.assertTrue(np.isfinite(a[20]))

if __name__ == '__main__':
    unittest.main()
