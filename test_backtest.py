"""Offline smoke tests use synthetic prices; NEVER interpret results as real market performance."""
from __future__ import annotations
import importlib
import sys
import types
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

if 'yfinance' not in sys.modules:
    sys.modules['yfinance'] = types.ModuleType('yfinance')
import backtest as b


def mock_prices(start, stop, seed):
    idx = pd.bdate_range(start, stop)
    rng = np.random.default_rng(seed)
    c = 42 * np.exp(np.cumsum(rng.normal(.0002, .026, len(idx))))
    o = np.r_[c[0], c[:-1]] * np.exp(rng.normal(0, .008, len(idx)))
    hi = np.maximum(o, c)*(1+np.abs(rng.normal(.01,.01,len(idx))))
    lo = np.minimum(o, c)*(1-np.abs(rng.normal(.01,.01,len(idx))))
    v = rng.integers(500000, 8000000, len(idx))
    return pd.DataFrame({'open':o,'high':hi,'low':lo,'close':c,'volume':v},index=idx)


def test_no_future_leak():
    d = mock_prices('2026-04-02', '2026-10-22', 12)
    a = b.indicators(d)
    e = d.copy()
    e.loc[e.index[115:], 'close'] *= 3.0
    p = b.indicators(e)
    assert a.iloc[:100][['A','B','C','score']].equals(p.iloc[:100][['A','B','C','score']])
    assert len(a) == len(d)
    for strategy in ('A','B','C'):
        trades = b.trades_for(d, a, 'DRAM', 'Extended', d.index[59], strategy)
        if trades:
            assert trades[0]['entry_date'] > trades[0]['signal_date']
            for t in trades:
                assert t['exit_date'] >= t['entry_date']
                assert t['status'] in ('CLOSED','OPEN_MTM')


def test_full_pipeline():
    real_load = b.load_prices
    real_out = b.OUT
    try:
        by_symbol = {
            'DRAM': mock_prices('2026-04-02', '2026-10-22', 13),
            '005930.KS': mock_prices('2021-01-01', '2026-10-22', 14),
            'NVDA': mock_prices('2021-01-01', '2026-10-22', 15),
        }
        b.load_prices = lambda s: by_symbol[s]
        with tempfile.TemporaryDirectory() as t:
            b.OUT = Path(t)
            b.main()
            assert (b.OUT/'backtest_summary.md').exists()
            d = pd.read_csv(b.OUT/'backtest_summary.csv')
            assert len(d) == 18
            assert all(x in set(d.ticker) for x in b.SYMBOLS)
    finally:
        b.load_prices = real_load
        b.OUT = real_out

if __name__ == '__main__':
    test_no_future_leak()
    test_full_pipeline()
    print('PASS: future-leak check, full report generation, three-symbol A/B/C routing')
