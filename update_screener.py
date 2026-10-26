"""F9-A 200-stock public signal snapshot for the mobile portfolio dashboard.

The sole authority for signal definitions is backtest_f_v6.indicators (the F9
backtest's input). No user portfolio data is fetched, stored, or published.
Data availability and timestamps are explicit; failed downloads never turn
into a synthetic buy/sell signal.
"""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from update_data import normalize
import backtest_f_v6 as v6

ROOT = Path(__file__).resolve().parent
UNIVERSE = ROOT / 'universe_f9_snapshot.csv'
TARGET = ROOT / 'data' / 'screener_f9a.json'
HISTORY_START = '2020-01-01'
BATCH_SIZE = 10
MIN_BARS = 120

# Grounded recognizable names; other securities display their actual ticker.
DISPLAY = {
    'DRAM':'DRAM ETF',
    '005930.KS':'삼성전자', '000660.KS':'SK하이닉스', '005380.KS':'현대자동차',
    '009150.KS':'삼성전기','373220.KS':'LG에너지솔루션','207940.KS':'삼성바이오로직스',
    '105560.KS':'KB금융','012450.KS':'한화에어로스페이스','000270.KS':'기아',
    '034020.KS':'두산에너빌리티','055550.KS':'신한지주', '032830.KS':'삼성생명',
    '068270.KS':'셀트리온', '012330.KS':'현대모비스', '006400.KS':'삼성SDI',
    '066570.KS':'LG전자','035420.KS':'NAVER','010120.KS':'LS ELECTRIC',
    '042660.KS':'한화오션','009540.KS':'HD한국조선해양','034730.KS':'SK',
    '000810.KS':'삼성화재', '005490.KS':'POSCO홀딩스','015760.KS':'한국전력',
    '051910.KS':'LG화학','096770.KS':'SK이노베이션','033780.KS':'KT&G',
    '035720.KS':'카카오','086790.KS':'하나금융지주','018260.KS':'삼성에스디에스',
    '000150.KS':'두산','003550.KS':'LG','003670.KS':'포스코퓨처엠',
    '259960.KS':'크래프톤','323410.KS':'카카오뱅크','005940.KS':'NH투자증권',
    '005830.KS':'DB손해보험','003490.KS':'대한항공','028050.KS':'삼성E&A',
    '024110.KS':'기업은행','039490.KS':'키움증권','316140.KS':'우리금융지주',
    '000100.KS':'유한양행','047050.KS':'포스코인터내셔널',
    'NVDA':'엔비디아','MU':'마이크론','AMD':'AMD','AAPL':'애플',
    'MSFT':'마이크로소프트','AMZN':'아마존','GOOGL':'알파벳 A','GOOG':'알파벳 C',
    'META':'메타','AVGO':'브로드컴','TSLA':'테슬라','NFLX':'넷플릭스',
    'INTC':'인텔','COST':'코스트코','ASML':'ASML','PLTR':'팔란티어',
    'WDC':'웨스턴디지털','STX':'시게이트','SNDK':'샌디스크',
    'ARM':'Arm','ADBE':'어도비','QCOM':'퀄컴','AMAT':'어플라이드머티어리얼즈',
    'RKLB':'로켓랩','SHOP':'쇼피파이','PDD':'핀둬둬','WMT':'월마트'
}


def read_universe(path: Path = UNIVERSE) -> list[dict]:
    with Path(path).open(encoding='utf-8-sig',newline='') as fp:
        src=list(csv.DictReader(fp))
    if len(src)!=200:
        raise ValueError(f'F9 universe must contain 200 ranked securities, got {len(src)}')
    output=[]
    for market in ('KOSPI','NASDAQ100'):
        subset=[r for r in src if r['market']==market]
        if len(subset)!=100 or [int(x['rank']) for x in subset]!=list(range(1,101)):
            raise ValueError(f'{market} ranks must contain 1 through 100')
        if len(set(x['yahoo_ticker'] for x in subset))!=100:
            raise ValueError(f'{market} duplicated ticker')
        for row in subset:
            ticker=row['yahoo_ticker']
            output.append({'symbol':ticker,'market':market,'rank':int(row['rank']),
                           'name':DISPLAY.get(ticker,ticker),
                           'currency':'KRW' if market=='KOSPI' else 'USD'})
    if len(set(x['symbol'] for x in output))!=200:
        raise ValueError('Duplicate cross-market ticker')
    # Explicitly retain the user's existing DRAM ETF watch item, outside the
    # 200 ranked common-equity universe. It does not displace a top-100 stock.
    output.insert(0, {'symbol':'DRAM','market':'ETF','rank':0,
                      'name':'DRAM ETF','currency':'USD'})
    return output


