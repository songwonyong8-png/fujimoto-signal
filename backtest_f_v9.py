"""F9: frozen RSI -> MACD -> strict Ichimoku 1:2:6 entry; compare stage-3 EXIT ONLY.

Independent lots:
    lot 1 RSI back <=30; lot 2 MACD death cross.
    lot 3 A: close below the displayed Ichimoku CLOUD BOTTOM.
          B: close below the displayed CLOUD TOP.
          C: two consecutive daily closes below CLOUD TOP.
All decisions at completed close[t], fill at next open[t+1], fee 0.1% each side.
No forced liquidation at research boundary, open trades marked to closing price
less estimated sell fee. Exactly 100 KOSPI and 100 NASDAQ100 snapshot symbols,
with market grouping and explicit missing-data accounting.

Universe is snapshot-selected, not historical constituent membership; research
only, no fully prospective test. Corporate actions/dividends/slippage/tax/FX
and exchange holiday alignment are not realistically modeled.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_15 as base
import backtest_f_v5 as v5
import backtest_f_v6 as v6

OUT = Path('reports/f_signal_exit_v9')
UNIVERSE_FILE = Path('universe_f9_snapshot.csv')
ASOF = base.ASOF
FEE = v5.FEE
WEIGHTS = v5.WEIGHTS
MAX_STAGE_GAP = v5.MAX_STAGE_GAP
STRATEGIES = ('A', 'B', 'C')
PHASES = (
    ('development_2021_2023',pd.Timestamp('2021-01-01'),pd.Timestamp('2023-12-31')),
    ('validation_2024_2025',pd.Timestamp('2024-01-01'),pd.Timestamp('2025-12-31')),
    ('year_2024',pd.Timestamp('2024-01-01'),pd.Timestamp('2024-12-31')),
    ('year_2025',pd.Timestamp('2025-01-01'),pd.Timestamp('2025-12-31')),
    ('exploratory_2026',pd.Timestamp('2026-01-01'),pd.Timestamp(ASOF)),
)
SUMMARY_COLS = ('phase market symbol model session_count completed_campaigns open_campaigns '
    'campaign_win_rate avg_completed_campaign_return avg_gain avg_loss profit_factor '
    'worst_completed_campaign cumulative_return mdd avg_exposure '
    'stage1_buys stage2_buys stage3_buys stage1_sells stage2_sells stage3_sells '
    'stage3_closed_win_rate stage3_mean_return stage3_worst_return stage3_mean_mae stage3_mean_mfe').split()
CAMPAIGN_COLS = ('phase market symbol model campaign status initial_equity first_signal entry '
    'last_mark_or_exit return stage3_bought stage3_sold exit_reasons hold_bars').split()
LOT_COLS = ('phase market symbol model campaign stage status signal_date entry_date exit_date '
    'reason entry_open exit_price net_return hold_bars mae mfe').split()
FILL_COLS = ('phase market symbol model campaign date signal_date side stage reason '
    'price shares cash_after').split()
MARKET_COLS = ('phase market model ranked_symbols downloaded_with_phase_prices '
    'mean_ticker_return median_ticker_return mean_ticker_mdd '
    'positive_tickers stage3_buys stage3_sells completed_campaigns '
    'campaign_wins campaign_win_rate mean_actual_exposure').split()
PORT_COLS = ('phase market model market_dates total_initial_accounts '
    'cumulative_return max_drawdown exposure_days_note').split()
OUTLIER_COLS = ('phase market candidate ranking_source excluded_top_n excluded_symbols '
    'remaining_symbols mean_excess_return median_excess_return mean_excess_mdd '
    'better equal worse').split()
MATCH_COLS = ('phase market symbol entry_date model_a_net_return model_b_net_return '
    'model_c_net_return model_a_hold_days model_b_hold_days model_c_hold_days '
    'model_a_mae model_b_mae model_c_mae').split()


def read_universe(path=UNIVERSE_FILE):
    """Freeze the *ranked source security set*; never silently refill failures."""
    with Path(path).open(encoding='utf-8-sig',newline='') as fd:
        rows=list(csv.DictReader(fd))
    if len(rows)!=200:raise ValueError('F9 expects precisely 200 ranked securities')
    for market in ('KOSPI','NASDAQ100'):
        group=[r for r in rows if r['market']==market]
        if len(group)!=100 or [int(x['rank']) for x in group]!=list(range(1,101)):
            raise ValueError(f'{market} must have 100 consecutively ranked rows')
        tickers=[r['yahoo_ticker'] for r in group]
        if len(set(tickers))!=100:raise ValueError(f'Duplicate ticker in {market}')
        if market=='KOSPI' and any(not t.endswith('.KS') for t in tickers):
            raise ValueError('KOSPI Yahoo tickers must have .KS suffix')
        if any(not r.get('source_url') for r in group):raise ValueError('Missing provenance')
    return rows


def stage3_exit(mode:str, i:int, closes:np.ndarray, top:np.ndarray, bottom:np.ndarray)->bool:
    """Today's completed signal. NaNs never trigger artificial exits."""
    if mode not in STRATEGIES:raise ValueError('Invalid F9 exit model')
    if i<0 or i>=len(closes):raise IndexError(i)
    x=closes[i]
    if mode=='A': return bool(np.isfinite(x) and np.isfinite(bottom[i]) and x<bottom[i])
    if mode=='B': return bool(np.isfinite(x) and np.isfinite(top[i]) and x<top[i])
    return bool(i>0 and np.isfinite(x) and np.isfinite(top[i]) and x<top[i]
                and np.isfinite(closes[i-1]) and np.isfinite(top[i-1])
                and closes[i-1]<top[i-1])


