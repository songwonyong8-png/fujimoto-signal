"""F8 robust outlier sensitivity + independent indicator signal efficacy.

Research rules, fixed before this experiment:
- F7 cumulative returns are compared after excluding the SAME securities from
  all alternatives; rank top performers by F5-A baseline or each candidate.
- Compare 0, 1, 3, 5, 10 excluded top names, plus leave-one-out and top/bottom
  winsorization; never claim this is new out-of-sample performance.
- Standalone RSI, MACD, Ichimoku signals are evaluated next-session OPEN to
  next OPEN 5/10/20/40 sessions later with 0.1% buy/sell costs.
- Nonoverlapping forward-return events per indicator/horizon reduce but do not
  eliminate dependence. Same-security, same-period unconditional buy baseline.
- Separate indicator-exit round trips: RSI<=30 or RSI>=70, MACD dead cross,
  Ichimoku cloud bottom break. Never mix these with the fixed-horizon hit rate.
- Sequences (RSI -> MACD -> strict Ichimoku) must have their signals in order,
  with at most 20 trading days between stages.
- One event never observes future bars before signal close. Do not count open
  positions as closed-trade wins. No dividends, taxes, slippage, FX modeled.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_15 as base
import backtest_f_v3 as v3
import backtest_f_v5 as v5
import backtest_f_v6 as v6
import backtest_f_v7 as v7

OUT = Path('reports/f_signal_robustness_v8')
ASOF = base.ASOF
FEE = .001
HORIZONS = (5, 10, 20, 40)
EXCLUDE_COUNTS = (0, 1, 3, 5, 10)
PHASES = tuple(x for x in base.PHASES if x[0] in
               ('development_2021_2023', 'validation_2024_2025', 'exploratory_2026'))
CONFIGS = (
    v7.Config(False, 'base', False, 'cloud'),
    v7.Config(False, 'strict', False, 'cloud'),
    v7.Config(False, 'trend', False, 'cloud'),
    v7.Config(False, 'base', False, 'cloud_vp'),
    v7.Config(False, 'strict', False, 'cloud_vp'),
    v7.Config(False, 'trend', False, 'cloud_vp'),
)
SIGNALS = ('RSI_REBOUND', 'MACD_GOLDEN', 'ICHI_CLOUD_SUPPORT',
           'ICHI_STRICT', 'ICHI_TREND', 'MACD_AFTER_RSI',
           'ICHI_AFTER_RSI_MACD')
INDICATOR_EXITS = ('RSI_REBOUND', 'MACD_GOLDEN', 'ICHI_CLOUD_SUPPORT', 'ICHI_STRICT')


def pair_ret(buy_open, sell_open):
    """Full invested-price return after buy & sell fee."""
    if not (np.isfinite(buy_open) and np.isfinite(sell_open)) or min(buy_open,sell_open) <= 0:
        return np.nan
    return float((sell_open * (1-FEE)) / (buy_open * (1+FEE)) - 1)


def rank_winners(symbol_returns: dict[str,float], n: int) -> list[str]:
    if n < 0:
        raise ValueError('n must be nonnegative')
    return [k for k,_ in sorted(symbol_returns.items(),key=lambda x:(-x[1],x[0]))[:n]]


def robust_stats(rows: list[dict], phase='validation_2024_2025') -> tuple[list[dict],list[dict],list[dict]]:
    """Exclude identical securities per comparison, not just winning candidate lots.

    Ranking by baseline F5-A, then by each candidate (an intentionally harsher
    outcome-dependent check); report both, so user knows why ranking matters.
    Paired difference is average over same remaining symbols, not difference
    between different top-N-filtered universes.
    """
    indexed = {(r['symbol'],r['variant']):r for r in rows if r['phase']==phase}
    base_id=CONFIGS[0].name
    syms=sorted({s for s,v in indexed if v==base_id})
    syms=[s for s in syms if all((s,c.name) in indexed for c in CONFIGS)]
    comparisons=[];rankings=[];leaveone=[]
    for cand in CONFIGS:
        if cand.ichimoku == 'base':
            continue
        # Compare cloud+VP candidate against F5 cloud+VP, not against F5 cloud.
        baseline_id=v7.baseline(cand.profile).name
        baseline={s:float(indexed[(s,baseline_id)]['cumulative_return']) for s in syms}
        cand_ret={s:float(indexed[(s,cand.name)]['cumulative_return']) for s in syms}
        for source,ranking in [('baseline_f5',baseline),('candidate',cand_ret)]:
            for n in EXCLUDE_COUNTS:
                dropped=rank_winners(ranking,n)
                excluded=set(dropped)
                remaining=[s for s in syms if s not in excluded]
                if not remaining:continue
                deltas=np.array([cand_ret[s]-baseline[s] for s in remaining])
                deltamdd=np.array([float(indexed[(s,cand.name)]['mdd'])-
                                   float(indexed[(s,base_id)]['mdd']) for s in remaining])
                comparisons.append(dict(
                    phase=phase,candidate=cand.name,ranking_method=source,excluded_top_n=n,
                    excluded_symbols=';'.join(dropped),remaining_symbols=len(remaining),
                    base_mean=float(np.mean([baseline[s] for s in remaining])),
                    candidate_mean=float(np.mean([cand_ret[s] for s in remaining])),
                    mean_excess=float(np.mean(deltas)),median_excess=float(np.median(deltas)),
                    candidate_better=int(np.sum(deltas>1e-10)),
                    candidate_tie=int(np.sum(np.abs(deltas)<=1e-10)),
                    candidate_worse=int(np.sum(deltas< -1e-10)),
                    mean_mdd_difference=float(np.mean(deltamdd))))
        if not syms:continue
        diffs=np.array([cand_ret[s]-baseline[s] for s in syms])
        # Winsorized differences: cap 10% of both positive and negative tails.
        if len(diffs)>=10:
            low,high=np.quantile(diffs,(.1,.9));win_mean=float(np.mean(np.clip(diffs,low,high)))
            trim=int(len(diffs)*.1)
            trim_mean=float(np.mean(np.sort(diffs)[trim:len(diffs)-trim]))
        else:
            win_mean=trim_mean=float(np.mean(diffs))
        rankings.append(dict(phase=phase,candidate=cand.name,symbols=len(syms),
            baseline_top5=';'.join(rank_winners(baseline,5)),
            candidate_top5=';'.join(rank_winners(cand_ret,5)),
            mean_excess=float(np.mean(diffs)),median_excess=float(np.median(diffs)),
            winsor10_excess=win_mean,trim10_excess=trim_mean,
            better_symbols=int(np.sum(diffs>1e-10)),worse_symbols=int(np.sum(diffs< -1e-10)),
            tie_symbols=int(np.sum(np.abs(diffs)<=1e-10))))
        for s in syms:
            rest=[t for t in syms if t!=s]
            if not rest:continue
            leaveone.append(dict(phase=phase,candidate=cand.name,left_out=s,
                                 mean_excess=float(np.mean([cand_ret[t]-baseline[t] for t in rest]))))
    return comparisons,rankings,leaveone


def ordered_confirmations(sig:pd.DataFrame) -> dict[str,np.ndarray]:
    """Chronological RSI->MACD->Ichimoku signals, no future reads."""
    n=len(sig);macd=np.zeros(n,bool);ichi=np.zeros(n,bool)
    stage=0;anchor=-1;s2=-1
    a=sig.stage1.to_numpy(bool);b=sig.stage2.to_numpy(bool)
    c=sig.f6_s3_breakout.to_numpy(bool)
    for i in range(n):
        if stage==1 and i-anchor>v5.MAX_STAGE_GAP:
            stage=0
        if stage==2 and i-s2>v5.MAX_STAGE_GAP:
            stage=0
        if stage==0:
            if a[i]:stage=1;anchor=i
        elif stage==1:
            if i>anchor and b[i]:
                macd[i]=True;stage=2;s2=i
        elif stage==2:
            if i>s2 and c[i]:
                ichi[i]=True;stage=0
    return {'MACD_AFTER_RSI':macd,'ICHI_AFTER_RSI_MACD':ichi}


def signal_arrays(sig:pd.DataFrame) -> dict[str,np.ndarray]:
    out={'RSI_REBOUND':sig.stage1.to_numpy(bool),
         'MACD_GOLDEN':sig.stage2.to_numpy(bool),
         'ICHI_CLOUD_SUPPORT':sig.cloud.to_numpy(bool),
         'ICHI_STRICT':sig.f6_s3_breakout.to_numpy(bool),
         'ICHI_TREND':sig.f6_s3_trend.to_numpy(bool)}
    out.update(ordered_confirmations(sig))
    return out


def phase_bounds(idx,first,last):
    sel=np.flatnonzero((idx>=first)&(idx<=last))
    if len(sel)<2:return None
    return int(sel[0]),int(sel[-1])


def nonoverlapping_events(indices, horizon):
    """Fixed spacing avoids double counting many adjacent trend signals."""
    picked=[];last=-10**8
    for i in indices:
        i=int(i)
        if i-last>horizon:
            picked.append(i);last=i
    return picked


def wilson_interval(wins,n,z=1.95996398454):
    if n<=0:return (None,None)
    q=wins/n;den=1+z*z/n
    cen=(q+z*z/(2*n))/den
    rad=z*np.sqrt(q*(1-q)/n+z*z/(4*n*n))/den
    return float(cen-rad),float(cen+rad)


def forward_signal_study(prices,sig,phase,first,last,symbol):
    bounds=phase_bounds(prices.index,first,last)
    if bounds is None:return [],[]
    start,end=bounds
    op=prices.open.to_numpy(float)
    signals=signal_arrays(sig)
    rows=[];traces=[]
    for horizon in HORIZONS:
        # signal confirmed at t, buy at open[t+1], sell at open[t+1+horizon]
        end_signal=end-horizon-1
        first_signal=max(start,78)
        if end_signal<first_signal:continue
        all_dates=np.arange(first_signal,end_signal+1)
        market_rets=np.array([pair_ret(op[i+1],op[i+1+horizon]) for i in all_dates])
        market_rets=market_rets[np.isfinite(market_rets)]
        unconditional_win=float(np.mean(market_rets>0)) if len(market_rets) else None
        unconditional_avg=float(np.mean(market_rets)) if len(market_rets) else None
        for kind,events in signals.items():
            eligible=[i for i in all_dates if events[i] and np.isfinite(op[i+1]) and
                      np.isfinite(op[i+1+horizon]) and min(op[i+1],op[i+1+horizon])>0]
            selected=nonoverlapping_events(eligible,horizon)
            returns=np.array([pair_ret(op[i+1],op[i+1+horizon]) for i in selected])
            n=len(returns);wins=int(np.sum(returns>0))
            lo,hi=wilson_interval(wins,n)
            row=dict(phase=phase,symbol=symbol,signal=kind,horizon_bars=horizon,
                     signal_count=n,positive_count=wins,
                     win_rate=float(wins/n) if n else None,
                     win_ci_low=lo,win_ci_high=hi,
                     average_return=float(np.mean(returns)) if n else None,
                     median_return=float(np.median(returns)) if n else None,
                     worst_return=float(np.min(returns)) if n else None,
                     best_return=float(np.max(returns)) if n else None,
                     unconditional_win_rate=unconditional_win,
                     unconditional_avg_return=unconditional_avg,
                     win_rate_lift=float(wins/n-unconditional_win) if n and unconditional_win is not None else None,
                     average_return_lift=float(np.mean(returns)-unconditional_avg) if n and unconditional_avg is not None else None,
                     valid_baseline_days=len(market_rets))
            rows.append(row)
            for i,rr in zip(selected,returns):
                traces.append(dict(phase=phase,symbol=symbol,signal=kind,
                                   horizon_bars=horizon,signal_date=str(prices.index[i].date()),
                                   entry_date=str(prices.index[i+1].date()),
                                   exit_date=str(prices.index[i+1+horizon].date()),
                                   entry_open=float(op[i+1]),exit_open=float(op[i+1+horizon]),
                                   net_return=float(rr),profitable=int(rr>0)))
    return rows,traces


def indicator_exit_study(prices,sig,phase,first,last,symbol):
    bounds=phase_bounds(prices.index,first,last)
    if bounds is None:return [],[]
    start,end=bounds
    op=prices.open.to_numpy(float)
    entries=signal_arrays(sig)
    exits={'RSI_REBOUND':(sig.rsi_failure|sig.rsi_overbought_entry).to_numpy(bool),
           'MACD_GOLDEN':sig.macd_death.to_numpy(bool),
           'ICHI_CLOUD_SUPPORT':sig.cloud_breakdown.to_numpy(bool),
           'ICHI_STRICT':sig.cloud_breakdown.to_numpy(bool)}
    stats=[];trade_rows=[]
    for kind in INDICATOR_EXITS:
        state='FLAT'; buy_price=None;buy_i=None
        completed=[];period_trades=[];opens=0;pending=None
        # Only actions triggered at close t and executed on t+1 OPEN.
        for i in range(start,end+1):
            if pending is not None:
                side,when=pending
                if not np.isfinite(op[i]) or op[i]<=0:
                    raise ValueError('Invalid open quote')
                if side=='BUY':
                    if state!='FLAT':raise AssertionError('Double entry')
                    buy_price=float(op[i]);buy_i=i;state='LONG'
                else:
                    if state!='LONG':raise AssertionError('Exit without entry')
                    rr=pair_ret(buy_price,float(op[i]));completed.append(rr)
                    period_trades.append(dict(phase=phase,symbol=symbol,signal=kind,
                        status='CLOSED',entry=str(prices.index[buy_i].date()),
                        exit=str(prices.index[i].date()),hold_bars=i-buy_i,
                        entry_open=buy_price,exit_open=float(op[i]),net_return=rr))
                    state='FLAT';buy_price=None;buy_i=None
                pending=None
            if i==end:break
            if state=='FLAT' and i>=78 and entries[kind][i]:
                pending=('BUY',i)
            elif state=='LONG' and exits[kind][i]:
                pending=('SELL',i)
        if state=='LONG':
            opens=1
            period_trades.append(dict(phase=phase,symbol=symbol,signal=kind,
                status='OPEN_MTM',entry=str(prices.index[buy_i].date()),
                exit=str(prices.index[end].date()),hold_bars=end-buy_i,
                entry_open=buy_price,exit_open=float(prices.close.iloc[end]),
                net_return=pair_ret(buy_price,float(prices.close.iloc[end]))))
        n=len(completed);wins=sum(x>0 for x in completed)
        lo,hi=wilson_interval(wins,n)
        stats.append(dict(phase=phase,symbol=symbol,signal=kind,
            completed_trades=n,open_trades=opens,wins=wins,
            win_rate=wins/n if n else None,win_ci_low=lo,win_ci_high=hi,
            mean_closed_return=float(np.mean(completed)) if n else None,
            median_closed_return=float(np.median(completed)) if n else None,
            worst_closed_return=min(completed) if n else None,
            mean_win_return=float(np.mean([r for r in completed if r>0])) if wins else None,
            mean_loss_return=float(np.mean([r for r in completed if r<=0])) if n>wins else None))
        trade_rows+=period_trades
    return stats,trade_rows


def signal_aggregate(rows,phase='validation_2024_2025',horizon=20):
    results=[]
    for kind in SIGNALS:
        all_eligible=[r for r in rows if r['phase']==phase and r['signal']==kind and
                      r['horizon_bars']==horizon and r['signal_count']>0]
        if not all_eligible:continue
        reliable=[r for r in all_eligible if r['signal_count']>=5]
        n=sum(int(r['signal_count']) for r in all_eligible)
        wins=sum(int(r['positive_count']) for r in all_eligible)
        results.append(dict(phase=phase,signal=kind,horizon_bars=horizon,
            tickers_with_any=len(all_eligible),tickers_with_at_least_5=len(reliable),trades=n,
            pooled_win_rate=wins/n if n else None,
            equal_ticker_win_rate=float(np.mean([r['win_rate'] for r in reliable])) if reliable else None,
            equal_ticker_return=float(np.mean([r['average_return'] for r in reliable])) if reliable else None,
            equal_ticker_unconditional_win=float(np.mean([r['unconditional_win_rate'] for r in reliable])) if reliable else None,
            equal_ticker_unconditional_return=float(np.mean([r['unconditional_avg_return'] for r in reliable])) if reliable else None))
    return results



def indicator_stock_matrix(rows, phase='validation_2024_2025', horizon=20):
    """One row per ticker with side-by-side RSI/MACD/Ichimoku 20-day results.

    A missing signal becomes 0 events and empty rate; never hallucinate a win.
    Distinguish 1-9 event samples from >=10, which is still NOT a guarantee.
    """
    signals=('RSI_REBOUND','MACD_GOLDEN','ICHI_CLOUD_SUPPORT','ICHI_STRICT',
             'ICHI_TREND','MACD_AFTER_RSI','ICHI_AFTER_RSI_MACD')
    tickers=sorted({r['symbol'] for r in rows if r['phase']==phase and r['horizon_bars']==horizon})
    indexed={(r['symbol'],r['signal']):r for r in rows
             if r['phase']==phase and r['horizon_bars']==horizon}
    result=[]
    for symbol in tickers:
        row={'phase':phase,'symbol':symbol,'horizon_bars':horizon}
        for kind in signals:
            src=indexed.get((symbol,kind))
            n=int(src['signal_count']) if src else 0
            prefix=kind.lower()
            row[prefix+'_count']=n
            row[prefix+'_win_rate']=src['win_rate'] if n else None
            row[prefix+'_net_return']=src['average_return'] if n else None
            row[prefix+'_win_rate_lift']=src['win_rate_lift'] if n else None
            row[prefix+'_sample_flag']=('10+ EVENTS' if n>=10 else
                                       '1-9 SPARSE' if n else 'NO SIGNAL')
        result.append(row)
    return result


def stock_matrix_cols():
    cols=['phase','symbol','horizon_bars']
    for kind in SIGNALS:
        prefix=kind.lower()
        cols.extend((prefix+'_count',prefix+'_win_rate',prefix+'_net_return',
                     prefix+'_win_rate_lift',prefix+'_sample_flag'))
    return cols


def csv_write(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as file:
        w=csv.DictWriter(file,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

SENS_COLS=('phase candidate ranking_method excluded_top_n excluded_symbols remaining_symbols '
           'base_mean candidate_mean mean_excess median_excess candidate_better '
           'candidate_tie candidate_worse mean_mdd_difference').split()
RANK_COLS=('phase candidate symbols baseline_top5 candidate_top5 mean_excess median_excess '
           'winsor10_excess trim10_excess better_symbols worse_symbols tie_symbols').split()
LOO_COLS=('phase candidate left_out mean_excess').split()
FORWARD_COLS=('phase symbol signal horizon_bars signal_count positive_count win_rate '
           'win_ci_low win_ci_high average_return median_return worst_return best_return '
           'unconditional_win_rate unconditional_avg_return win_rate_lift average_return_lift '
           'valid_baseline_days').split()
EVENT_COLS=('phase symbol signal horizon_bars signal_date entry_date exit_date '
            'entry_open exit_open net_return profitable').split()
ROUND_COLS=('phase symbol signal completed_trades open_trades wins win_rate win_ci_low win_ci_high '
            'mean_closed_return median_closed_return worst_closed_return mean_win_return mean_loss_return').split()
TRADE_COLS=('phase symbol signal status entry exit hold_bars entry_open exit_open net_return').split()
AGG_COLS=('phase signal horizon_bars tickers_with_any tickers_with_at_least_5 trades pooled_win_rate '
          'equal_ticker_win_rate equal_ticker_return equal_ticker_unconditional_win '
          'equal_ticker_unconditional_return').split()


def report_lines(sens,ranks,aggregate,roundtrips,errors,downloaded,total):
    s=['# F8: top-winner exclusion and indicator win rates (signal effectiveness)',
       '',f'OHLCV cut-off {ASOF}, 2026 top50 survivor universe. Not independent holdout.',
       '## Definitions / limitations',
       '- Each F7 strategy uses RSI→MACD→Ichimoku sequence and staged weights 1:2:6.',
       '- Outlier exclusion applies THE SAME tickers to F5 baseline and each F7 alternative.',
       '- Exclusions are determined by baseline F5 profits OR candidate profits, separately.',
       '- Rank top 1/3/5/10 of 2024-25 account returns; exclude them from all variants before calculating paired mean difference.',
       '- Both winner-based exclusions are outcome-dependent diagnostics, NOT investable filters knowable at entry.',
       '- Standalone indicator win rate: at day t signal close, buy next open, exit after 5/10/20/40 full bars at next open. Fee 0.10% each direction.',
       '- Same-period unconditional buy-and-hold days provide a market-direction baseline. A high raw win rate alone does not prove forecasting skill.',
       '- Indicator event samples are filtered to non-overlapping spans per horizon; successive horizons/indicators still overlap. Wilson intervals assume iid, which is imperfect.',
       '- Indicator exit round trips are a DIFFERENT experiment: RSI exits at <=30 or upward 70 crossover; MACD exits at death cross; Ichimoku exits below cloud bottom. Unclosed trades excluded from closed win rates.',
       '- Conditional confirmation event sample counts may be too small to interpret. Pooled rate includes all eligible signals; equal-ticker comparison requires >=5 signals per security.',
       '- 2024-25 has already been extensively inspected. Nasdaq selection anchored to 2026, survivorship bias, cross-stock dependence, no tax/slippage/corporate action/dividend/FX realism.',
       '', '## F7 top-winner sensitivity: 2024-2025',
       '| F7 candidate | Winner ranking | Removed | Remaining | Mean return advantage (pp) | Median advantage (pp) | better/tie/worse |',
       '|---|---|---:|---:|---:|---:|---|']
    for r in sens:
        if (r['phase']=='validation_2024_2025'
                and r['excluded_top_n'] in EXCLUDE_COUNTS
                and r['candidate'] in (CONFIGS[1].name,CONFIGS[2].name)
                and r['ranking_method'] in ('baseline_f5','candidate')):
            s.append(f"| {r['candidate']} | {r['ranking_method']} | {r['excluded_top_n']} | "
                     f"{r['remaining_symbols']} | {100*r['mean_excess']:+.2f} | "
                     f"{100*r['median_excess']:+.2f} | {r['candidate_better']}/{r['candidate_tie']}/{r['candidate_worse']} |")
    s += ['','## Ranking robustness: mean/median/winsor/trim of matched excess return',
          '| Candidate | n | mean (pp) | median (pp) | winsor 10% (pp) | trimmed 10% (pp) | better/tie/worse |',
          '|---|---:|---:|---:|---:|---:|---|']
    for r in ranks:
        if r['candidate'] in (CONFIGS[1].name,CONFIGS[2].name):
            s.append(f"| {r['candidate']} | {r['symbols']} | {100*r['mean_excess']:+.2f} | {100*r['median_excess']:+.2f} | "
                     f"{100*r['winsor10_excess']:+.2f} | {100*r['trim10_excess']:+.2f} | "
                     f"{r['better_symbols']}/{r['tie_symbols']}/{r['worse_symbols']} |")
    s+=['','## Raw indicator signal hit rate, 20-bar horizon',
        '| Signal | Any-signal tickers | Tickers>=5 | Nonoverlap events | Pooled win | Equal-ticker win (n>=5) | Equal-ticker mean trade (n>=5) | Unconditional win (n>=5) |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in aggregate:
        if r['phase']=='validation_2024_2025' and r['horizon_bars']==20:
            n5=r['tickers_with_at_least_5']
            pretty=(f"{r['equal_ticker_win_rate']:.1%} | {r['equal_ticker_return']:+.2%} | "
                    f"{r['equal_ticker_unconditional_win']:.1%}") if n5 else 'n/a | n/a | n/a'
            s.append(f"| {r['signal']} | {r['tickers_with_any']} | {n5} | {r['trades']} | "
                     f"{r['pooled_win_rate']:.1%} | {pretty} |")
    s+=['','## Detailed ticker-by-ticker indicator effectiveness',
          'See indicator_stock_matrix_20d.csv for RSI/MACD/cloud side-by-side 20-day win rates, net returns, sample counts and win-rate lift.',
          'Sample size labels: NO SIGNAL, 1-9 SPARSE or 10+ EVENTS. Even 10 signals is not enough to prove a forecasting edge.',
          '', '## Indicator-defined round trips (different from fixed-horizon signal success)',
        '| Signal | Completed trades | Open MTM | Pooled win | Mean per closed trade |',
        '|---|---:|---:|---:|---:|']
    for kind in INDICATOR_EXITS:
        rr=[r for r in roundtrips if r['phase']=='validation_2024_2025' and r['signal']==kind]
        n=sum(r['completed_trades'] for r in rr);o=sum(r['open_trades'] for r in rr)
        wins=sum(r['wins'] for r in rr)
        avg=np.average([r['mean_closed_return'] for r in rr if r['completed_trades']],
                       weights=[r['completed_trades'] for r in rr if r['completed_trades']]) if n else None
        s.append(f'| {kind} | {n} | {o} | {wins/n:.1%} | {avg:+.2%} |' if n else
                 f'| {kind} | 0 | {o} | n/a | n/a |')
    s+=['','## Data failures',f'- Downloaded {downloaded}/{total} symbols',
        *[f"- {r['symbol']}: {r['error']}" for r in errors],'']
    return '\n'.join(s)+'\n'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    top,_=v3.top50_candidates()
    universe=list(base.UNIVERSE)
    present={r[0] for r in universe}
    for r in top:
        if r['symbol'] not in present:
            universe.append((r['symbol'],r['symbol'],'Nasdaq_largecap','SPY'))
            present.add(r['symbol'])
    account=[];sig_rows=[];sig_events=[];rounds=[];round_trades=[];errors=[];downloaded=[]
    for symbol,_,_,_ in universe:
        try:
            print('F8',symbol,flush=True)
            p=base.fetch_prices(symbol)
            sig=v6.indicators(p)
            for phase,first,last in PHASES:
                if phase_bounds(p.index,first,last) is None:continue
                for cfg in CONFIGS:
                    row,_,_=v7.run_config(p,sig,phase,first,last,symbol,cfg,
                                          return_details=False)
                    if row is not None:account.append(row)
                fr,events=forward_signal_study(p,sig,phase,first,last,symbol)
                sr,tr=indicator_exit_study(p,sig,phase,first,last,symbol)
                sig_rows.extend(fr);sig_events.extend(events)
                rounds.extend(sr);round_trades.extend(tr)
            downloaded.append(symbol)
        except Exception as exc:
            errors.append(dict(symbol=symbol,error=str(exc)[:450]))
            print('WARN F8',symbol,exc,flush=True)
    sens,ranks,leaveone=robust_stats(account)
    agg=[]
    for phase,_,_ in PHASES:
        for horizon in HORIZONS:
            agg.extend(signal_aggregate(sig_rows,phase,horizon))
    csv_write(OUT/'strategy_accounts.csv',account,v7.SUMMARY_COLS)
    csv_write(OUT/'outlier_sensitivity.csv',sens,SENS_COLS)
    csv_write(OUT/'outlier_rankings.csv',ranks,RANK_COLS)
    csv_write(OUT/'leave_one_out.csv',leaveone,LOO_COLS)
    csv_write(OUT/'indicator_forward_winrates.csv',sig_rows,FORWARD_COLS)
    csv_write(OUT/'indicator_stock_matrix_20d.csv',indicator_stock_matrix(sig_rows),stock_matrix_cols())
    csv_write(OUT/'indicator_signal_trades.csv',sig_events,EVENT_COLS)
    csv_write(OUT/'indicator_roundtrip_winrates.csv',rounds,ROUND_COLS)
    csv_write(OUT/'indicator_roundtrip_trades.csv',round_trades,TRADE_COLS)
    csv_write(OUT/'indicator_aggregate.csv',agg,AGG_COLS)
    csv_write(OUT/'errors.csv',errors,['symbol','error'])
    ok=len(downloaded)>=len(universe)-5 and set(base.REQUIRED).issubset(downloaded)
    meta=dict(status='success' if ok else 'incomplete',asof=str(ASOF),
      requested=len(universe),downloaded=len(downloaded),failures=errors,
      configs=[c.name for c in CONFIGS],horizons=HORIZONS,
      excluded_top_counts=EXCLUDE_COUNTS,
      signal_definitions=list(SIGNALS),indicator_exit_definitions=list(INDICATOR_EXITS),
      out_of_sample=False,universe_survivorship_bias=True,transaction_fee_each_side=FEE)
    (OUT/'run_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (OUT/'report.md').write_text(report_lines(sens,ranks,agg,rounds,errors,len(downloaded),len(universe)),encoding='utf-8')
    if not ok:raise RuntimeError(f'F8 incomplete: {len(downloaded)}/{len(universe)} downloads')
    print(f'F8 complete {len(downloaded)}/{len(universe)}; {len(sens)} sensitivity rows; '
          f'{len(sig_rows)} indicator result rows; {len(sig_events)} indicator events',flush=True)


if __name__=='__main__':
    main()