def safe_number(v, digits=5):
    try:
        number=float(v)
        return round(number,digits) if np.isfinite(number) else None
    except (ValueError,TypeError):
        return None


def safe_bool(v):
    return bool(v) if pd.notna(v) else False



def completed_daily_bars(prices:pd.DataFrame, market:str,
                         now:datetime|None=None) -> pd.DataFrame:
    """Never use an unfinished market-local daily candle as a close signal.

    KOSPI cash market closes at 15:30 KST; allow 40 minutes data latency.
    US regular session closes at 16:00 US/Eastern; allow 75 minutes latency.
    Early-close days are conservatively delayed, not anticipated.
    """
    if prices.empty:return prices
    current=now or datetime.now(timezone.utc)
    if current.tzinfo is None:raise ValueError('now must be timezone aware')
    if market=='KOSPI':
        local=current.astimezone(ZoneInfo('Asia/Seoul'))
        threshold=(16,10)
    else:
        local=current.astimezone(ZoneInfo('America/New_York'))
        threshold=(17,15)
    if prices.index[-1].date()==local.date() and (local.hour,local.minute)<threshold:
        return prices.iloc[:-1]
    return prices

def indicator_snapshot(prices:pd.DataFrame, meta:dict) -> dict:
    """One public signal record based exclusively on the last completed bar."""
    if len(prices)<MIN_BARS:
        raise ValueError(f'Need {MIN_BARS} trading days, got {len(prices)}')
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError('Prices must be unique and ordered')
    sig=v6.indicators(prices)
    s=sig.iloc[-1];close=prices.close.astype(float)
    line=close.ewm(span=12,adjust=False).mean()-close.ewm(span=26,adjust=False).mean()
    signal=line.ewm(span=9,adjust=False).mean()
    bottom=s.get('cloud_bottom')
    c=float(prices.close.iloc[-1]);p=float(prices.close.iloc[-2])
    result={**meta,'status':'OK','asof':str(prices.index[-1].date()),
        'close':safe_number(c,4),'previous_close':safe_number(p,4),
        'change_pct':safe_number((c/p-1)*100,3) if p>0 else None,
        'rsi14':safe_number(s.get('rsi'),2),
        'macd':safe_number(line.iloc[-1]),
        'macd_signal':safe_number(signal.iloc[-1]),
        'cloud_top':safe_number(s.get('cloud_top'),4),
        'cloud_bottom':safe_number(bottom,4),
        'signals':{
            'buy1':safe_bool(s.get('stage1',False)),
            'buy2':safe_bool(s.get('stage2',False)),
            'buy3':safe_bool(s.get('f6_s3_breakout',False)),
            'sell1':safe_bool(s.get('rsi_failure',False)),
            'sell2':safe_bool(s.get('macd_death',False)),
            'sell3':bool(np.isfinite(c) and bottom is not None and
                         pd.notna(bottom) and c<float(bottom)),
        },
        'recent_closes':[safe_number(x,3) for x in close.tail(50)],
        'bars':len(prices)}
    return result


def empty_record(meta:dict,reason='조회 전') -> dict:
    return {**meta,'status':'UNAVAILABLE','asof':None,'close':None,
            'previous_close':None,'change_pct':None,'rsi14':None,
            'macd':None,'macd_signal':None,'cloud_top':None,
            'cloud_bottom':None,
            'signals':{'buy1':False,'buy2':False,'buy3':False,
                       'sell1':False,'sell2':False,'sell3':False},
            'recent_closes':[], 'bars':0,'error':str(reason)[:180]}