def lot_return(entry:float, exit_:float)->float:
    if min(entry,exit_)<=0 or not(np.isfinite(entry) and np.isfinite(exit_)):
        raise ValueError('Nonfinite trade fill')
    return exit_*(1-FEE)/(entry*(1+FEE))-1


def simulate(prices:pd.DataFrame,signals:pd.DataFrame,phase:str,first:pd.Timestamp,
             last:pd.Timestamp,market:str,symbol:str,model:str):
    """Per-ticker self-financing account; stages never bought twice per campaign.

    For fair execution, no reentry on a campaign's final exit day. A stage-3
    exit never forces a stage-1/2 exit, and vice versa.
    """
    if model not in STRATEGIES:raise ValueError('Unknown F9 model')
    indices=np.flatnonzero((prices.index>=first)&(prices.index<=last))
    if len(indices)<2:return None,[],[],[],pd.Series(dtype=float)
    start,end=map(int,(indices[0],indices[-1]))
    op=prices.open.to_numpy(float);cl=prices.close.to_numpy(float)
    high=prices.high.to_numpy(float);low=prices.low.to_numpy(float)
    top=signals.cloud_top.to_numpy(float);bottom=signals.cloud_bottom.to_numpy(float)
    rsi=signals.stage1.to_numpy(bool)
    macd=signals.stage2.to_numpy(bool)
    ichi=signals.f6_s3_breakout.to_numpy(bool)  # F6 strict, frozen
    rsi_fail=signals.rsi_failure.to_numpy(bool)
    macd_death=signals.macd_death.to_numpy(bool)
    cash=1.0;pos={1:None,2:None,3:None};pending=[]
    campaign=None;campaign_no=0;campaigns=[];lots=[];fills=[]
    exposure=[];daily=[];qty_buy=Counter();qty_sell=Counter()

    def value(i:int):
        return cash+sum(x['shares']*cl[i]*(1-FEE) for x in pos.values() if x)

    def current_lot(stage:int):return pos[stage] is not None

    def record_lot(stage:int,i:int,price:float,status:str,reason:str,signal_i:int|None):
        x=pos[stage]
        if x is None:raise AssertionError('Missing held lot')
        rr=lot_return(x['entry_price'],price)
        lots.append(dict(phase=phase,market=market,symbol=symbol,model=model,
                         campaign=campaign['id'],stage=stage,status=status,
                         signal_date=str(prices.index[x['signal_i']].date()),
                         entry_date=str(prices.index[x['entry_i']].date()),
                         exit_date=str(prices.index[i].date()),reason=reason,
                         entry_open=x['entry_price'],exit_price=price,net_return=rr,
                         hold_bars=i-x['entry_i'],mae=x['low']/x['entry_price']-1,
                         mfe=x['high']/x['entry_price']-1))
        return rr

    def finish_campaign(i:int,status:str):
        nonlocal campaign
        if campaign is None:return
        account=cash if status=='CLOSED' else value(i)
        campaigns.append(dict(phase=phase,market=market,symbol=symbol,model=model,
                              campaign=campaign['id'],status=status,
                              initial_equity=campaign['capital'],
                              first_signal=str(prices.index[campaign['signal']].date()),
                              entry=str(prices.index[campaign['entry']].date()),
                              last_mark_or_exit=str(prices.index[i].date()),
                              **{'return':account/campaign['capital']-1},
                              stage3_bought=campaign['bought'][3],
                              stage3_sold=campaign['sold'][3],
                              exit_reasons=';'.join(campaign['reasons']),
                              hold_bars=i-campaign['entry']))
        campaign=None

    for i in range(start,end+1):
        had_at_open=campaign is not None
        # Fill yesterday's signals at today's open (SELL before BUY).
        for action in sorted(pending,key=lambda a:(a['side']!='SELL',-a['stage'] if a['side']=='SELL' else a['stage'])):
            stage=action['stage'];price=float(op[i]);side=action['side']
            if not np.isfinite(price) or price<=0:raise ValueError('Bad next-open price')
            if side=='BUY':
                if stage==1:
                    if campaign or any(pos.values()):raise AssertionError('Overlapping campaigns')
                    campaign_no+=1
                    campaign={'id':campaign_no,'capital':cash,'signal':action['signal_i'],
                              'entry':i,'s2_signal':None,'bought':{1:False,2:False,3:False},
                              'sold':{1:False,2:False,3:False},'reasons':[]}
                if not campaign or campaign['bought'][stage]:raise AssertionError('Duplicate stage')
                if stage>1 and not current_lot(stage-1):
                    raise AssertionError('Missing prerequisite lot')
                budget=campaign['capital']*WEIGHTS[stage]
                if cash+1e-10<budget:raise AssertionError('Insufficient cash')
                shares=budget/(price*(1+FEE));cash-=budget
                pos[stage]={'shares':shares,'entry_i':i,'signal_i':action['signal_i'],
                            'entry_price':price,'low':price,'high':price}
                campaign['bought'][stage]=True
                if stage==2:campaign['s2_signal']=action['signal_i']
                qty_buy[stage]+=1
            else:
                if not campaign or not current_lot(stage):raise AssertionError('Sell nonexistent lot')
                held=pos[stage];shares=held['shares']
                cash+=shares*price*(1-FEE)
                record_lot(stage,i,price,'CLOSED',action['reason'],action['signal_i'])
                pos[stage]=None;qty_sell[stage]+=1
                campaign['sold'][stage]=True;campaign['reasons'].append(action['reason'])
            fills.append(dict(phase=phase,market=market,symbol=symbol,model=model,
                              campaign=campaign['id'],date=str(prices.index[i].date()),
                              signal_date=str(prices.index[action['signal_i']].date()),
                              side=side,stage=stage,reason=action['reason'],price=price,
                              shares=shares,cash_after=cash))
        pending=[]
        if campaign is not None and all(x is None for x in pos.values()):
            finish_campaign(i,'CLOSED')
        # Update highs/lows only for held shares AFTER today's open. If an
        # exit filled at today's OPEN, today's intraday high/low is excluded.
        for x in pos.values():
            if x:
                x['low']=min(x['low'],float(low[i]));x['high']=max(x['high'],float(high[i]))
        daily.append(value(i))
        gross=sum(x['shares']*cl[i] for x in pos.values() if x)
        exposure.append(gross/(cash+gross) if cash+gross>0 else 0.)
        if i==end:break
        if campaign is None:
            if not had_at_open and i>=78 and rsi[i]:
                pending=[{'side':'BUY','stage':1,'signal_i':i,'reason':'RSI_REBOUND'}]
            continue
        sells={}
        if current_lot(1) and rsi_fail[i]:sells[1]='RSI_BACK_BELOW_30'
        if current_lot(2) and macd_death[i]:sells[2]='MACD_DEATH_CROSS'
        if current_lot(3) and stage3_exit(model,i,cl,top,bottom):
            sells[3]={'A':'CLOUD_BOTTOM_BREAK','B':'CLOUD_TOP_BREAK','C':'CLOUD_TOP_TWO_CLOSES'}[model]
        if sells:
            pending=[{'side':'SELL','stage':s,'signal_i':i,'reason':why} for s,why in sells.items()]
            continue
        if (current_lot(1) and not campaign['bought'][2] and i>campaign['signal']
                and i-campaign['signal']<=MAX_STAGE_GAP and macd[i]):
            pending=[{'side':'BUY','stage':2,'signal_i':i,'reason':'MACD_GOLDEN'}]
        elif (current_lot(1) and current_lot(2) and not campaign['bought'][3]
              and i>campaign['s2_signal'] and i-campaign['s2_signal']<=MAX_STAGE_GAP
              and ichi[i]):
            pending=[{'side':'BUY','stage':3,'signal_i':i,'reason':'ICHI_STRICT_CROSS'}]

    if campaign is not None:
        for stage in (1,2,3):
            if pos[stage]:record_lot(stage,end,float(cl[end]),'OPEN_MTM','BOUNDARY_MARK',None)
        finish_campaign(end,'OPEN_MTM')
    eq=np.array(daily,float)
    if not (len(eq) and np.isfinite(eq).all() and np.min(eq)>=0):raise AssertionError('Invalid account equity')
    peak=np.maximum.accumulate(np.r_[1.,eq])[1:]
    completed=[x for x in campaigns if x['status']=='CLOSED'];returns=np.array([x['return'] for x in completed],float)
    lot3_closed=[x for x in lots if x['stage']==3 and x['status']=='CLOSED']
    wins=returns[returns>0];loss=returns[returns<=0]
    gross_gain=float(np.sum(wins));gross_loss=float(-np.sum(loss))
    pf=gross_gain/gross_loss if gross_loss>0 else None
    out=dict(phase=phase,market=market,symbol=symbol,model=model,
             session_count=len(eq),completed_campaigns=len(completed),
             open_campaigns=sum(x['status']!='CLOSED' for x in campaigns),
             campaign_win_rate=float(np.mean(returns>0)) if len(returns) else None,
             avg_completed_campaign_return=float(np.mean(returns)) if len(returns) else None,
             avg_gain=float(np.mean(wins)) if len(wins) else None,
             avg_loss=float(np.mean(loss)) if len(loss) else None,
             profit_factor=pf,
             worst_completed_campaign=float(np.min(returns)) if len(returns) else None,
             cumulative_return=float(eq[-1]-1),mdd=float(np.min(eq/peak-1)),
             avg_exposure=float(np.mean(exposure)),
             **{f'stage{k}_buys':qty_buy[k] for k in (1,2,3)},
             **{f'stage{k}_sells':qty_sell[k] for k in (1,2,3)},
             stage3_closed_win_rate=float(np.mean([x['net_return']>0 for x in lot3_closed])) if lot3_closed else None,
             stage3_mean_return=float(np.mean([x['net_return'] for x in lot3_closed])) if lot3_closed else None,
             stage3_worst_return=float(np.min([x['net_return'] for x in lot3_closed])) if lot3_closed else None,
             stage3_mean_mae=float(np.mean([x['mae'] for x in lot3_closed])) if lot3_closed else None,
             stage3_mean_mfe=float(np.mean([x['mfe'] for x in lot3_closed])) if lot3_closed else None)
    return out,campaigns,lots,fills,pd.Series(eq,index=prices.index[start:end+1],name=symbol)


