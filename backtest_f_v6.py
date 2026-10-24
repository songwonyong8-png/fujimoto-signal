"""F6 research: book/article-inspired RSI+candle → MACD → Ichimoku confirmations.

Two stage-3 interpretations: strict cloud breakout, or confirmed upward trend
following a recent cloud breakout; optionally require the previous-120-bar
volume-profile POC. F5-A is the unchanged comparator. Every decision is based
on completed daily data; fills occur at next session OPEN.

NOT a reconstruction of a discretionary trader's actual trades. No 5-minute
study or fundamental earnings screen is claimed absent historical input data.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_15 as base
import backtest_f_v3 as v3
import backtest_f_v4 as v4
import backtest_f_v5 as v5

OUT = Path('reports/f_signal_article_v6')
ASOF = base.ASOF
FEE = v5.FEE
WEIGHTS = v5.WEIGHTS
MAX_STAGE_GAP = v5.MAX_STAGE_GAP
HORIZONS = (40, 80, 120)  # Shared evaluation windows; NOT forced liquidation.
CONFIRM_WINDOW = 20
PROFILE_NAMES = ('cloud', 'cloud_vp')
STAGE3_MODES = ('breakout', 'trend')
FUNDAMENTALS_PATH = Path('research_inputs/fundamentals_asof.csv')
FUNDAMENTAL_GATE = os.environ.get('F6_FUNDAMENTAL_GATE', 'off').lower()


def variant_id(mode: str, profile: str) -> str:
    if mode not in STAGE3_MODES or profile not in PROFILE_NAMES:
        raise ValueError('Unknown F6 strategy')
    return f'F6_{mode}_{profile}'


def indicators(p: pd.DataFrame) -> pd.DataFrame:
    """Do not read any future bars, including the lagging-span confirmation."""
    sig = v5.extended_indicators(p).copy()
    c = p.close.astype(float)
    o = p.open.astype(float)
    h = p.high.astype(float)
    l = p.low.astype(float)
    tenkan = (h.rolling(9).max()+l.rolling(9).min())/2
    kijun = (h.rolling(26).max()+l.rolling(26).min())/2
    top = sig.cloud_top.astype(float)

    # Bullish real-body daily candle is a conservative, reproducible proxy for
    # the article's candlestick confirmation, not the claimed 5-minute signal.
    sig['f6_s1'] = (sig.stage1 & (c > o)).fillna(False)
    sig['f6_s2'] = sig.stage2.copy()

    # Tenkan above a RISING Kijun, price above displayed cloud, and Chikou
    # above the candle 26 sessions earlier. At t, Chikou(t) plots close[t]
    # at t-26, so compare close[t] to high[t-26], never close[t+26].
    tk_ok = ((tenkan > kijun) & (kijun > kijun.shift(1))).fillna(False)
    chikou_ok = (c > h.shift(26)).fillna(False)
    cloud_cross = ((c > top) & (c.shift(1) <= top.shift(1))).fillna(False)
    # Confirmed trend must have a cloud upward crossing within the last 20
    # sessions; a strong price above cloud alone is not sufficient.
    recent_cross = cloud_cross.rolling(CONFIRM_WINDOW, min_periods=1).max().fillna(0).astype(bool)
    sig['f6_s3_breakout'] = (tk_ok & chikou_ok & cloud_cross).fillna(False)
    sig['f6_s3_trend'] = (tk_ok & chikou_ok & recent_cross & (c > top)).fillna(False)
    vp = sig.vp_poc.astype(float)
    vp_ok = (vp.notna() & top.gt(0) & vp.gt(0)
             & ((vp-top).abs()/top <= .04)
             & ((c-vp).abs()/vp <= .04)).fillna(False)
    sig['f6_s3_breakout_vp'] = sig.f6_s3_breakout & vp_ok
    sig['f6_s3_trend_vp'] = sig.f6_s3_trend & vp_ok

    sig['rsi_overbought_entry'] = (sig.rsi.ge(70) & sig.rsi.shift(1).lt(70)).fillna(False)
    sig['f6_cloud_failed'] = (c < sig.cloud_bottom).fillna(False)
    sig['tk_bullish'] = tk_ok
    sig['chikou_bullish'] = chikou_ok
    sig['cloud_up_cross'] = cloud_cross
    return sig


def load_fundamentals(path: Path = FUNDAMENTALS_PATH) -> dict[str,list[dict]]:
    """Verified point-in-time research input supplied by the user, if any.

    Do NOT query today's company.info for a historical backtest.
    available_date is the date the metrics became publicly available.
    """
    if FUNDAMENTAL_GATE not in ('off', 'strict'):
        raise ValueError('F6_FUNDAMENTAL_GATE must be off or strict')
    if FUNDAMENTAL_GATE == 'off':
        return {}
    if not path.is_file():
        raise RuntimeError('Strict fundamental gate requires research_inputs/fundamentals_asof.csv')
    required = {'symbol','available_date','revenue_yoy','net_income_yoy','dividend_yoy','source_url'}
    data: dict[str,list[dict]] = {}
    with path.open(encoding='utf-8-sig',newline='') as fd:
        reader = csv.DictReader(fd)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('Fundamentals CSV missing required columns')
        for row in reader:
            date = pd.Timestamp(row['available_date'])
            if pd.isna(date) or not row['source_url'] or not row['symbol']:
                raise ValueError('Missing dated/source fundamental evidence')
            growth = [float(row[k]) for k in ('revenue_yoy','net_income_yoy','dividend_yoy')]
            if not all(np.isfinite(g) for g in growth):
                raise ValueError('Fundamental growth metric is not finite')
            data.setdefault(row['symbol'],[]).append({'date':date, 'growth':growth})
    for rows in data.values():
        rows.sort(key=lambda r:r['date'])
    return data


def eligible_fundamental(symbol: str, when: pd.Timestamp, records: dict[str,list[dict]]) -> bool:
    if FUNDAMENTAL_GATE == 'off':
        return True
    # No future financial result publication; stale observations rejected.
    approved = [r for r in records.get(symbol,[]) if r['date'] <= when
                and 0 <= (when-r['date']).days <= 550]
    return bool(approved and all(x > 0 for x in approved[-1]['growth']))


def run_f6(p:pd.DataFrame, sig:pd.DataFrame, phase:str, first:pd.Timestamp,
           last:pd.Timestamp, symbol:str, mode:str, profile:str,
           fundamental_records:dict[str,list[dict]]|None=None):
    """One non-overlapping position campaign per symbol, lots 1/2/3 independent.

    Stage1 exits: RSI back to <=30, OR RSI crosses UP into >=70 (profit take).
    Stage2 exits: a fresh MACD death cross.
    Stage3 exits: price CLOSE below cloud BOTTOM.
    Already sold lots stay sold within the campaign. Further buys require the
    prerequisite lots still owned. No duration-based forced liquidation.
    """
    variant = variant_id(mode, profile)
    allowed = np.flatnonzero((p.index >= first)&(p.index <= last))
    if len(allowed) < 2:
        return None, [], []
    start,end = int(allowed[0]),int(allowed[-1])
    idx = p.index
    oo = p.open.to_numpy(float)
    cc = p.close.to_numpy(float)
    s1 = sig.f6_s1.to_numpy(bool)
    s2 = sig.f6_s2.to_numpy(bool)
    s3 = sig[f'f6_s3_{mode}' + ('_vp' if profile=='cloud_vp' else '')].to_numpy(bool)
    death = sig.macd_death.to_numpy(bool)
    rsi_fail = sig.rsi_failure.to_numpy(bool)
    takeprofit = sig.rsi_overbought_entry.to_numpy(bool)
    cloud_fail = sig.f6_cloud_failed.to_numpy(bool)

    cash = 1.
    lots = {1:0., 2:0., 3:0.}
    pending = []
    campaign = None
    number = 0
    buycounts = {1:0,2:0,3:0}
    sellcounts = {1:0,2:0,3:0}
    equity=[];exposures=[];fills=[];trades=[]
    skipped_fundamentals = 0

    def account_value(i):
        return cash + sum(lots.values())*cc[i]*(1-FEE)

    def record_campaign(i, status):
        nonlocal campaign
        if campaign is None:
            return
        val = cash if status == 'CLOSED' else account_value(i)
        trades.append(dict(phase=phase,symbol=symbol,variant=variant,
                           campaign=campaign['number'],status=status,
                           first_signal=str(idx[campaign['s1_signal']].date()),
                           entry=str(idx[campaign['entry']].date()),
                           last_mark_or_exit=str(idx[i].date()),
                           **{'return': val/campaign['initial']-1},
                           stage2_bought=campaign['bought'][2],
                           stage3_bought=campaign['bought'][3],
                           stage3_sold=campaign['sold'][3],
                           exit_reasons=';'.join(campaign['exit_reasons']),
                           calendar_bars_held=i-campaign['entry']))
        campaign = None

    for i in range(start,end+1):
        had_campaign = campaign is not None
        for action in sorted(pending,key=lambda z: (z['side']!='SELL',-z['stage'] if z['side']=='SELL' else z['stage'])):
            stage=action['stage']
            px=float(oo[i])
            if not np.isfinite(px) or px<=0:
                raise ValueError(f'Invalid next-open price: {symbol} {idx[i]}')
            if action['side']=='BUY':
                if stage==1:
                    if campaign is not None or any(q>0 for q in lots.values()):
                        raise AssertionError('Overlapping first buys')
                    number+=1
                    campaign=dict(number=number,s1_signal=action['signal_i'],entry=i,
                                  initial=cash,s2_signal=None,
                                  bought={1:False,2:False,3:False},
                                  sold={1:False,2:False,3:False},exit_reasons=[])
                if campaign is None or campaign['bought'][stage]:
                    raise AssertionError('Stage already bought or missing campaign')
                if stage>1 and lots[stage-1]<=0:
                    raise AssertionError('Previous lot not owned; cannot scale in')
                budget=campaign['initial']*WEIGHTS[stage]
                if cash+1e-10<budget:
                    raise AssertionError('Insufficient cash')
                shares=budget/(px*(1+FEE))
                lots[stage]+=shares
                cash-=budget
                campaign['bought'][stage]=True
                buycounts[stage]+=1
                if stage==2:
                    campaign['s2_signal']=action['signal_i']
            else:
                if campaign is None or lots[stage]<=0:
                    raise AssertionError('Attempt to sell non-owned lot')
                shares=lots[stage]
                cash+=shares*px*(1-FEE)
                lots[stage]=0.
                sellcounts[stage]+=1
                campaign['sold'][stage]=True
                campaign['exit_reasons'].append(action['reason'])
            fills.append(dict(phase=phase,symbol=symbol,variant=variant,
                              campaign=campaign['number'],date=str(idx[i].date()),
                              signal_date=str(idx[action['signal_i']].date()),
                              side=action['side'],stage=stage,reason=action['reason'],
                              price=px,shares=float(shares),cash_after=float(cash),
                              initial_capital_weight=WEIGHTS[stage]))
        pending=[]
        if campaign is not None and all(v==0 for v in lots.values()):
            record_campaign(i,'CLOSED')
        equity.append(account_value(i))
        position=sum(lots.values())*cc[i]
        exposures.append(position/(cash+position) if cash+position>0 else 0.)
        if i>=end:
            break
        if campaign is None:
            if not had_campaign and i>=78 and s1[i]:
                if eligible_fundamental(symbol,idx[i],fundamental_records or {}):
                    pending=[dict(side='BUY',stage=1,signal_i=i,reason='RSI_CANDLE_REBOUND')]
                else:
                    skipped_fundamentals+=1
            continue
        owns={j for j,v in lots.items() if v>0}
        sells={}
        if 3 in owns and cloud_fail[i]:
            sells[3]='CLOUD_BOTTOM_BREAK'
        if 2 in owns and death[i]:
            sells[2]='MACD_DEAD_CROSS'
        if 1 in owns:
            if rsi_fail[i]:
                sells[1]='RSI_THESIS_FAILED'
            elif takeprofit[i]:
                sells[1]='RSI_70_PROFIT_TAKE'
        if sells:
            pending=[dict(side='SELL',stage=stage,signal_i=i,reason=sells[stage])
                     for stage in sorted(sells,reverse=True)]
            continue
        if (campaign['bought'][1] and lots[1]>0 and not campaign['bought'][2]
            and i>campaign['s1_signal'] and i-campaign['s1_signal']<=MAX_STAGE_GAP and s2[i]):
            pending=[dict(side='BUY',stage=2,signal_i=i,reason='MACD_GOLDEN_CROSS')]
        elif (campaign['bought'][2] and lots[1]>0 and lots[2]>0 and not campaign['bought'][3]
              and i>campaign['s2_signal'] and i-campaign['s2_signal']<=MAX_STAGE_GAP and s3[i]):
            pending=[dict(side='BUY',stage=3,signal_i=i,reason='ICHIMOKU_'+mode.upper() + ('_VP' if profile=='cloud_vp' else ''))]
    if campaign is not None:
        record_campaign(end,'OPEN_MTM')
    eq=np.asarray(equity,dtype=float)
    peak=np.maximum.accumulate(np.r_[1.,eq])[1:]
    closed=[t for t in trades if t['status']=='CLOSED']
    summary=dict(phase=phase,symbol=symbol,variant=variant,
                 completed_trades=len(closed),open_trades=len(trades)-len(closed),
                 winning_fraction=float(np.mean([t['return']>0 for t in closed])) if closed else None,
                 worst_closed_trade=float(min(t['return'] for t in closed)) if closed else None,
                 cumulative_return=float(eq[-1]-1),
                 cagr=float(eq[-1]**(252/len(eq))-1) if eq[-1]>0 else -1.,
                 mdd=float(np.min(eq/peak-1)),
                 avg_actual_exposure=float(np.mean(exposures)),
                 stage1_buys=buycounts[1],stage2_buys=buycounts[2],stage3_buys=buycounts[3],
                 stage1_sells=sellcounts[1],stage2_sells=sellcounts[2],stage3_sells=sellcounts[3],
                 skipped_fundamentals=skipped_fundamentals)
    return summary,trades,fills


def matched_cohort_starts(sig,start,end,horizon):
    """Select anchors based on current F6 RSI+candle signals, not outcomes."""
    if horizon < MAX_STAGE_GAP+2:
        raise ValueError('Horizon too short for staged entries')
    signal=sig.f6_s1.to_numpy(bool)
    i=max(start,78)
    result=[]
    while i+horizon<=end:
        if signal[i]:
            result.append(i)
            i+=horizon+1
        else:
            i+=1
    return result


def compare_matched(p,sig,phase,first,last,symbol,records):
    """F5-A original versus F6 strict/trend at identical RSI+candle anchors."""
    allowed=np.flatnonzero((p.index>=first)&(p.index<=last))
    if len(allowed)<2:
        return []
    start,end=int(allowed[0]),int(allowed[-1]); result=[]
    for horizon in HORIZONS:
        for anchor in matched_cohort_starts(sig,start,end,horizon):
            isolated=sig.copy()
            isolated['stage1']=False
            isolated['f6_s1']=False
            isolated.iloc[anchor,isolated.columns.get_loc('stage1')]=True
            isolated.iloc[anchor,isolated.columns.get_loc('f6_s1')]=True
            for profile in PROFILE_NAMES:
                base_row,base_trades,_=v5.run_signal_lot_variant(
                    p,isolated,phase,p.index[anchor],p.index[anchor+horizon],symbol,'A',profile)
                if base_row is None or len(base_trades)!=1:
                    raise AssertionError('F5 matched cohort did not enter once')
                for mode in STAGE3_MODES:
                    row,ts,_=run_f6(p,isolated,phase,p.index[anchor],p.index[anchor+horizon],
                                    symbol,mode,profile,records)
                    if FUNDAMENTAL_GATE=='strict' and row is not None and row['stage1_buys']==0:
                        # Eligibility is explicitly screened; no matched entry.
                        continue
                    if row is None or len(ts)!=1:
                        raise AssertionError('F6 matched cohort did not enter once')
                    result.append(dict(phase=phase,symbol=symbol,profile=profile,mode=mode,
                                       horizon_bars=horizon,
                                       first_signal=str(p.index[anchor].date()),
                                       entry=str(p.index[anchor+1].date()),
                                       evaluation_date=str(p.index[anchor+horizon].date()),
                                       f5_return=float(base_row['cumulative_return']),
                                       f6_return=float(row['cumulative_return']),
                                       f6_minus_f5=float(row['cumulative_return']-base_row['cumulative_return']),
                                       f5_status=base_trades[0]['status'],f6_status=ts[0]['status'],
                                       f5_3rd_buys=int(base_row['stage3_buys']),
                                       f6_3rd_buys=int(row['stage3_buys'])))
    return result


SUMMARY_COLUMNS = ('phase symbol variant completed_trades open_trades winning_fraction worst_closed_trade '
                   'cumulative_return cagr mdd avg_actual_exposure stage1_buys stage2_buys stage3_buys '
                   'stage1_sells stage2_sells stage3_sells skipped_fundamentals').split()
TRADE_COLUMNS = ('phase symbol variant campaign status first_signal entry last_mark_or_exit return '
                 'stage2_bought stage3_bought stage3_sold exit_reasons calendar_bars_held').split()
FILL_COLUMNS = ('phase symbol variant campaign date signal_date side stage reason price shares '
                'cash_after initial_capital_weight').split()
PAIRED_COLUMNS = ('phase symbol profile mode horizon_bars first_signal entry evaluation_date '
                  'f5_return f6_return f6_minus_f5 f5_status f6_status f5_3rd_buys f6_3rd_buys').split()


def write_csv(path,rows,fields):
    with path.open('w',newline='',encoding='utf-8-sig') as fp:
        w=csv.DictWriter(fp,fieldnames=fields,extrasaction='ignore')
        w.writeheader();w.writerows(rows)


def summarise_report(summaries,pairs,errors,meta):
    lines=['# F6 — Blog-informed Ichimoku confirmation + RSI profit-taking, daily-bar research','',
           'Article: https://myrichlife.tistory.com/643 (secondary blog summary, NOT verified discretionary source-code).',
           f'OHLCV ends {ASOF}; large-cap ranking snapshot {v3.TOP50_SNAPSHOT_DATE}.',
           '## Verified implementation versus research hypotheses',
           '- Article-derived principles: stage up 1:2:6; RSI oversold, MACD cross, Ichimoku Tenkan/Kijun, cloud breakout, Chikou confirmation; RSI >=70 profit consideration.',
           '- Experimental choices: entry 1 RSI 30..48 rebound with green daily candle; entry 2 MACD cross within 20 bars; entry3 rising Kijun and Tenkan>Kijun, Chikou close[t]>high[t-26], plus cloud cross on the day (STRICT) or within past 20 bars (TREND).',
           '- VP alternative adds previous-120-session volume-at-typical-price POC (32 bins) within 4% of cloud top and current close; optional research choice.',
           '- Sell 1/9 RSI <=30 thesis break OR upward RSI cross 70 profit take, sell 2/9 MACD death, sell 6/9 close below cloud bottom. Independent lots only; no cascading forced sell.',
           '- Every signal closes at t; executed next-day OPEN, 0.1% commission each side; no time-based exit or rebuy of sold lot in same campaign.',
           '- F5-A reference uses ORIGINAL F5 entry/exit implementation without added candlestick, RSI70 or stricter Ichimoku constraints.',
           '- 40/80/120-day matched studies are evaluation cutoffs, not exit rules. Open lots marked to close less hypothetical sale fee.',
           f'- Fundamental historical growth gate: {FUNDAMENTAL_GATE}. Strict mode requires point-in-time verified CSV inputs (by PUBLICATION date).',
           '- 5-minute/day-trading validation NOT performed: only daily bars available for full multi-year backtest.',
           '- Live earnings growth screening NOT faked from modern data. No slippage, tax, dividend or FX; survivorship bias persists.',
           '', '## 2024-2025 account study (mean of per-ticker outcomes; not pooled portfolio)',
           '| strategy | tickers | closed | open | mean cumulative | median cumulative | avg MDD | avg exposure | third fills | RSI70 profit sells |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for v in ('F5_A_cloud','F5_A_cloud_vp',*(variant_id(mode,p) for mode in STAGE3_MODES for p in PROFILE_NAMES)):
        a=[x for x in summaries if x['phase']=='validation_2024_2025' and x['variant']==v]
        if not a:continue
        def mean(col):return float(np.mean([x[col] for x in a if x.get(col) is not None]))
        profits=meta['profit_sell_counts'].get(v,0)
        lines.append(f'| {v} | {len(a)} | {sum(x["completed_trades"] for x in a)} | '
                     f'{sum(x["open_trades"] for x in a)} | {mean("cumulative_return"):+.2%} | '
                     f'{np.median([x["cumulative_return"] for x in a]):+.2%} | '
                     f'{mean("mdd"):+.2%} | {mean("avg_actual_exposure"):.2%} | '
                     f'{sum(x["stage3_buys"] for x in a)} | {profits} |')
    lines+=['','## Matched first RSI+candle cohorts — 2024-2025 (40/80/120 bars)',
            '| evaluation bars | profile | F6 stage3 | matched cases | avg F5 | avg F6 | mean difference | F6 strictly better | F6 stage3 fills |',
            '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for horizon in HORIZONS:
        for profile in PROFILE_NAMES:
            for mode in STAGE3_MODES:
                subset=[r for r in pairs if r['phase']=='validation_2024_2025' and r['profile']==profile and r['mode']==mode and r['horizon_bars']==horizon]
                if subset:
                    avg=lambda key:float(np.mean([r[key] for r in subset]))
                    lines.append(f'| {horizon} | {profile} | {mode} | {len(subset)} | '
                                 f'{avg("f5_return"):+.2%} | {avg("f6_return"):+.2%} | '
                                 f'{avg("f6_minus_f5"):+.2%} | '
                                 f'{np.mean([r["f6_minus_f5"]>0 for r in subset]):.1%} | '
                                 f'{sum(x["f6_3rd_buys"] for x in subset)} |')
    lines+=['','## Price and coverage failures','']+[f'- {e["symbol"]}: {e["error"]}' for e in errors]
    return lines


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records=load_fundamentals()
    top,_=v3.top50_candidates()
    universe=list(base.UNIVERSE)
    seen={x[0] for x in universe}
    for row in top:
        sym=row['symbol']
        if sym not in seen:
            universe.append((sym,sym,'Nasdaq_largecap','SPY'));seen.add(sym)
    summary=[];trades=[];fills=[];pairs=[];errors=[];successful=[]
    profit_sell_counts={}
    for symbol,label,group,bench in universe:
        try:
            print('Fv6',symbol,flush=True)
            p=base.fetch_prices(symbol)
            sig=indicators(p)
            for phase,first,last in base.PHASES:
                for profile in PROFILE_NAMES:
                    old,t,f=v5.run_signal_lot_variant(p,sig,phase,first,last,symbol,'A',profile)
                    if old is not None:
                        old['skipped_fundamentals']=0
                        summary.append(old);trades+=t;fills+=f
                    for mode in STAGE3_MODES:
                        new,t,f=run_f6(p,sig,phase,first,last,symbol,mode,profile,records)
                        if new is not None:
                            summary.append(new);trades+=t;fills+=f
                            if phase=='validation_2024_2025':
                                key=new['variant'];profit_sell_counts[key]=profit_sell_counts.get(key,0)+sum(x['reason']=='RSI_70_PROFIT_TAKE' for x in f)
                pairs+=compare_matched(p,sig,phase,first,last,symbol,records)
            successful.append(symbol)
        except Exception as exc:
            errors.append({'symbol':symbol,'error':str(exc)[:360]})
            print('WARN',symbol,exc,flush=True)
    meta={'status':'success' if len(successful)>=len(universe)-5 and set(base.REQUIRED).issubset(successful) else 'incomplete',
          'data_asof':str(ASOF),'ranking_snapshot':v3.TOP50_SNAPSHOT_DATE,
          'requested':len(universe),'downloaded':len(successful),'failures':errors,
          'article':'https://myrichlife.tistory.com/643',
          'fundamental_mode':FUNDAMENTAL_GATE,
          'fundamental_gate_applied':FUNDAMENTAL_GATE=='strict',
          'timeframe':'daily_only_5minute_not_tested',
          'strategies':6,'paired_evaluation_bars':HORIZONS,
          'profit_sell_counts':profit_sell_counts}
    write_csv(OUT/'summary.csv',summary,SUMMARY_COLUMNS)
    write_csv(OUT/'trades.csv',trades,TRADE_COLUMNS)
    write_csv(OUT/'fills.csv',fills,FILL_COLUMNS)
    write_csv(OUT/'paired_cohorts.csv',pairs,PAIRED_COLUMNS)
    write_csv(OUT/'errors.csv',errors,['symbol','error'])
    write_csv(OUT/'selected_top50.csv',top,['symbol','market_cap'])
    (OUT/'run_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'report.md').write_text('\n'.join(summarise_report(summary,pairs,errors,meta))+'\n',encoding='utf-8')
    if meta['status']!='success':
        raise RuntimeError(f'F6 coverage incomplete {len(successful)}/{len(universe)}')
    print(f'F6 complete: {len(successful)}/{len(universe)} assets, {len(summary)} summary rows, {len(pairs)} paired cases',flush=True)

if __name__=='__main__':
    main()
