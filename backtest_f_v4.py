"""F v4 research: RSI -> MACD -> Ichimoku(+optional VP) 1:2:6 entries,
reverse invalidation exits, and F v3 40-session exit comparators.

New study only. Does not change the live signal app or previous backtests.
Data universe, indicators and phase definitions are reused from F v3.
All trading decisions use closing data at t and execute at t+1 OPEN.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_f_v3 as v3
import backtest_15 as base

OUT = Path('reports/f_signal_reverse_v4')
ASOF = base.ASOF
FEE = .001
MAX_STAGE_GAP = 20
WEIGHTS = {1: 1/9, 2: 2/9, 3: 6/9}
REVERSE_VARIANTS = ('F4_cloud_reverse', 'F4_cloud_vp_reverse')
BASELINE_VARIANTS = ('F3_cloud_40', 'F3_cloud_vp_40')


def extended_indicators(p: pd.DataFrame) -> pd.DataFrame:
    """Reuse unchanged v3 entry rules; add reversal exits using only past/current bars."""
    sig = v3.indicators(p).copy()
    c, h, l = p.close.astype(float), p.high.astype(float), p.low.astype(float)
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    span_a = ((tenkan + kijun)/2).shift(26)
    span_b = ((h.rolling(52).max() + l.rolling(52).min())/2).shift(26)
    sig['cloud_bottom'] = pd.concat((span_a, span_b), axis=1).min(axis=1)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    sig['macd_death'] = ((macd < signal) & (macd.shift(1) >= signal.shift(1))).fillna(False)
    sig['macd_bullish'] = (macd > signal).fillna(False)
    sig['cloud_breakdown'] = (c < sig.cloud_bottom).fillna(False)
    # Loss of the initial RSI thesis; a fail-safe even without MACD dead cross.
    sig['rsi_failure'] = sig.rsi.le(30).fillna(False)
    return sig


def run_reverse_variant(p, sig, phase, first, last, symbol, variant):
    """One sequential, self-financing, single-position account per symbol/phase.

    Reverse exit hierarchy (signal close -> next open):
      - Cloud lower-edge CLOSE breakdown: sell stage 3 (6/9 original capital).
      - MACD dead cross: sell any stage 3 first, then stages 2+1 (remaining 3/9).
      - RSI back to <=30: sell all remaining lots as a fail-safe.
    If stage 2 / 3 wasn't purchased, never fabricate its sale.
    A stage 3 lot already sold cannot be repurchased in the same campaign.
    No 40-day liquidation. At the phase boundary, open positions are MTM only.
    """
    if variant not in REVERSE_VARIANTS:
        raise ValueError(f'Unknown reverse variant: {variant}')
    idx = p.index
    allowed = np.flatnonzero((idx >= first) & (idx <= last))
    if len(allowed) < 2:
        return None, [], []
    start, end = int(allowed[0]), int(allowed[-1])
    oo = p.open.to_numpy(float)
    cc = p.close.to_numpy(float)
    s1 = sig.stage1.to_numpy(bool)
    s2 = sig.stage2.to_numpy(bool)
    s3 = sig['cloud_vp' if variant == 'F4_cloud_vp_reverse' else 'cloud'].to_numpy(bool)
    death = sig.macd_death.to_numpy(bool)
    breakdown = sig.cloud_breakdown.to_numpy(bool)
    rsi_failure = sig.rsi_failure.to_numpy(bool)

    cash = 1.
    qty = {1: 0., 2: 0., 3: 0.}
    pending = []
    campaign = None
    trade_rows, fill_rows, equity, exposure = [], [], [], []
    stage_buy_count = {1: 0, 2: 0, 3: 0}
    stage_sell_count = {1: 0, 2: 0, 3: 0}
    campaign_count = 0

    def position_value(i):
        return sum(qty.values()) * cc[i]

    def account_value(i):
        # Assume liquidation-side commission for mark-to-market, like F v3.
        return cash + position_value(i) * (1-FEE)

    def record_campaign(closing_i, status):
        nonlocal campaign
        if campaign is None:
            return
        capital = cash if status == 'CLOSED' else account_value(closing_i)
        trade_rows.append({
            'phase': phase, 'symbol': symbol, 'variant': variant,
            'campaign': campaign['number'], 'status': status,
            'first_signal': str(idx[campaign['s1_signal']].date()),
            'entry': str(idx[campaign['entry']].date()),
            'last_mark_or_exit': str(idx[closing_i].date()),
            'return': capital / campaign['initial'] - 1,
            'stage2_bought': bool(campaign['bought'][2]),
            'stage3_bought': bool(campaign['bought'][3]),
            'stage3_sold': bool(campaign['sold'][3]),
            'exit_reasons': ';'.join(campaign['exit_reasons']),
            'calendar_bars_held': closing_i - campaign['entry'],
        })
        campaign = None

    for i in range(start, end+1):
        had_campaign_at_open = campaign is not None
        # ALL orders originate from the PREVIOUS day's completed close.
        if pending:
            for action in sorted(pending, key=lambda a: (0 if a['side']=='SELL' else 1,
                                                         -a['stage'] if a['side']=='SELL' else a['stage'])):
                stage = action['stage']
                price = float(oo[i])
                if not np.isfinite(price) or price <= 0:
                    raise ValueError(f'Invalid opening price {symbol} {idx[i]}')
                if action['side'] == 'BUY':
                    if stage == 1:
                        if campaign is not None:
                            raise AssertionError('Overlapping entry campaign')
                        campaign_count += 1
                        campaign = dict(number=campaign_count, initial=cash,
                                        s1_signal=action['signal_i'], entry=i,
                                        s2_signal=None, bought={1:False,2:False,3:False},
                                        sold={1:False,2:False,3:False},exit_reasons=[])
                    if campaign is None or campaign['bought'][stage]:
                        raise AssertionError('Invalid sequential stage buy')
                    if stage == 2 and not campaign['bought'][1]:
                        raise AssertionError('Stage 2 requires stage 1')
                    if stage == 3 and not campaign['bought'][2]:
                        raise AssertionError('Stage 3 requires stage 2')
                    budget = campaign['initial'] * WEIGHTS[stage]
                    if cash + 1e-10 < budget:
                        raise AssertionError('Overspending cash')
                    shares = budget / (price*(1+FEE))
                    qty[stage] += shares
                    cash -= budget
                    campaign['bought'][stage] = True
                    stage_buy_count[stage] += 1
                    if stage == 2:
                        campaign['s2_signal'] = action['signal_i']
                    fill_rows.append(dict(phase=phase,symbol=symbol,variant=variant,
                                          campaign=campaign['number'],date=str(idx[i].date()),
                                          signal_date=str(idx[action['signal_i']].date()),
                                          side='BUY',stage=stage,reason=action['reason'],
                                          price=price,shares=shares,cash_after=cash,
                                          initial_capital_weight=WEIGHTS[stage]))
                else:
                    if campaign is None or qty[stage] <= 0:
                        raise AssertionError('Cannot sell lot not owned')
                    shares = qty[stage]
                    cash += shares*price*(1-FEE)
                    qty[stage] = 0.
                    campaign['sold'][stage] = True
                    campaign['exit_reasons'].append(action['reason'])
                    stage_sell_count[stage] += 1
                    fill_rows.append(dict(phase=phase,symbol=symbol,variant=variant,
                                          campaign=campaign['number'],date=str(idx[i].date()),
                                          signal_date=str(idx[action['signal_i']].date()),
                                          side='SELL',stage=stage,reason=action['reason'],
                                          price=price,shares=shares,cash_after=cash,
                                          initial_capital_weight=WEIGHTS[stage]))
            pending = []
            if campaign is not None and all(v == 0 for v in qty.values()):
                record_campaign(i, 'CLOSED')

        val = account_value(i)
        equity.append(val)
        raw_pos = position_value(i)
        exposure.append(raw_pos/(cash+raw_pos) if cash+raw_pos>0 else 0.)
        if i >= end:
            break

        if campaign is None:
            # A new RSI signal must occur after the last campaign ended.
            if not had_campaign_at_open and i >= 78 and s1[i]:
                pending = [dict(side='BUY',stage=1,reason='RSI_REBOUND',signal_i=i)]
            continue

        # Priority: risk exit supersedes ALL pending additional buys.
        sells = []
        if rsi_failure[i]:
            sells = [(stage,'RSI_THESIS_FAILED') for stage in (3,2,1) if qty[stage] > 0]
        elif death[i]:
            # MACD death can precede cloud breakdown. Exit cloud lot FIRST, then 2+1.
            sells = [(stage,'MACD_DEAD_CROSS') for stage in (3,2,1) if qty[stage] > 0]
        elif qty[3] > 0 and breakdown[i]:
            sells = [(3,'CLOUD_BOTTOM_BREAK')]
        if sells:
            pending = [dict(side='SELL',stage=stage,reason=reason,signal_i=i)
                       for stage,reason in sells]
            continue

        # No re-buy of a stage previously purchased/sold in the SAME campaign.
        if (campaign['bought'][1] and not campaign['bought'][2]
                and i > campaign['s1_signal']
                and i - campaign['s1_signal'] <= MAX_STAGE_GAP and s2[i]):
            pending = [dict(side='BUY',stage=2,reason='MACD_GOLDEN_CROSS',signal_i=i)]
        elif (campaign['bought'][2] and not campaign['bought'][3]
              and i > campaign['s2_signal']
              and i - campaign['s2_signal'] <= MAX_STAGE_GAP and s3[i]):
            # Match F v3 entry trigger exactly; only exits change in this study.
            pending = [dict(side='BUY',stage=3,reason='CLOUD_VP_SUPPORT' if
                            variant=='F4_cloud_vp_reverse' else 'CLOUD_SUPPORT',signal_i=i)]

    if campaign is not None:
        record_campaign(end, 'OPEN_MTM')
    arr = np.asarray(equity, dtype=float)
    peaks = np.maximum.accumulate(np.r_[1.,arr])[1:]
    closed = [x for x in trade_rows if x['status']=='CLOSED']
    summary = dict(phase=phase,symbol=symbol,variant=variant,
                   completed_trades=len(closed),open_trades=len(trade_rows)-len(closed),
                   winning_fraction=float(np.mean([x['return']>0 for x in closed])) if closed else None,
                   cumulative_return=float(arr[-1]-1),
                   cagr=float(arr[-1]**(252/len(arr))-1) if arr[-1]>0 else -1.,
                   mdd=float(np.min(arr/peaks-1)),
                   avg_actual_exposure=float(np.mean(exposure)),
                   stage1_buys=stage_buy_count[1],stage2_buys=stage_buy_count[2],
                   stage3_buys=stage_buy_count[3],
                   stage1_sells=stage_sell_count[1],stage2_sells=stage_sell_count[2],
                   stage3_sells=stage_sell_count[3])
    return summary, trade_rows, fill_rows


def v3_baselines(p, sig, phase, first, last, symbol):
    """Run original unchanged v3 40-day holdings on same downloaded bars."""
    a,b,c = v3.simulate(p, sig, phase, first, last, symbol)
    renamed = {'F_cloud':'F3_cloud_40','F_cloud_vp':'F3_cloud_vp_40'}
    summaries = []
    for row in a:
        if row['variant'] not in renamed:
            continue
        summaries.append(dict(phase=phase,symbol=symbol,variant=renamed[row['variant']],
                              completed_trades=row['trades'],open_trades=0,
                              winning_fraction=row['win_rate'],
                              cumulative_return=row['cumulative_return'],cagr=row['cagr'],
                              mdd=row['mdd'],avg_actual_exposure=None,
                              avg_deployed_capital_per_campaign=row['avg_capital_used'],
                              stage1_buys=row['stage1_fills'],stage2_buys=row['stage2_fills'],
                              stage3_buys=row['stage3_fills'],
                              stage1_sells=None,stage2_sells=None,stage3_sells=None))
    return summaries


def write_csv(path, rows, cols):
    with path.open('w',encoding='utf-8-sig',newline='') as fp:
        w=csv.DictWriter(fp,fieldnames=cols,extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    top,_=v3.top50_candidates()
    universe=list(base.UNIVERSE)
    seen={x[0] for x in universe}
    for r in top:
        sym=r['symbol']
        if sym not in seen:
            universe.append((sym,sym,'Nasdaq_largecap','SPY'))
            seen.add(sym)
    summary,trades,fills,errors=[],[],[],[]
    successful=[]
    for symbol,label,group,benchmark in universe:
        try:
            print(f'Fv4 {symbol}',flush=True)
            p=base.fetch_prices(symbol)
            sig=extended_indicators(p)
            for phase,first,last in base.PHASES:
                for variant in REVERSE_VARIANTS:
                    row,t,f=run_reverse_variant(p,sig,phase,first,last,symbol,variant)
                    if row is not None:
                        summary.append(row);trades.extend(t);fills.extend(f)
                summary.extend(v3_baselines(p,sig,phase,first,last,symbol))
            successful.append(symbol)
        except Exception as exc:
            errors.append(dict(symbol=symbol,error=str(exc)[:300]))
            print(f'WARN {symbol}: {exc}',flush=True)

    summary_cols=['phase','symbol','variant','completed_trades','open_trades',
                  'winning_fraction','cumulative_return','cagr','mdd','avg_actual_exposure',
                  'avg_deployed_capital_per_campaign','stage1_buys','stage2_buys','stage3_buys',
                  'stage1_sells','stage2_sells','stage3_sells']
    trades_cols=['phase','symbol','variant','campaign','status','first_signal','entry',
                 'last_mark_or_exit','return','stage2_bought','stage3_bought','stage3_sold',
                 'exit_reasons','calendar_bars_held']
    fills_cols=['phase','symbol','variant','campaign','date','signal_date','side','stage',
                'reason','price','shares','cash_after','initial_capital_weight']
    write_csv(OUT/'summary.csv',summary,summary_cols)
    write_csv(OUT/'trades.csv',trades,trades_cols)
    write_csv(OUT/'fills.csv',fills,fills_cols)
    write_csv(OUT/'errors.csv',errors,['symbol','error'])
    write_csv(OUT/'selected_top50.csv',top,['symbol','market_cap'])
    ok=len(successful)>=len(universe)-5 and set(base.REQUIRED).issubset(successful)
    meta=dict(status='success' if ok else 'incomplete',price_data_cutoff=str(ASOF),
              selected_as_of=v3.TOP50_SNAPSHOT_DATE,universe_count=len(universe),
              fetched_count=len(successful),failures=errors,
              primary_rule='reverse exit signals, not fixed-40-day hold',
              baseline_rule='unchanged v3 fixed-40-day, DIFFERENT entry schedules',
              data_source='yfinance via backtest_15.py; OHLCV as available')
    (OUT/'run_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    lines=['# F v4: 1:2:6 sequential buys + reverse signal exits','',
           f'Data cutoff: {ASOF}; frozen current Nasdaq top50 securities snapshot: {v3.TOP50_SNAPSHOT_DATE}.',
           '## Exact trading assumptions','',
           '- BUY1: v3 RSI oversold rebound (last 5 days RSI<=30, current RSI 30..48 and rising close); 1/9.',
           '- BUY2: fresh MACD golden cross after BUY1 signal, within 20 sessions; 2/9.',
           '- BUY3: unchanged v3 Ichimoku cloud-top test/reclaim, optional volume-profile POC match, after BUY2 signal within 20 sessions; 6/9.',
           '- SELL3: close below cloud BOTTOM; next-session open sell exact stage-3 lot (not 66% of current portfolio market value).',
           '- MACD death cross: next-session open sell ALL remaining lots, stage3 first then stages2+1 (3/9 if all stages previously filled).',
           '- RSI again <=30: loss of initial entry rationale => next-session open sell all remaining lots as fail-safe.',
           '- No re-buy of an already filled stage in one campaign. No 40-session automatic liquidation in v4.',
           '- One position per symbol and phase; no interest on cash; 0.10% each side; fill at NEXT OPEN.',
           '- Open positions at period cutoff are marked to last CLOSE net of hypothetical selling fee (OPEN_MTM) and excluded from closed-trade win rate.',
           '- v3 reference rows use its ORIGINAL 40-day schedule; entry events may differ and comparisons are NOT perfectly paired.',
           '- RSI 30, cloud-bottom exit, 20-day stage windows and other parameters are proposed experimental assumptions, not proprietary confirmed rules.',
           '- No take-profit. Neither gap risk nor slippage, tax, foreign exchange, corporate actions or dividends are fully modeled.',
           '- Frozen 2026 top50 securities applied historically creates survivorship bias. 2026 is not an independent holdout.',
           '', '## 2024-2025 summary, simple per-ticker mean (including tickers with 0 signals)',
           '| Variant | Tickers | closed | open MTM | avg cumulative | avg CAGR | avg MDD | pooled closed win | 3rd buys |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for v in (*REVERSE_VARIANTS,*BASELINE_VARIANTS):
        subset=[x for x in summary if x['phase']=='validation_2024_2025' and x['variant']==v]
        completed=[x for x in trades if x['phase']=='validation_2024_2025' and x['variant']==v and x['status']=='CLOSED']
        if subset:
            avg=lambda k:np.mean([float(x[k]) for x in subset if x.get(k) is not None])
            wins=f'{np.mean([t["return"]>0 for t in completed]):.1%}' if completed else 'n/a'
            lines.append(f'| {v} | {len(subset)} | {sum(x["completed_trades"] for x in subset)} | '
                         f'{sum(x["open_trades"] for x in subset)} | {avg("cumulative_return"):+.1%} | '
                         f'{avg("cagr"):+.1%} | {avg("mdd"):+.1%} | {wins} | '
                         f'{sum(x["stage3_buys"] for x in subset)} |')
    lines.extend(['','## Download / symbol analysis failures',
                  *[f'- {x["symbol"]}: {x["error"]}' for x in errors]])
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if not ok:
        raise RuntimeError(f'Insufficient coverage: {len(successful)}/{len(universe)}; see {OUT}/errors.csv')
    print(f'F v4 complete: {len(successful)}/{len(universe)} downloaded, {len(summary)} summary rows',flush=True)


if __name__=='__main__':
    main()
