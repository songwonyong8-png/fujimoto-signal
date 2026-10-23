"""Tests for E matched-entry research. Run: python -m unittest test_backtest_e.py -v"""
from __future__ import annotations

import sys
import types
import unittest

import numpy as np
import pandas as pd

# Running test offline is possible without yfinance; live CI installs it.
try:
    import yfinance
except ImportError:
    sys.modules['yfinance'] = types.ModuleType('yfinance')

import backtest_e as e


def prices(n=270, override=None):
    date=pd.bdate_range('2024-01-01',periods=n)
    c=100 + np.arange(n)*.02
    o=c.copy()
    h=c+1.5
    l=c-1.5
    if override:
        for i, (oo,hh,ll,cc) in override.items():
            o[i],h[i],l[i],c[i] = oo,hh,ll,cc
    return pd.DataFrame({'open':o,'high':h,'low':l,'close':c,'volume':np.full(n,1e6)},index=date)


def signals(p,days):
    s=pd.DataFrame({'A':False},index=p.index)
    s.iloc[days,0]=True
    return s


def run(p,s,first=70,last=260):
    return e.simulate_common(p,s,'T','test','S',None,'validation_2024_2025',p.index[first],p.index[last])


class EStudyChecks(unittest.TestCase):
    def test_same_entry_dates_and_lockout(self):
        p=prices()
        s=signals(p,[72,73,80,100,115,130,140,200])
        summaries,trades,curve,pairs=run(p,s)
        entries={v:[x['entry_date'] for x in trades if x['variant']==v] for v in e.RULES}
        self.assertEqual(entries['E10_hold10'], entries['E20_hold20'])
        self.assertEqual(entries['E20_hold20'], entries['E40_hold40'])
        # Earliest 72 -> entry 73 exit40=113; next 115 -> entry 116 exit40=156;
        # 200 -> entry 201 exit40=241.
        self.assertEqual(len(pairs),3)
        self.assertEqual([x['entry_date'] for x in pairs],
                         [str(p.index[i].date()) for i in [73,116,201]])
        self.assertEqual({x['closed_trades'] for x in summaries},{3})

    def test_exit_next_open_exact_horizon_and_pair_differences(self):
        p=prices(270, {75:(100,102,99,101),85:(110,112,108,111),
                       95:(120,122,118,121),115:(140,142,138,141)})
        s=signals(p,[74])
        summaries,trades,_,pairs=run(p,s)
        t={x['variant']:x for x in trades}
        self.assertEqual([t[v]['exit_date'] for v in e.RULES],
                         [str(p.index[i].date()) for i in [85,95,115]])
        self.assertEqual([t[v]['exit_price'] for v in e.RULES], [110,120,140])
        self.assertAlmostEqual(pairs[0]['diff_40_minus_20'],
                               e.fee_return(100,140)-e.fee_return(100,120),places=12)
        self.assertEqual(pairs[0]['winner'],'E40')

    def test_exits_before_intraday_low_of_exit_day(self):
        p=prices(270,{75:(100,103,98,101),85:(111,112,50,60)})
        s=signals(p,[74]); _,tr,_,_=run(p,s)
        t=next(x for x in tr if x['variant']=='E10_hold10')
        self.assertEqual(t['exit_price'],111)
        self.assertGreater(t['mae_intraday'],-.10)

    def test_censored_end_signals_excluded_from_all_arms(self):
        p=prices()
        s=signals(p,[74,225,240,259])
        rows,tr,_,pairs=run(p,s,70,260)
        self.assertEqual(len(pairs),1)
        self.assertEqual({x['closed_trades'] for x in rows},{1})
        self.assertTrue(all(x['excluded_recent_signal_days']>=2 for x in rows))

    def test_cash_between_common_entries_and_capital_compounds(self):
        p=prices()
        s=signals(p,[74,160])
        rows,tr,curves,pairs=run(p,s)
        short={pd.Timestamp(x['date']):x['equity'] for x in curves if x['variant']=='E10_hold10'}
        self.assertEqual(len(pairs),2)
        # For 10-day arm, the equity after the 10-day exit remains flat until next entry.
        self.assertAlmostEqual(short[p.index[100]],short[p.index[120]],places=12)
        hold10=next(x for x in rows if x['variant']=='E10_hold10')
        cash_return=np.prod([1+x['return'] for x in tr if x['variant']=='E10_hold10'])-1
        self.assertAlmostEqual(hold10['cumulative_return'],cash_return,places=12)
        self.assertEqual(hold10['exposed_sessions'],20)
        self.assertAlmostEqual(hold10['exposure_bars_pct'],20/(260-70+1))

    def test_40_day_exit_original_A_fee_formula(self):
        p=prices();s=signals(p,[72])
        rows,tr,_,_=run(p,s)
        record=next(x for x in tr if x['variant']=='E20_hold20')
        old=e.expansion.legacy.fee_return(record['entry_price'],record['exit_price'])
        self.assertAlmostEqual(record['return'],old,places=12)

    def test_no_signal_no_trades_flat_equity(self):
        p=prices();s=signals(p,[])
        rows,tr,curves,pairs=run(p,s)
        self.assertEqual(len(rows),3)
        self.assertEqual(len(pairs),0)
        self.assertEqual(len(tr),0)
        self.assertTrue(all(x['cumulative_return']==0 for x in rows))
        self.assertTrue(all(x['max_drawdown']==0 for x in rows))
        self.assertTrue(all(x['equity']==1 for x in curves))

    def test_short_phase_is_absent(self):
        p=prices();s=signals(p,[72])
        rows,tr,curve,pairs=run(p,s,70,100)
        self.assertEqual((rows,tr,curve,pairs),([],[],[],[]))

    def test_no_lookahead_signal_change_future_price_only(self):
        p=prices();s=signals(p,[74])
        x1=run(p,s)[3][0]['entry_date']
        p2=p.copy();p2.iloc[200,p2.columns.get_loc('close')]=5000
        x2=run(p2,s)[3][0]['entry_date']
        self.assertEqual(x1,x2)

    def test_cagr_compounded_over_full_calendar(self):
        p=prices();s=signals(p,[74])
        rows,_,_,_=run(p,s)
        for r in rows:
            self.assertAlmostEqual(r['cagr_252'],(1+r['cumulative_return'])**(252/r['bars'])-1)


if __name__=='__main__':
    unittest.main()