def extract_prices(frame:pd.DataFrame,ticker:str,ticker_count:int) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError('Empty OHLCV response')
    if isinstance(frame.columns,pd.MultiIndex):
        for level in (0,1):
            if ticker in frame.columns.get_level_values(level):
                price=frame.xs(ticker,axis=1,level=level)
                return normalize(price)
        raise ValueError('Missing ticker in downloaded batch')
    if ticker_count!=1:
        raise ValueError('Expected multi-symbol download columns')
    return normalize(frame)


def download_batch(tickers:list[str]) -> pd.DataFrame:
    end=(datetime.now(timezone.utc).date()+timedelta(days=2)).isoformat()
    return yf.download(tickers=tickers,start=HISTORY_START,end=end,
        group_by='ticker',auto_adjust=False,progress=False,threads=True,
        actions=False,timeout=25)


def load_previous(path=TARGET) -> dict[str,dict]:
    try:
        d=json.loads(Path(path).read_text(encoding='utf-8'))
        return {r['symbol']:r for r in d.get('stocks',[]) if isinstance(r,dict) and r.get('symbol')}
    except (OSError,ValueError,TypeError,KeyError):
        return {}


def update_all(fetcher:Callable=download_batch, universe_path=UNIVERSE,
               output_path=TARGET, batch_size=BATCH_SIZE) -> dict:
    """Batch refresh; bounded isolated retry; atomically publish one JSON.

    Any failure is explicit, and older cached prices (if any) are marked
    STALE_CACHED, never presented as a current authoritative buy/sell signal.
    """
    stocks=read_universe(Path(universe_path));prior=load_previous(output_path)
    out=[];errors=[];fresh=0
    if batch_size<1:raise ValueError('batch_size must be positive')
    for offset in range(0,len(stocks),batch_size):
        group=stocks[offset:offset+batch_size]
        symbols=[x['symbol'] for x in group]
        try:
            raw=fetcher(symbols)
        except Exception as exc:
            raw=None
            print(f'Batch {offset//batch_size+1} failed: {str(exc)[:140]}',flush=True)
        for meta in group:
            ticker=meta['symbol']
            try:
                prices=extract_prices(raw,ticker,len(group))
                prices=completed_daily_bars(prices,meta['market'])
                item=indicator_snapshot(prices,meta)
                if not item['asof']:raise ValueError('Missing price timestamp')
                fresh+=1
            except Exception as exc:
                why=str(exc)[:180]
                prev=prior.get(ticker)
                if prev and prev.get('status')=='OK' and prev.get('asof'):
                    item={**prev,**meta,'status':'STALE_CACHED','error':why}
                else:
                    item=empty_record(meta,why)
                errors.append({'symbol':ticker,'error':why})
            out.append(item)
        print(f'F9-A screener scanned {len(out)}/{len(stocks)}; valid={fresh}',flush=True)
    now=datetime.now(timezone.utc).isoformat()
    payload={'version':'F9-A-PORTFOLIO-1','updated_at':now,
             'universe_snapshot':'2026-10-25 (fixed F9 100+100 universe)',
             'data_source':'Yahoo Finance via yfinance (unadjusted historical OHLCV)',
             'signal_definitions':'F9 RSI(14), MACD(12/26/9), strict Ichimoku; A exits',
             'total':len(out),'core_universe':200,'extras':['DRAM'],'fresh_count':fresh,'failed_count':len(errors),
             'stocks':out,'errors':errors}
    path=Path(output_path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')),
                   encoding='utf-8')
    tmp.replace(path)
    # Daily workflow succeeds only with reasonably broad fresh coverage.
    if fresh < 171:
        raise RuntimeError(f'Screener only refreshed {fresh}/{len(stocks)}; published explicit missing-data status')
    return payload

if __name__=='__main__':
    update_all()