def summarise_market(summaries:list[dict],phase:str,market:str,model:str)->dict:
    selected=[x for x in summaries if x['phase']==phase and x['market']==market and x['model']==model]
    if not selected:return {}
    r=np.array([x['cumulative_return'] for x in selected],float)
    mdd=np.array([x['mdd'] for x in selected],float)
    n=sum(int(x['completed_campaigns']) for x in selected)
    w=sum(round(float(x['campaign_win_rate'])*int(x['completed_campaigns']))
          for x in selected if x['campaign_win_rate'] is not None)
    return dict(phase=phase,market=market,model=model,ranked_symbols=100,
                downloaded_with_phase_prices=len(selected),
                mean_ticker_return=float(r.mean()),median_ticker_return=float(np.median(r)),
                mean_ticker_mdd=float(mdd.mean()),positive_tickers=int(np.sum(r>0)),
                stage3_buys=sum(x['stage3_buys'] for x in selected),
                stage3_sells=sum(x['stage3_sells'] for x in selected),
                completed_campaigns=n,campaign_wins=w,
                campaign_win_rate=w/n if n else None,
                mean_actual_exposure=float(np.mean([x['avg_exposure'] for x in selected])))


def equal_weight_portfolio(equities:dict[str,pd.Series],
                           market_dates:pd.DatetimeIndex,expected:int=100)->pd.Series:
    """Equal initial allocation per ranked name; missing/no-history name stays CASH.

    Each self-financing account earns 0 before its own first available bar,
    and its last equity is carried forward over market-specific holidays.
    """
    if expected<1:raise ValueError('Expected count must be positive')
    dates=pd.DatetimeIndex(market_dates).sort_values().unique()
    if not len(dates):return pd.Series(dtype=float)
    total=np.zeros(len(dates),float)
    for series in equities.values():
        aligned=series.reindex(dates).ffill().fillna(1.)
        total+=aligned.to_numpy(float)-1
    return pd.Series(1+total/expected,index=dates)


