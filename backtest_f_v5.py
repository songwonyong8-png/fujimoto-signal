"""F v5 independent invalidation exits: same v3 1:2:6 entries, 3 exit designs.

Run with ``python backtest_f_v5.py``. Requires existing backtest.py,
backtest_15.py, backtest_f_v3.py and backtest_f_v4.py in the repository.
No existing live app or prior backtest is modified.

V5-A: Close below Ichimoku cloud BOTTOM sells only stage 3; MACD dead-cross
      sells only stage 2; RSI <= 30 sells only stage 1.
V5-B: Hierarchical: cloud bottom -> stage 3; MACD death -> stages 2+3;
      RSI <= 30 -> stages 1+2+3.
V5-C: Identical to A except stage 3 exits below cloud TOP (early exit).
F4 reference: ORIGINAL v4 MACD/RSI emergency liquidation, unchanged.

Decisions at today's CLOSE always fill next trading day's OPEN; 0.1% fee per
side. Last day open trades are marked to closing price less a *hypothetical*
selling fee; no fictitious completed sale. No fixed-duration exits in F v5.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_15 as base
import backtest_f_v3 as v3
import backtest_f_v4 as v4

OUT = Path('reports/f_signal_independent_v5')
ASOF = base.ASOF
FEE = v4.FEE
WEIGHTS = v4.WEIGHTS
MAX_STAGE_GAP = v4.MAX_STAGE_GAP
PAIR_HORIZONS = (40, 80, 120)  # Observation windows, NEVER forced exit dates.
PROFILES = ('cloud', 'cloud_vp')
EXIT_MODELS = ('A', 'B', 'C')


def strategy_id(model: str, profile: str) -> str:
    if model not in EXIT_MODELS or profile not in PROFILES:
        raise ValueError(f'Unknown strategy: {model}, {profile}')
    return f'F5_{model}_{profile}'


def f4_id(profile: str) -> str:
    if profile not in PROFILES:
        raise ValueError(f'Unknown profile {profile}')
    return 'F4_cloud_reverse' if profile == 'cloud' else 'F4_cloud_vp_reverse'


def sell_stages(model: str, owns: set[int], cloud_break: bool,
                macd_death: bool, rsi_failure: bool) -> dict[int, str]:
    """Signal-invalidation hierarchy. Return ONLY owned stages to liquidate.

    Check all 3 signals independently at the same CLOSE. More basic invalidation
    takes precedence when a lot has multiple applicable reasons. No RSI/MACD
    event liquidates unrelated lots in independent modes A/C.
    """
    if model not in EXIT_MODELS:
        raise ValueError(model)
    if not owns.issubset({1, 2, 3}):
        raise ValueError('Invalid stage holdings')
    result: dict[int, str] = {}
    if cloud_break and 3 in owns:
        result[3] = 'CLOUD_TOP_BREAK' if model == 'C' else 'CLOUD_BOTTOM_BREAK'
    if macd_death:
        for stage in (2, 3) if model == 'B' else (2,):
            if stage in owns:
                result[stage] = 'MACD_DEAD_CROSS'
    if rsi_failure:
        for stage in (1, 2, 3) if model == 'B' else (1,):
            if stage in owns:
                result[stage] = 'RSI_THESIS_FAILED'
    return result


def extended_indicators(p: pd.DataFrame) -> pd.DataFrame:
    """Use identical F3 entry indicators and F4 closing exit signals."""
    sig = v4.extended_indicators(p)
    # A *close* below the cloud top is an early warning for the C variant.
    # NaN cloud periods must NEVER count as a valid breakdown.
    sig['cloud_top_breakdown'] = (p.close < sig.cloud_top).fillna(False)
    return sig


def run_signal_lot_variant(p: pd.DataFrame, sig: pd.DataFrame, phase: str,
                           first: pd.Timestamp, last: pd.Timestamp, symbol: str,
                           model: str, profile: str):
    """Realistic no-overlap sequential account. One campaign per symbol at once.

    Each lot is individually owned. A sale cancels that lot, not the entire
    campaign in A/C. Later buys require earlier lots STILL owned, so no adding
    onto a campaign whose lower-level rationale was already invalidated.
    Sold stages cannot be rebought in the same campaign. After all lots exit,
    the next NEW RSI trigger may create a new campaign.
    """
    variant = strategy_id(model, profile)
    idx = p.index
    days = np.flatnonzero((idx >= first) & (idx <= last))
    if len(days) < 2:
        return None, [], []
    start, end = int(days[0]), int(days[-1])
    oo = p.open.to_numpy(float)
    cc = p.close.to_numpy(float)
    s1 = sig.stage1.to_numpy(bool)
    s2 = sig.stage2.to_numpy(bool)
    s3 = sig['cloud' if profile == 'cloud' else 'cloud_vp'].to_numpy(bool)
    death = sig.macd_death.to_numpy(bool)
    rsi_failed = sig.rsi_failure.to_numpy(bool)
    breakdown = sig['cloud_top_breakdown' if model == 'C' else 'cloud_breakdown'].to_numpy(bool)

    cash = 1.0
    qty = {1: 0., 2: 0., 3: 0.}
    campaign = None
    campaign_number = 0
    pending = []
    fills, trades, equity, exposures = [], [], [], []
    buys = {1: 0, 2: 0, 3: 0}
    sells = {1: 0, 2: 0, 3: 0}

    def marked_value(i: int) -> float:
        return cash + sum(qty.values()) * cc[i] * (1-FEE)

    def close_campaign(i: int, status: str) -> None:
        nonlocal campaign
        if campaign is None:
            return
        value = cash if status == 'CLOSED' else marked_value(i)
        trades.append({
            'phase': phase, 'symbol': symbol, 'variant': variant,
            'campaign': campaign['number'], 'status': status,
            'first_signal': str(idx[campaign['s1_signal']].date()),
            'entry': str(idx[campaign['entry']].date()),
            'last_mark_or_exit': str(idx[i].date()),
            'return': value / campaign['initial']-1,
            'stage2_bought': campaign['bought'][2],
            'stage3_bought': campaign['bought'][3],
            'stage3_sold': campaign['sold'][3],
            'exit_reasons': ';'.join(campaign['exit_reasons']),
            'calendar_bars_held': i-campaign['entry'],
        })
        campaign = None

    for i in range(start, end+1):
        had_campaign_at_open = campaign is not None
        # Fill all orders placed from the PREVIOUS finished daily bar.
        for action in sorted(pending, key=lambda a: (0 if a['side'] == 'SELL' else 1,
                                                   -a['stage'] if a['side'] == 'SELL' else a['stage'])):
            stage = action['stage']
            price = oo[i]
            if not np.isfinite(price) or price <= 0:
                raise ValueError(f'Invalid open price for {symbol} on {idx[i]}')
            if action['side'] == 'BUY':
                if stage == 1:
                    if campaign is not None or any(qty.values()):
                        raise AssertionError('Overlapping campaigns forbidden')
                    campaign_number += 1
                    campaign = dict(number=campaign_number, initial=cash,
                                    s1_signal=action['signal_i'], entry=i,
                                    s2_signal=None, bought={1: False, 2: False, 3: False},
                                    sold={1: False, 2: False, 3: False}, exit_reasons=[])
                if campaign is None or campaign['bought'][stage]:
                    raise AssertionError('Duplicate or missing stage purchase')
                if stage > 1 and qty[stage-1] <= 0:
                    raise AssertionError('Cannot add stage after prerequisite lot sold')
                budget = campaign['initial'] * WEIGHTS[stage]
                if cash + 1e-10 < budget:
                    raise AssertionError('Cash constraint violated')
                shares = budget / (price * (1+FEE))
                qty[stage] += shares
                cash -= budget
                campaign['bought'][stage] = True
                buys[stage] += 1
                if stage == 2:
                    campaign['s2_signal'] = action['signal_i']
            else:
                if campaign is None or qty[stage] <= 0:
                    raise AssertionError('Sell requires owned lot')
                shares = qty[stage]
                cash += shares * price * (1-FEE)
                qty[stage] = 0.
                campaign['sold'][stage] = True
                campaign['exit_reasons'].append(action['reason'])
                sells[stage] += 1
            fills.append({
                'phase': phase, 'symbol': symbol, 'variant': variant,
                'campaign': campaign['number'], 'date': str(idx[i].date()),
                'signal_date': str(idx[action['signal_i']].date()),
                'side': action['side'], 'stage': stage, 'reason': action['reason'],
                'price': float(price), 'shares': float(shares), 'cash_after': float(cash),
                'initial_capital_weight': WEIGHTS[stage],
            })
        pending = []
        if campaign is not None and all(q == 0 for q in qty.values()):
            close_campaign(i, 'CLOSED')

        value = marked_value(i)
        equity.append(value)
        gross_position = sum(qty.values()) * cc[i]
        exposures.append(gross_position/(cash + gross_position) if cash + gross_position > 0 else 0.)
        if i == end:
            break

        if campaign is None:
            # Prevent exiting at OPEN and immediately entering from CLOSE of same day.
            if not had_campaign_at_open and i >= 78 and s1[i]:
                pending = [{'side': 'BUY', 'stage': 1, 'reason': 'RSI_REBOUND', 'signal_i': i}]
            continue

        owned = {stage for stage, held in qty.items() if held > 0}
        to_sell = sell_stages(model, owned, bool(breakdown[i]),
                             bool(death[i]), bool(rsi_failed[i]))
        if to_sell:
            pending = [{'side': 'SELL', 'stage': stage, 'reason': reason, 'signal_i': i}
                       for stage, reason in to_sell.items()]
            continue

        # Exactly unchanged V3 entry signals, windows, next-open execution.
        # But never add capital when the previous entry lot was already sold.
        if (campaign['bought'][1] and qty[1] > 0 and not campaign['bought'][2]
                and i > campaign['s1_signal']
                and i-campaign['s1_signal'] <= MAX_STAGE_GAP and s2[i]):
            pending = [{'side': 'BUY', 'stage': 2,
                        'reason': 'MACD_GOLDEN_CROSS', 'signal_i': i}]
        elif (campaign['bought'][2] and qty[1] > 0 and qty[2] > 0 and not campaign['bought'][3]
              and i > campaign['s2_signal']
              and i-campaign['s2_signal'] <= MAX_STAGE_GAP and s3[i]):
            pending = [{'side': 'BUY', 'stage': 3,
                        'reason': 'CLOUD_SUPPORT' if profile == 'cloud' else 'CLOUD_VP_SUPPORT',
                        'signal_i': i}]

    if campaign is not None:
        close_campaign(end, 'OPEN_MTM')
    eq = np.asarray(equity, dtype=float)
    peaks = np.maximum.accumulate(np.r_[1., eq])[1:]
    closed = [t for t in trades if t['status'] == 'CLOSED']
    summary = dict(
        phase=phase, symbol=symbol, variant=variant,
        completed_trades=len(closed), open_trades=len(trades)-len(closed),
        winning_fraction=float(np.mean([t['return'] > 0 for t in closed])) if closed else None,
        worst_closed_trade=float(min(t['return'] for t in closed)) if closed else None,
        cumulative_return=float(eq[-1]-1),
        cagr=float(eq[-1]**(252/len(eq))-1) if eq[-1] > 0 else -1.,
        mdd=float(np.min(eq/peaks-1)),
        avg_actual_exposure=float(np.mean(exposures)),
        stage1_buys=buys[1], stage2_buys=buys[2], stage3_buys=buys[3],
        stage1_sells=sells[1], stage2_sells=sells[2], stage3_sells=sells[3],
    )
    return summary, trades, fills


def cohort_starts(sig: pd.DataFrame, start: int, end: int,
                  horizon: int) -> list[int]:
    """Greedy non-overlapping RSI anchors with a COMPLETE common horizon.

    This selection depends only on stage1 at each bar and the fixed horizon.
    It does not depend on strategy returns, exits, or future price direction.
    """
    s = sig.stage1.to_numpy(bool)
    selected = []
    i = max(start, 78)
    while i + horizon <= end:
        if s[i]:
            selected.append(i)
            i += horizon + 1
        else:
            i += 1
    return selected


def paired_comparison(p: pd.DataFrame, sig: pd.DataFrame, phase: str,
                      first: pd.Timestamp, last: pd.Timestamp, symbol: str,
                      horizons=PAIR_HORIZONS) -> list[dict]:
    """Fixed, non-overlapping RSI cohorts, same anchor & mark date for all models.

    Unlike whole-account testing, ALL 4 models run on the SAME first RSI signal,
    evaluate through the SAME 40/80/120-bar horizon, do NOT open any new campaign
    after a sell, and mark any open position to market at the common horizon.
    This is a matched experiment, NOT a forced holding-period strategy.
    """
    idx = p.index
    allowed = np.flatnonzero((idx >= first) & (idx <= last))
    if len(allowed) < 2:
        return []
    start, end = int(allowed[0]), int(allowed[-1])
    out = []
    for horizon in horizons:
        if horizon < 22:
            raise ValueError('Paired horizon must cover all three possible stage entries')
        for anchor in cohort_starts(sig, start, end, horizon):
            # Only the chosen RSI signal is allowed to start a trade.
            isolated = sig.copy(deep=True)
            isolated['stage1'] = False
            isolated.iloc[anchor, isolated.columns.get_loc('stage1')] = True
            finish = anchor + horizon
            for profile in PROFILES:
                scores = {}
                statuses = {}
                v4_variant = f4_id(profile)
                v4_row, v4_trades, _ = v4.run_reverse_variant(
                    p, isolated, phase, idx[anchor], idx[finish], symbol, v4_variant)
                if v4_row is None or len(v4_trades) != 1:
                    raise AssertionError(f'F4 paired cohort not uniquely entered {symbol} {anchor}')
                scores['F4'] = v4_row['cumulative_return']
                statuses['F4'] = v4_trades[0]['status']
                for model in EXIT_MODELS:
                    row, ts, _ = run_signal_lot_variant(
                        p, isolated, phase, idx[anchor], idx[finish], symbol, model, profile)
                    if row is None or len(ts) != 1:
                        raise AssertionError(f'V5 paired cohort not uniquely entered {symbol} {anchor} {model}')
                    scores[model] = row['cumulative_return']
                    statuses[model] = ts[0]['status']
                out.append({
                    'phase': phase, 'symbol': symbol, 'profile': profile,
                    'horizon_bars': horizon,
                    'first_signal': str(idx[anchor].date()),
                    'entry': str(idx[anchor+1].date()),
                    'evaluation_date': str(idx[finish].date()),
                    'f4_return': scores['F4'],
                    'v5a_return': scores['A'],
                    'v5b_return': scores['B'],
                    'v5c_return': scores['C'],
                    'v5a_minus_f4': scores['A'] - scores['F4'],
                    'v5b_minus_f4': scores['B'] - scores['F4'],
                    'v5c_minus_f4': scores['C'] - scores['F4'],
                    'f4_status': statuses['F4'],
                    'v5a_status': statuses['A'],
                    'v5b_status': statuses['B'],
                    'v5c_status': statuses['C'],
                })
    return out


SUMMARY_FIELDS = ('phase symbol variant completed_trades open_trades winning_fraction '
                  'worst_closed_trade cumulative_return cagr mdd avg_actual_exposure stage1_buys stage2_buys '
                  'stage3_buys stage1_sells stage2_sells stage3_sells').split()
TRADE_FIELDS = ('phase symbol variant campaign status first_signal entry last_mark_or_exit '
                'return stage2_bought stage3_bought stage3_sold exit_reasons '
                'calendar_bars_held').split()
FILL_FIELDS = ('phase symbol variant campaign date signal_date side stage reason price '
               'shares cash_after initial_capital_weight').split()
PAIR_FIELDS = ('phase symbol profile horizon_bars first_signal entry evaluation_date '
               'f4_return v5a_return v5b_return v5c_return v5a_minus_f4 '
               'v5b_minus_f4 v5c_minus_f4 f4_status v5a_status v5b_status v5c_status').split()


def save_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def report_lines(summaries: list[dict], pairs: list[dict], errors: list[dict]) -> list[str]:
    lines = [
        '# F v5: Independent signal-based exits versus F4 and hierarchical exits',
        '',
        f'OHLCV cutoff: {ASOF}. Large-cap universe selected using {v3.TOP50_SNAPSHOT_DATE} snapshot.',
        'Historical membership is NOT point-in-time; survivorship bias remains.',
        '',
        '## Exact rules',
        '',
        '- BUY1 1/9: original v3 RSI oversold rebound; BUY2 2/9: later MACD golden-cross <=20 sessions; BUY3 6/9: later cloud / cloud+VP support <=20 sessions.',
        '- F4 baseline: ORIGINAL v4 exits, MACD death or RSI<=30 liquidates every owned lot; cloud bottom breakdown sells lot3 only.',
        '- V5-A: sell LOT3 below cloud BOTTOM; LOT2 at MACD death-cross; LOT1 at RSI<=30. Other owned lots stay open.',
        '- V5-B: below cloud bottom sell lot3; MACD death sell lot2 AND lot3; RSI<=30 sell all lots.',
        '- V5-C: like V5-A, but sell lot3 when close below cloud TOP instead of bottom.',
        '- If different exit signals occur on one bar, all applicable lots are sold at the NEXT open, stage3 first.',
        '- No re-buy within a campaign; no entry into a later stage after any prerequisite lot has been sold.',
        '- Every decision at today CLOSE, every fill tomorrow OPEN. Fee=0.1% each side, no slippage, FX, dividend/tax modelling.',
        '- No fixed-day exit in v5; positions at phase end marked to close less a hypothetical 0.1% sale fee, excluded from closed-trade win-rate.',
        '- Profits include idle cash (0% cash yield). Summary means average equal-weight per-symbol RESULTS, not a pooled investable portfolio.',
        '',
        '## 2024-2025 whole-account strategies (different entry dates possible)',
        '| strategy | tickers | closed | open MTM | average cumulative return | avg CAGR | avg MDD | worst closed trade | win on closed trades | avg daily exposure |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for profile in PROFILES:
        names = (f4_id(profile), *(strategy_id(m, profile) for m in EXIT_MODELS))
        for name in names:
            s = [x for x in summaries if x['phase'] == 'validation_2024_2025' and x['variant'] == name]
            if not s:
                continue
            avg = lambda field: float(np.mean([x[field] for x in s if x[field] is not None]))
            wins_num = sum(x['completed_trades'] * (x['winning_fraction'] or 0) for x in s)
            wins_den = sum(x['completed_trades'] for x in s)
            win = f'{wins_num/wins_den:.1%}' if wins_den else 'n/a'
            worst = min((x['worst_closed_trade'] for x in s if x.get('worst_closed_trade') is not None), default=None)
            worst_label = f'{worst:+.1%}' if worst is not None else 'n/a'
            lines.append(f"| {name} | {len(s)} | {wins_den} | "
                         f"{sum(x['open_trades'] for x in s)} | "
                         f"{avg('cumulative_return'):+.1%} | {avg('cagr'):+.1%} | "
                         f"{avg('mdd'):+.1%} | {worst_label} | {win} | {avg('avg_actual_exposure'):.1%} |")
    lines.extend([
        '',
        '## Matched RSI-entry cohorts — common 40/80/120-bar EVALUATION only',
        '',
        'Greedy non-overlapping eligible RSI signals: chosen without reference to any exit return.',
        'All 4 variants start from same RSI signal on same symbol, enter at same next open,',
        'have no other entry campaign during the window, and are marked on the same final date.',
        'A fixed EVALUATION horizon does **not** force a sell; open lots are marked to market.',
        'A paired cohort is one security and a fixed horizon; do NOT treat horizons as independent.',
        '| window | entry profile | pairs | avg F4 return | avg V5-A | avg V5-B | avg V5-C | avg A-F4 difference | win A vs F4 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|',
    ])
    for horizon in PAIR_HORIZONS:
        for profile in PROFILES:
            p = [r for r in pairs if r['phase'] == 'validation_2024_2025'
                 and r['horizon_bars'] == horizon and r['profile'] == profile]
            if not p:
                lines.append(f'| {horizon} | {profile} | 0 | n/a | n/a | n/a | n/a | n/a | n/a |')
                continue
            a = lambda key: float(np.mean([r[key] for r in p]))
            win = float(np.mean([r['v5a_return'] > r['f4_return'] for r in p]))
            lines.append(f'| {horizon} | {profile} | {len(p)} | {a("f4_return"):+.1%} | '
                         f'{a("v5a_return"):+.1%} | {a("v5b_return"):+.1%} | '
                         f'{a("v5c_return"):+.1%} | {a("v5a_minus_f4"):+.1%} | {win:.1%} |')
    lines.extend(['', '## Price/data failures', '',
                  *(f'- {x["symbol"]}: {x["error"]}' for x in errors), ''])
    return lines


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    top, _ = v3.top50_candidates()
    universe = list(base.UNIVERSE)
    seen = {r[0] for r in universe}
    for row in top:
        symbol = row['symbol']
        if symbol not in seen:
            universe.append((symbol, symbol, 'Nasdaq_largecap', 'SPY'))
            seen.add(symbol)

    summaries, trades, fills, pairs, errors, downloaded = [], [], [], [], [], []
    for symbol, label, group, benchmark in universe:
        try:
            print('Fv5', symbol, flush=True)
            prices = base.fetch_prices(symbol)
            sig = extended_indicators(prices)
            for phase, first, last in base.PHASES:
                for profile in PROFILES:
                    ref, t, f = v4.run_reverse_variant(prices, sig, phase, first, last,
                                                       symbol, f4_id(profile))
                    if ref is not None:
                        closed_ref = [tr['return'] for tr in t if tr['status'] == 'CLOSED']
                        ref['worst_closed_trade'] = min(closed_ref) if closed_ref else None
                        summaries.append(ref)
                        trades.extend(t)
                        fills.extend(f)
                    for model in EXIT_MODELS:
                        result, t, f = run_signal_lot_variant(prices, sig, phase, first, last,
                                                              symbol, model, profile)
                        if result is not None:
                            summaries.append(result)
                            trades.extend(t)
                            fills.extend(f)
                pairs.extend(paired_comparison(prices, sig, phase, first, last, symbol))
            downloaded.append(symbol)
        except Exception as exc:
            errors.append({'symbol': symbol, 'error': str(exc)[:350]})
            print('WARN', symbol, exc, flush=True)

    save_csv(OUT/'summary.csv', summaries, SUMMARY_FIELDS)
    save_csv(OUT/'trades.csv', trades, TRADE_FIELDS)
    save_csv(OUT/'fills.csv', fills, FILL_FIELDS)
    save_csv(OUT/'paired_cohorts.csv', pairs, PAIR_FIELDS)
    save_csv(OUT/'errors.csv', errors, ['symbol', 'error'])
    save_csv(OUT/'selected_top50.csv', top, ['symbol', 'market_cap'])
    status = 'success' if len(downloaded) >= len(universe)-5 and set(base.REQUIRED).issubset(downloaded) else 'incomplete'
    metadata = dict(status=status, asof=str(ASOF), universe_count=len(universe),
                    downloaded=len(downloaded), failed=errors, pair_horizons=PAIR_HORIZONS,
                    strategy_count=8, selection_snapshot=v3.TOP50_SNAPSHOT_DATE,
                    entry_rules='unchanged F v3', baseline='unchanged F4 reversed exits',
                    costs='0.1 percent per side; no slippage')
    (OUT/'run_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (OUT/'report.md').write_text('\n'.join(report_lines(summaries, pairs, errors))+'\n', encoding='utf-8')
    if status != 'success':
        raise RuntimeError(f'Price coverage failed: {len(downloaded)}/{len(universe)}; see errors.csv')
    print(f'Fv5 complete: {len(downloaded)}/{len(universe)} assets; {len(summaries)} summary rows; {len(pairs)} matched cohorts', flush=True)


if __name__ == '__main__':
    main()
