"""Refresh the existing iPhone PWA's four watchlist symbols using the F9-A engine.

Prices downloaded through the latest completed candle, not a future market date.
Each JSON contains ordinary OHLCV and a server-calculated strategy snapshot.
Preserves previously published JSON when one symbol cannot be downloaded.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from signal_snapshot import build_strategy_snapshot

WATCHLIST = ('DRAM', 'NVDA', 'MU', 'AMD')
START = '2020-01-01'
DATA_DIR = Path(__file__).resolve().parent / 'data'


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError('Yahoo Finance returned no OHLCV records')
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    names = {str(c).lower():c for c in df.columns}
    cols = ('open','high','low','close','volume')
    if any(x not in names for x in cols):
        raise ValueError('Missing OHLCV columns')
    df = df[[names[x] for x in cols]]
    df.columns = list(cols)
    index = pd.DatetimeIndex(df.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    df.index = index.normalize()
    df = df[~df.index.duplicated(keep='last')].sort_index()
    df = df.apply(pd.to_numeric,errors='coerce').dropna()
    df = df[(df.open>0)&(df.close>0)&(df.high>=df.low)&(df.high>=df.open)&
            (df.high>=df.close)&(df.low<=df.open)&(df.low<=df.close)&(df.volume>=0)]
    if len(df) < 120:
        raise ValueError(f'Need at least 120 valid trading days; got {len(df)}')
    if df.index[-1].date() > datetime.now(timezone.utc).date() + timedelta(days=1):
        raise ValueError('Future OHLCV candle detected')
    return df


def download(ticker: str) -> pd.DataFrame:
    end = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
    raw = yf.download(ticker,start=START,end=end,auto_adjust=False,progress=False,
                      threads=False,actions=False)
    return normalize(raw)


def update_all(fetcher=None, root=DATA_DIR) -> dict:
    fetcher = fetcher or download
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    good=[];errors=[]
    for ticker in WATCHLIST:
        try:
            prices = fetcher(ticker)
            if not isinstance(prices,pd.DataFrame):
                raise ValueError('Non-DataFrame prices')
            prices = normalize(prices)
            strategy = build_strategy_snapshot(prices,ticker)
            rows = [{'date':day.date().isoformat(),
                     'open':round(float(r.open),6),'high':round(float(r.high),6),
                     'low':round(float(r.low),6),'close':round(float(r.close),6),
                     'volume':int(r.volume)} for day,r in prices.iterrows()]
            data = {'ticker':ticker,'updated_at':datetime.now(timezone.utc).isoformat(),
                    'currency':'USD','rows':rows,'strategy':strategy}
            # One file per ticker. A failure must never replace valid prior data.
            target = root / f'{ticker}.json'
            temp = root / f'{ticker}.json.tmp'
            temp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
            temp.replace(target)
            good.append({'ticker':ticker,'asof':strategy['asof'],'rows':len(rows),
                         'state':strategy['state']})
            print(f'PWA F9-A {ticker}: {len(rows)} bars, {strategy["asof"]}, {strategy["state"]}',flush=True)
        except Exception as exc:
            errors.append({'ticker':ticker,'error':str(exc)[:250]})
            print(f'WARNING PWA {ticker}: {exc}',flush=True)
    result={'engine':'F9-A','updated_at':datetime.now(timezone.utc).isoformat(),
            'updated':good,'failed':errors}
    (root/'update_status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if len(good)<3:
        raise RuntimeError(f'PWA: too few refreshed tickers, {len(good)}/4')
    return result


if __name__ == '__main__':
    update_all()