def outlier_sensitivity(summaries:list[dict],phase:str,market:str,candidate:str,
                        baseline:str='A',counts=(0,1,3,5,10))->list[dict]:
    indexed={(r['symbol'],r['model']):r for r in summaries
             if r['phase']==phase and r['market']==market}
    universe=sorted(s for s,c in indexed if c==baseline and (s,candidate) in indexed)
    ref={s:indexed[s,baseline] for s in universe};cand={s:indexed[s,candidate] for s in universe}
    out=[]
    for method in ('baseline','candidate'):
        ranking=ref if method=='baseline' else cand
        order=sorted(universe,key=lambda s:(-ranking[s]['cumulative_return'],s))
        for n in counts:
            rem=[s for s in universe if s not in set(order[:n])]
            if not rem:continue
            dr=np.array([cand[s]['cumulative_return']-ref[s]['cumulative_return'] for s in rem])
            dm=np.array([cand[s]['mdd']-ref[s]['mdd'] for s in rem])
            out.append(dict(phase=phase,market=market,candidate=candidate,
                ranking_source=method,excluded_top_n=n,excluded_symbols=';'.join(order[:n]),
                remaining_symbols=len(rem),mean_excess_return=float(np.mean(dr)),
                median_excess_return=float(np.median(dr)),mean_excess_mdd=float(np.mean(dm)),
                better=int(np.sum(dr>1e-10)),equal=int(np.sum(np.abs(dr)<=1e-10)),
                worse=int(np.sum(dr< -1e-10))))
    return out


