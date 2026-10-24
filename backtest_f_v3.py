"""F v3: ordered RSI -> MACD cross -> Ichimoku cloud/volume-profile confirmation.
Frozen study ASOF 2026-10-22. Research only; no changes to the live app.
Requires original backtest.py and backtest_15.py in repository.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import backtest_15 as base

OUT=Path('reports/f_signal_126_v3'); ASOF=base.ASOF
FEE=.001; HOLD=40; MAX_STAGE_GAP=20; VP_BARS=120; VP_BINS=32
# Fixed observation of Nasdaq-100 components ranked by market capitalization,
# retrieved 2026-10-24 from https://www.slickcharts.com/nasdaq100/marketcap
# Cap values are rounded USD billions. This is a RESEARCH SNAPSHOT, not historical
# index membership, not a daily updating ranking, and not independent validation.
# It deliberately does not call yfinance ticker.info/fast_info (which may return 0 caps).
# Two Alphabet share classes are counted separately because the source ranks securities.
# Symbols with short histories (e.g., SPCX) may have limited backtest coverage.
TOP50_SNAPSHOT_BILLIONS = """NVDA 5100
AAPL 5070
MSFT 3890
AMZN 2680
GOOGL 2020
SPCX 2010
GOOG 1890
META 1630
AVGO 1540
TSLA 1470
MU 995.57
WMT 951.97
AMD 845.24
ASML 606.81
PLTR 472.50
INTC 459.49
COST 444.87
CSCO 419.91
PANW 311.95
AMAT 300.04
LRCX 287.94
NFLX 274.28
CRWD 263.67
TXN 260.27
AMGN 238.96
LIN 235.58
ARM 224.62
SHOP 217.52
MRVL 205.13
GILD 193.85
KLAC 190.62
ADI 189.78
QCOM 187.29
PEP 185.05
SNDK 179.42
ISRG 159.93
TMUS 157.58
STX 143.71
VRTX 133.04
FTNT 132.22
WDC 128.01
ADP 121.37
BKNG 117.32
SBUX 115.34
PDD 112.59
ADBE 102.80
MAR 102.03
ABNB 101.79
DDOG 96.94
CSX 94.29
"""
TOP50_SOURCE = 'https://www.slickcharts.com/nasdaq100/marketcap'
TOP50_SNAPSHOT_DATE = '2026-10-24'


def top50_candidates():
    """Return a frozen, auditable 50-security ranking without metadata APIs."""
    rows = [dict(symbol=s, market_cap=float(cap) * 1e9)
            for s, cap in (line.split() for line in TOP50_SNAPSHOT_BILLIONS.splitlines())]
    symbols = [r['symbol'] for r in rows]
    if len(rows) != 50 or len(set(symbols)) != 50:
        raise AssertionError('Embedded market-cap snapshot must contain 50 unique securities')
    if any(a['market_cap'] < b['market_cap'] for a, b in zip(rows, rows[1:])):
        raise AssertionError('Embedded market-cap snapshot not descending')
    return rows, rows[:]


def indicators(p):
    c=p.close.astype(float); h=p.high.astype(float); l=p.low.astype(float)
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+gain/loss.replace(0,np.nan)); rsi=rsi.where(loss.ne(0),100)
    rsi=rsi.where(~(gain.eq(0)&loss.eq(0)),50)
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    signal=macd.ewm(span=9,adjust=False).mean()
    cross=(macd>signal)&(macd.shift(1)<=signal.shift(1))
    tenkan=(h.rolling(9).max()+l.rolling(9).min())/2
    kijun=(h.rolling(26).max()+l.rolling(26).min())/2
    # Chart plots Senkou spans 26 bars forward. The cloud VISIBLE at t was
    # computed at t-26, not at t+26. Never use future data.
    span_a=((tenkan+kijun)/2).shift(26)
    span_b=((h.rolling(52).max()+l.rolling(52).min())/2).shift(26)
    cloud_top=pd.concat([span_a,span_b],axis=1).max(axis=1)
    cloud_bottom=pd.concat([span_a,span_b],axis=1).min(axis=1)
    # First stage: RSI crossed upward out of <=30 within previous 5 sessions,
    # and RSI now 30..48, price closes up. Parameter choices are study assumptions.
    was_oversold=rsi.shift(1).rolling(5,min_periods=1).min()<=30
    stage1=was_oversold&rsi.between(30,48)&(c>c.shift(1))
    # Third stage: test cloud top intraday, recover above top at close;
    # volume profile must be calculated from PAST bars only (previous 120).
    cloud=(l<=cloud_top*1.01)&(c>cloud_top)&(c>c.shift(1))&(c>=cloud_bottom)
    vp=np.full(len(p),np.nan); typical=((h+l+c)/3).to_numpy()
    volume=p.volume.astype(float).to_numpy()
    for i in range(VP_BARS,len(p)):
        pp=typical[i-VP_BARS:i]; vv=volume[i-VP_BARS:i]
        if not (np.isfinite(pp).all() and np.isfinite(vv).all()):continue
        lo=float(np.min(pp)); hi=float(np.max(pp))
        if hi<=lo:continue
        edges=np.linspace(lo,hi,VP_BINS+1)
        bins=np.clip(np.searchsorted(edges,pp,side='right')-1,0,VP_BINS-1)
        weights=np.bincount(bins,weights=vv,minlength=VP_BINS)
        k=int(np.argmax(weights));vp[i]=(edges[k]+edges[k+1])/2
    # POC proximity to cloud zone and price; profile derived from yesterday and earlier.
    vp_match=np.isfinite(vp)&(np.abs(vp-cloud_top.to_numpy())/cloud_top.to_numpy()<=.04)&(np.abs(c.to_numpy()-vp)/vp<=.04)
    return pd.DataFrame({'stage1':stage1.fillna(False),'stage2':cross.fillna(False),
                         'cloud':cloud.fillna(False),'cloud_vp':(cloud&vp_match).fillna(False),
                         'rsi':rsi,'cloud_top':cloud_top,'vp_poc':vp},index=p.index)


def stage_events(sig, start, end):
    """One cohort, sequential signals; no signal after an earlier stage can be skipped."""
    stage1=sig.stage1.to_numpy(bool);stage2=sig.stage2.to_numpy(bool)
    cloud=sig.cloud.to_numpy(bool);cloudvp=sig.cloud_vp.to_numpy(bool)
    # Ichimoku visible cloud requires 52 + 26 = 78 history bars.
    # Volume-profile needs 120 bars but is OPTIONAL for the cloud-only strategy.
    # A shared 198-bar warmup incorrectly excluded the short-history DRAM ETF.
    anchors=[];i=max(start,78)
    while i+1+HOLD<=end:
        if not stage1[i]:i+=1;continue
        anchor=i;entry=i+1; end_signal=entry+HOLD-1
        results={}
        for variant,third in [('F_cloud',cloud),('F_cloud_vp',cloudvp)]:
            s2=next((j for j in range(anchor+1,min(anchor+MAX_STAGE_GAP+1,end_signal)) if stage2[j]),None)
            s3=next((j for j in range(s2+1,min(s2+MAX_STAGE_GAP+1,end_signal)) if third[j]),None) if s2 is not None else None
            results[variant]=(anchor,s2,s3)
        anchors.append((anchor,entry,results))
        i=entry+HOLD+1
    return anchors


def simulate(p,sig,phase,first,last,symbol):
    dates=p.index; allowed=np.flatnonzero((dates>=first)&(dates<=last))
    if len(allowed)<HOLD+2:return [],[],[]
    start,end=int(allowed[0]),int(allowed[-1]); anchors=stage_events(sig,start,end)
    oo=p.open.to_numpy(float);cc=p.close.to_numpy(float)
    summaries=[];trades=[];fills=[]
    for variant in ['F_lump','F_cloud','F_cloud_vp']:
        equity=np.ones(end-start+1); capital=1.; current=start; wins=[]; deployments=[];stage_counts=[0,0,0]
        for k,(signal_i,entry_i,events) in enumerate(anchors):
            equity[current-start:entry_i-start]=capital
            exit_i=entry_i+HOLD
            cash=capital; shares=0.;initial=capital; invested=0.
            if variant=='F_lump': orders=[(entry_i,1.,1)]
            else:
                _,s2,s3=events[variant]
                orders=[(entry_i,1/9,1)]
                if s2 is not None:orders.append((s2+1,2/9,2))
                if s3 is not None:orders.append((s3+1,6/9,3))
            ordermap={i:(weight,stage) for i,weight,stage in orders if i<exit_i}
            for j in range(entry_i,exit_i):
                if j in ordermap:
                    weight,stage=ordermap[j];budget=initial*weight
                    if budget>cash+1e-9:raise AssertionError('Cash constraint')
                    qty=budget/(oo[j]*(1+FEE));shares+=qty;cash-=budget;invested+=weight
                    stage_counts[stage-1]+=1
                    fills.append({'phase':phase,'symbol':symbol,'variant':variant,'cohort':k+1,
                                  'stage':stage,'date':str(dates[j].date()),'price':oo[j],
                                  'weight':weight,'cash_after':cash})
                equity[j-start]=cash+shares*cc[j]*(1-FEE)
            capital=cash+shares*oo[exit_i]*(1-FEE)
            equity[exit_i-start]=capital
            ret=capital/initial-1;wins.append(ret);deployments.append(invested)
            trades.append({'phase':phase,'symbol':symbol,'variant':variant,'cohort':k+1,
                           'entry':str(dates[entry_i].date()),'exit':str(dates[exit_i].date()),
                           'return':ret,'stages':len(orders),'invested_fraction':invested})
            current=exit_i+1
        equity[current-start:]=capital
        peak=np.maximum.accumulate(np.r_[1.,equity])[1:]
        summaries.append({'phase':phase,'symbol':symbol,'variant':variant,'trades':len(wins),
                          'win_rate':float(np.mean(np.array(wins)>0)) if wins else None,
                          'cumulative_return':capital-1,'cagr':capital**(252/len(equity))-1,
                          'mdd':float(np.min(equity/peak-1)),
                          'avg_capital_used':float(np.mean(deployments)) if deployments else 0,
                          'stage1_fills':stage_counts[0],'stage2_fills':stage_counts[1],
                          'stage3_fills':stage_counts[2]})
    return summaries,trades,fills


def writecsv(name,rows,columns):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=columns);writer.writeheader();writer.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    top,ranked=top50_candidates()
    selected=[x['symbol'] for x in top]
    universe=list(base.UNIVERSE);seen={x[0] for x in universe}
    for sym in selected:
        if sym not in seen:universe.append((sym,sym,'Nasdaq_largecap','SPY'));seen.add(sym)
    prices={};errors=[];summaries=[];trades=[];fills=[]
    for sym,name,group,bench in universe:
        try:
            print('Fv3',sym,flush=True)
            p=base.fetch_prices(sym);prices[sym]=p
            ind=indicators(p)
            for phase,first,last in base.PHASES:
                a,b,c=simulate(p,ind,phase,first,last,sym)
                summaries+=a;trades+=b;fills+=c
        except Exception as exc:
            errors.append({'symbol':sym,'error':str(exc)[:250]})
            print('WARN',sym,exc,flush=True)
    writecsv('selected_top50.csv',top,['symbol','market_cap'])
    writecsv('candidate_market_caps.csv',ranked,['symbol','market_cap'])
    writecsv('summary.csv',summaries,list(summaries[0]) if summaries else ['phase','symbol','variant'])
    writecsv('trades.csv',trades,list(trades[0]) if trades else ['phase','symbol','variant'])
    writecsv('fills.csv',fills,list(fills[0]) if fills else ['phase','symbol','variant'])
    writecsv('errors.csv',errors,['symbol','error'])
    lines=['# F v3 RSI → MACD → Ichimoku/Volume Profile, 1:2:6','',
           f'Price-data cutoff: {ASOF}. Frozen market-cap snapshot observed {TOP50_SNAPSHOT_DATE}.',
           f'Selection: Nasdaq-100 market-cap top 50 securities, source: {TOP50_SOURCE}. NOT historical membership.',
           'Stage 1 RSI rebound; stage 2 strict MACD golden cross after stage 1; stage 3 cloud support after stage 2.',
           'F_cloud_vp also requires prior-120-bar POC proximity to cloud top and close.',
           'Stages execute next-session OPEN. Fees 0.1% each side. Unused cash earns 0%. Fixed 40-session exit.',
           'Parameters (RSI <=30 within 5 bars, stage gap <=20, cloud touch 1%, VP distance 4%) are hypotheses.',
           'No lookahead in indicator construction. Split/dividend/FX/tax/slippage not fully modeled.',
           'Current ranking backtested historically creates survivorship/selection bias; not out-of-sample.',
           '', '## 2024-2025 group-level summary (independent symbols, simple average)',
           '| variant | tickers | trades | avg cumulative return | avg MDD | win rate | stage 3 fills |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for v in ['F_lump','F_cloud','F_cloud_vp']:
        r=[x for x in summaries if x['phase']=='validation_2024_2025' and x['variant']==v]
        t=[x for x in trades if x['phase']=='validation_2024_2025' and x['variant']==v]
        if r:lines.append(f"| {v} | {len(r)} | {len(t)} | {np.mean([x['cumulative_return'] for x in r]):+.1%} | {np.mean([x['mdd'] for x in r]):+.1%} | {np.mean([x['return']>0 for x in t]) if t else 0:.1%} | {sum(x['stage3_fills'] for x in r)} |")
    lines+=['','## Download/analysis failures']+[f"- {x['symbol']}: {x['error']}" for x in errors]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    ok=len(prices)>=len(universe)-5 and set(base.REQUIRED).issubset(prices)
    (OUT/'run_metadata.json').write_text(json.dumps({'status':'success' if ok else 'incomplete',
        'price_asof':str(ASOF),'ranking_method':'frozen Nasdaq-100 market-cap top50 securities as observed 2026-10-24 (not historical membership)',
        'ranking_source':TOP50_SOURCE,'ranking_snapshot_date':TOP50_SNAPSHOT_DATE,
        'requested':len(universe),'downloaded':len(prices),'failed':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    if not ok:raise RuntimeError(f'Insufficient coverage {len(prices)}/{len(universe)}')

if __name__=='__main__':main()