def matched_third_lots(lots:list[dict],phase:str)->list[dict]:
    """Strict same-date stage-3 entry across 3 exit models; *closed* in all 3.

    This is conditional on common entry and complete liquidation, so it is
    supplementary to the main intention-to-test account study.
    """
    d={}
    for x in lots:
        if x['phase']!=phase or x['stage']!=3 or x['status']!='CLOSED':continue
        d[(x['market'],x['symbol'],x['entry_date'],x['model'])]=x
    base=sorted({(m,s,e) for m,s,e,v in d})
    out=[]
    for m,s,e in base:
        if not all((m,s,e,v) in d for v in STRATEGIES):continue
        a,b,c=(d[m,s,e,v] for v in STRATEGIES)
        out.append(dict(phase=phase,market=m,symbol=s,entry_date=e,
            model_a_net_return=a['net_return'],model_b_net_return=b['net_return'],
            model_c_net_return=c['net_return'],
            model_a_hold_days=a['hold_bars'],model_b_hold_days=b['hold_bars'],
            model_c_hold_days=c['hold_bars'],
            model_a_mae=a['mae'],model_b_mae=b['mae'],model_c_mae=c['mae']))
    return out


def write_csv(path,rows,cols):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def fmt(v):return '—' if v is None else f'{v:+.2%}'


def make_report(market_rows,portfolio_rows,outliers,matched,errors,asof:str):
    lines=['# F9: 1:2:6 fixed BUY, three stage-3 EXIT alternatives, 200-stock ranking snapshot','',
        f'OHLCV price cut-off: **{asof}**; market-cap snapshot from published ranking sources, not point-in-time 2024 constituents.',
        'KOSPI market-cap top100 common equities (Korea Stock Exchange list), NASDAQ100 top100 listed share classes by weight.',
        'Sources: https://stockanalysis.com/list/korea-stock-exchange/ ; https://www.slickcharts.com/nasdaq100 .',
        '**Survivorship bias:** current top100 lists projected backward; NOT prospective out-of-sample.',
        '', '## Frozen entry logic (identical across all A/B/C)',
        '- 1/9: RSI(14) <=30 in preceding 5 trading days; today RSI 30..48 and close>prior close.',
        '- 2/9: MACD(12/26/9) golden-cross after first RSI within 20 trading days, while lot1 held.',
        '- 6/9: strict Ichimoku breakout: Tenkan>Kijun and rising Kijun; Chikou close[t]>high[t-26]; close crosses ABOVE visible cloud top at t; <=20 sessions after MACD and both lots held.',
        '- RSI <=30 exits lot1 only; MACD death exits lot2 only; no RSI 70 profit sale, no VP condition.',
        '- A: close below cloud BOTTOM exits lot3; B: close below cloud TOP exits lot3; C: TWO consecutive closes below cloud TOP exit lot3.',
        '- Orders fill on next session OPEN, 0.1% fees on each buy/sell. No slippage, dividends, taxes, currency FX, stock-borrow, live liquidity simulation.',
        '- Closed campaign win rate is based on *entire campaign* return; lot3 win rate is calculated on actually exited lot3 positions.',
        '- OPEN_MTM campaigns mark the last known close less estimated selling fee; open lots are NOT counted as closed wins.',
        '- Market equal-initial-weight portfolios use 1/100 allocation each; unavailable and newly listed historical names remain in cash, NOT silently replaced.',
        '- Report periods are measured independently, NOT continuously carried over across phase boundaries.',
        '- Daily source is yfinance auto_adjust=False. Historical splits and corporate actions may influence results. KOSPI and US trading calendars are independent.',
        '', '## Per-market account results (per-symbol mean/median vs equal-weight portfolio)',
        '| Phase | Market | Exit model | Coverage | Avg ticker return | Median ticker return | Avg ticker MDD | 3rd buys | Campaign win | Portfolio return | Portfolio MDD |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    pp={(x['phase'],x['market'],x['model']):x for x in portfolio_rows}
    for phase in ('development_2021_2023','validation_2024_2025','year_2024','year_2025','exploratory_2026'):
        for market in ('KOSPI','NASDAQ100'):
            for mode in STRATEGIES:
                rr=next((x for x in market_rows if (x['phase'],x['market'],x['model'])==(phase,market,mode)),None)
                if rr is None:continue
                q=pp.get((phase,market,mode),{})
                lines.append(f'| {phase} | {market} | {mode} | {rr["downloaded_with_phase_prices"]}/100 | '
                             f'{fmt(rr["mean_ticker_return"])} | {fmt(rr["median_ticker_return"])} | '
                             f'{fmt(rr["mean_ticker_mdd"])} | {rr["stage3_buys"]} | '
                             f'{fmt(rr["campaign_win_rate"])} | {fmt(q.get("cumulative_return"))} | '
                             f'{fmt(q.get("max_drawdown"))} |')
    lines.extend(['','## Remove top 5 performers on SAME remaining names, by market (2024-2025)',
                  '| Market | Candidate | Ranking by | Remaining | Mean strategy advantage | Better / tie / worse |',
                  '|---|---|---|---:|---:|---:|'])
    for x in outliers:
        if x['phase']=='validation_2024_2025' and x['excluded_top_n']==5:
            lines.append(f'| {x["market"]} | {x["candidate"]} | {x["ranking_source"]} | '
                         f'{x["remaining_symbols"]} | {100*x["mean_excess_return"]:+.2f} pp | '
                         f'{x["better"]}/{x["equal"]}/{x["worse"]} |')
    lines+=['','## Matching actual stage-3 entries, 2024-2025','Matched only when the exact same ticker/date entered lot3 AND all models closed it before the window end.']
    for market in ('KOSPI','NASDAQ100'):
        a=[x for x in matched if x['market']==market]
        if a:
            lines.append(f'- {market}: {len(a)} matched exits; mean lot3 net A {fmt(float(np.mean([x["model_a_net_return"] for x in a])))}; '
                         f'B {fmt(float(np.mean([x["model_b_net_return"] for x in a])))}; '
                         f'C {fmt(float(np.mean([x["model_c_net_return"] for x in a])))}.')
        else:lines.append(f'- {market}: no fully matched closed lot3 entries; no causal claim made.')
    lines+=['','## Data coverage and errors',f'- Failures/warnings: {len(errors)}.',
            *[f'- {x["market"]}/{x["symbol"]}: {x["error"]}' for x in errors[:45]],
            '- See data_audit.csv and errors.csv for ALL names and coverage issues.',
            '- Preferred shares, ETF share classes and Nasdaq-listed non-index stocks are not included: the selection definition is in the locked universe CSV.',
            '- 2024-25 has been explored repeatedly in earlier F3-F8; metrics are retrospective research, not fresh unbiased validation.',
            '- One symbol can contribute multiple campaigns and lots; correlation across stock/industry exists.',
            '', '## Output files',
            '- universe_snapshot.csv, data_audit.csv, account_summary.csv, campaign_trades.csv, lot_trades.csv, fills.csv',
            '- market_summary.csv, market_portfolio.csv, market_daily_equity.csv, outlier_sensitivity.csv, matched_stage3.csv, errors.csv, run_metadata.json.','']
    return '\n'.join(lines)+'\n'


def main(universe_path=UNIVERSE_FILE,fetcher=None,out=OUT):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    selections=read_universe(universe_path)
    if fetcher is None:fetcher=base.fetch_prices
    summaries=[];campaigns=[];lot_trades=[];fills=[];audit=[];errors=[]
    market_series=defaultdict(dict);market_dates=defaultdict(set)
    unique_downloaded=Counter()
    for k,meta in enumerate(selections,1):
        symbol=meta['yahoo_ticker'];market=meta['market']
        try:
            print(f'F9 [{k:03d}/200] {market} {symbol}',flush=True)
            price=fetcher(symbol)
            if price.index[-1].date()>ASOF:raise ValueError('Future price bar found')
            if len(price)<120:raise ValueError('Less than 120 history bars')
            sig=v6.indicators(price)
            unique_downloaded[market]+=1
            audit.append(dict(market=market,symbol=symbol,rank=meta['rank'],status='DOWNLOADED',
                bars=len(price),first=str(price.index[0].date()),last=str(price.index[-1].date()),error=''))
            for phase,first,last in PHASES:
                days=price.index[(price.index>=first)&(price.index<=last)]
                if len(days)<2:continue
                key=(phase,market)
                market_dates[key].update(days)
                for model in STRATEGIES:
                    row,camp,lots,ff,eq=simulate(price,sig,phase,first,last,market,symbol,model)
                    if row is not None:
                        summaries.append(row);campaigns.extend(camp);lot_trades.extend(lots);fills.extend(ff)
                        market_series[(phase,market,model)][symbol]=eq
        except Exception as exc:
            message=str(exc).replace('\n',' ')[:300]
            print('F9 WARN',symbol,message,flush=True)
            audit.append(dict(market=market,symbol=symbol,rank=meta['rank'],status='ERROR',
                              bars=0,first='',last='',error=message))
            errors.append(dict(market=market,symbol=symbol,error=message))

    market_rows=[];portfolio_rows=[];daily_equity=[]
    for phase,first,last in PHASES:
        for market in ('KOSPI','NASDAQ100'):
            dates=pd.DatetimeIndex(sorted(market_dates[(phase,market)]))
            for model in STRATEGIES:
                summary=summarise_market(summaries,phase,market,model)
                if summary:market_rows.append(summary)
                portfolios=equal_weight_portfolio(market_series[(phase,market,model)],dates,100)
                if portfolios.empty:continue
                peak=np.maximum.accumulate(np.r_[1.,portfolios.values])[1:]
                portfolio_rows.append(dict(phase=phase,market=market,model=model,
                    market_dates=len(portfolios),total_initial_accounts=100,
                    cumulative_return=float(portfolios.iloc[-1]-1),
                    max_drawdown=float(np.min(portfolios.values/peak-1)),
                    exposure_days_note='Not a live rebalanced portfolio; missing prices hold cash'))
                for d,e in portfolios.items():
                    daily_equity.append(dict(phase=phase,market=market,model=model,
                                              date=str(d.date()),equity=float(e)))
    robust=[]
    for phase in ('validation_2024_2025','year_2024','year_2025','exploratory_2026'):
        for market in ('KOSPI','NASDAQ100'):
            for model in ('B','C'):
                robust.extend(outlier_sensitivity(summaries,phase,market,model))
    matches=matched_third_lots(lot_trades,'validation_2024_2025')
    write_csv(out/'universe_snapshot.csv',selections,list(selections[0].keys()))
    write_csv(out/'data_audit.csv',audit,['market','symbol','rank','status','bars','first','last','error'])
    write_csv(out/'account_summary.csv',summaries,SUMMARY_COLS)
    write_csv(out/'campaign_trades.csv',campaigns,CAMPAIGN_COLS)
    write_csv(out/'lot_trades.csv',lot_trades,LOT_COLS)
    write_csv(out/'fills.csv',fills,FILL_COLS)
    write_csv(out/'market_summary.csv',market_rows,MARKET_COLS)
    write_csv(out/'market_portfolio.csv',portfolio_rows,PORT_COLS)
    write_csv(out/'market_daily_equity.csv',daily_equity,['phase','market','model','date','equity'])
    write_csv(out/'outlier_sensitivity.csv',robust,OUTLIER_COLS)
    write_csv(out/'matched_stage3.csv',matches,MATCH_COLS)
    write_csv(out/'errors.csv',errors,['market','symbol','error'])
    (out/'report.md').write_text(make_report(market_rows,portfolio_rows,robust,matches,errors,str(ASOF)),encoding='utf-8')
    enough=unique_downloaded['KOSPI']>=85 and unique_downloaded['NASDAQ100']>=85
    metadata=dict(status='success' if enough else 'incomplete',
        data_asof=str(ASOF),universe_snapshot_retrieved='2026-10-25 (source may be cached)',
        universe_definition='KOSPI top100 common + Nasdaq100 index cap-weight top100 share classes',
        requested_by_market={'KOSPI':100,'NASDAQ100':100},downloaded_by_market=dict(unique_downloaded),
        required_minimum_by_market=85,errors=errors,
        frozen_entry='RSI 14 rebound -> MACD 12 26 9 golden -> strict Ichimoku 9 26 52',
        stage_weights={'1':WEIGHTS[1],'2':WEIGHTS[2],'3':WEIGHTS[3]},
        exit_models={'A':'cloud bottom 1 close','B':'cloud top 1 close','C':'cloud top 2 consecutive closes'},
        time_based_liquidation=False,fees_each_side=FEE,slippage=0.,
        out_of_sample=False,point_in_time_membership=False,
        account_rows=len(summaries),campaign_rows=len(campaigns),lot_rows=len(lot_trades),
        matched_stage3_closed=len(matches),warn_missing_current_top_names=True)
    (out/'run_metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'F9 completed {dict(unique_downloaded)}; {len(summaries)} account summaries; '
          f'{len(matches)} matched stage3 closed positions',flush=True)
    if not enough:
        raise RuntimeError('F9 insufficient current top100 data coverage; see errors.csv')
    return metadata


if __name__=='__main__':main()
