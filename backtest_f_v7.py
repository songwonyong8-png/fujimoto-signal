"""F v7 pre-registered factorial ablation of the RSI/candle, Ichimoku and RSI70 rules.

Keep the original F3/F5/F6 1:2:6 staged buy sizes and F5-A independent lot exits.
Compare 2 (RSI bullish candle yes/no) x 3 (stage3 base/strict/trend)
x 2 (RSI70 take-profit yes/no) x 2 (volume profile yes/no) = 24 variants.

OUT-OF-SAMPLE WARNING: 2024-2025 has already been inspected when creating
F3-F6. Treat this as *retrospective diagnostic*, not fresh confirmation.
No access to real historical Nasdaq100 constituent universes or publication-
dated fundamentals. 2026-10-22 frozen OHLCV cut-off; daily bars only.

All signals from the completed day's close execute at NEXT OPEN, fee .1% on
both sides, no forced sell at a study boundary (OPEN_MTM marks to market).
For paired cohorts, each model is offered the identical ORIGINAL F5 RSI anchor.
A candle-required model can decline the anchor and keep cash; no new entry is
permitted inside the common 40/80/120-bar evaluation window.
"""
from __future__ import annotations

import csv
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_15 as base
import backtest_f_v3 as v3
import backtest_f_v5 as v5
import backtest_f_v6 as v6

OUT = Path('reports/f_signal_ablation_v7')
ASOF = base.ASOF
HORIZONS = (40, 80, 120)
PROFILES = ('cloud', 'cloud_vp')
ICHIMOKU = ('base', 'strict', 'trend')
BOOTSTRAPS = 2000
BOOT_SEED = 20261024


@dataclass(frozen=True)
class Config:
    candle: bool
    ichimoku: str
    profit70: bool
    profile: str

    def __post_init__(self):
        if self.ichimoku not in ICHIMOKU or self.profile not in PROFILES:
            raise ValueError('Bad Ichimoku mode or profile')

    @property
    def name(self):
        return f'F7_C{int(self.candle)}_I{self.ichimoku}_T{int(self.profit70)}_{self.profile}'


def all_configs():
    # Stable order: separately compare VP/no VP; no optimization, no pruning.
    return tuple(Config(c, i, t, p) for p in PROFILES
                 for c, i, t in itertools.product((False, True), ICHIMOKU, (False, True)))


def baseline(profile):
    return Config(False, 'base', False, profile)


def f6_equivalent(profile, ichimoku):
    return Config(True, ichimoku, True, profile)


def chosen_stage3(sig, config):
    if config.ichimoku == 'base':
        col = 'cloud' if config.profile == 'cloud' else 'cloud_vp'
    else:
        col = 'f6_s3_' + ('breakout' if config.ichimoku == 'strict' else 'trend')
        if config.profile == 'cloud_vp':
            col += '_vp'
    return sig[col].astype(bool)


def run_config(p, sig, phase, first, last, symbol, config, *, only_anchor=None,
               return_details=True):
    """Adapt inputs ONLY, not F6's price/fills/cash bookkeeping.

    The variant always executes in v6.run_f6's isolated-lot engine. Its signal
    overrides reproduce F5-A, F6 breakout and F6 trend at pre-specified corners.
    ``only_anchor`` is a GLOBAL price-array index from the baseline RSI signal.
    Even when a candle filter refuses that anchor, the evaluation still returns
    a zero-return cash-only row for proper intention-to-test comparison.
    """
    if v6.FUNDAMENTAL_GATE != 'off':
        raise RuntimeError('F7 requires F6_FUNDAMENTAL_GATE=off for a fair ablation')
    if config not in all_configs():
        raise ValueError('Unknown configuration')
    work = sig.copy(deep=True)
    stage1 = sig['f6_s1' if config.candle else 'stage1'].astype(bool)
    if only_anchor is not None:
        if only_anchor < 0 or only_anchor >= len(sig):
            raise ValueError('Outside available bars')
        single = np.zeros(len(sig), dtype=bool)
        single[only_anchor] = bool(stage1.iloc[only_anchor])
        stage1 = pd.Series(single, index=sig.index)
    work['f6_s1'] = stage1
    s3 = chosen_stage3(sig, config)
    # Mode breakout is a common execution route; the actual third-stage
    # indicator is replaced for each Ichimoku condition, no future peeking.
    work['f6_s3_breakout'] = s3
    work['f6_s3_breakout_vp'] = s3
    if not config.profit70:
        work['rsi_overbought_entry'] = False
    row, trades, fills = v6.run_f6(p, work, phase, first, last, symbol,
                                   mode='breakout', profile=config.profile)
    if row is None:
        return None, [], []
    row['variant'] = config.name
    for collection in (trades, fills):
        for rec in collection:
            rec['variant'] = config.name
    return row, trades if return_details else [], fills if return_details else []


def select_anchors(sig, start, end, horizon):
    """Choose cohorts based on BASE RSI only, never the strategy's returns."""
    if horizon < 22:
        raise ValueError('Evaluation horizon must be >=22 bars')
    orig = sig.stage1.to_numpy(bool)
    chosen = []
    i = max(start, 78)
    while i + horizon <= end:
        if orig[i]:
            chosen.append(i)
            i += horizon + 1
        else:
            i += 1
    return chosen


def matched_results(p, sig, symbol, first, last, phase='validation_2024_2025',
                    horizons=HORIZONS, configs=None):
    """Same symbol/entry/evaluation date for ALL 24 alternatives.

    Nonoverlap applies separately for each horizon. 40/80/120 observations
    must NOT be treated as statistically independent of each other.
    """
    configs = tuple(configs if configs is not None else all_configs())
    allowed = np.flatnonzero((p.index >= first) & (p.index <= last))
    if len(allowed) < 2:
        return []
    start, end = int(allowed[0]), int(allowed[-1])
    rows = []
    for horizon in horizons:
        for anchor in select_anchors(sig, start, end, horizon):
            evaluations = {}
            for c in configs:
                row, _, _ = run_config(p, sig, phase, p.index[anchor],
                                       p.index[anchor+horizon], symbol, c,
                                       only_anchor=anchor, return_details=False)
                if row is None:
                    raise AssertionError('Complete horizon unexpectedly has no account')
                evaluations[c.name] = row
            for c in configs:
                ref = evaluations[baseline(c.profile).name]
                own = evaluations[c.name]
                rows.append(dict(phase=phase, symbol=symbol, profile=c.profile,
                                 variant=c.name, candle=int(c.candle),
                                 ichimoku=c.ichimoku, profit70=int(c.profit70),
                                 horizon_bars=horizon,
                                 first_signal=str(p.index[anchor].date()),
                                 entry=str(p.index[anchor+1].date()),
                                 evaluation_date=str(p.index[anchor+horizon].date()),
                                 initial_entry=int(own['stage1_buys'] > 0),
                                 stage3_buys=own['stage3_buys'],
                                 account_return=own['cumulative_return'],
                                 baseline_return=ref['cumulative_return'],
                                 excess_return=own['cumulative_return']-ref['cumulative_return'],
                                 account_mdd=own['mdd'], baseline_mdd=ref['mdd'],
                                 avg_exposure=own['avg_actual_exposure'],
                                 baseline_exposure=ref['avg_actual_exposure']))
    return rows


def bootstrap_symbol_ci(symbol_values, *, seed=BOOT_SEED, n=BOOTSTRAPS):
    """95% percentile interval for equal-symbol-mean difference, not trade iid.

    All within-symbol effects are averaged before resampling symbol clusters.
    Market-wide/common shocks are NOT accounted for; exploratory, not a proof.
    """
    values = np.asarray(symbol_values, dtype=float)
    if not len(values) or not np.isfinite(values).all():
        return (None, None)
    rng = np.random.default_rng(seed)
    k = len(values)
    boots = np.empty(n)
    for i in range(n):
        boots[i] = float(np.mean(values[rng.integers(k, size=k)]))
    return tuple(float(v) for v in np.quantile(boots, (.025, .975)))


def per_symbol_ablation(summaries, phase='validation_2024_2025'):
    """Marginal effect of ONE rule averaged over the other pre-set rule levels.

    Additive differences in WHOLE-ACCOUNT per-symbol return are descriptive,
    not causal inference on live trading, and do not control market exposure.
    """
    indexed = {(r['symbol'], r['variant']): r for r in summaries if r['phase'] == phase}
    symbols = sorted({s for s, _ in indexed})
    effects = []
    for dimension in ('candle', 'RSI70', 'ichi_strict', 'ichi_trend'):
        vals = []
        for symbol in symbols:
            diffs = []
            for c in all_configs():
                if dimension == 'candle' and not c.candle:
                    left, right = c, Config(True,c.ichimoku,c.profit70,c.profile)
                elif dimension == 'RSI70' and not c.profit70:
                    left, right = c, Config(c.candle,c.ichimoku,True,c.profile)
                elif dimension in ('ichi_strict','ichi_trend') and c.ichimoku == 'base':
                    right_mode = dimension.split('_')[1]
                    left, right = c, Config(c.candle,right_mode,c.profit70,c.profile)
                else:
                    continue
                if (symbol,left.name) not in indexed or (symbol,right.name) not in indexed:
                    continue
                a,b = indexed[(symbol,left.name)],indexed[(symbol,right.name)]
                diffs.append((float(b['cumulative_return'])-float(a['cumulative_return']),
                              float(b['mdd'])-float(a['mdd']),
                              float(b['avg_actual_exposure'])-float(a['avg_actual_exposure'])))
            if diffs:
                x=np.mean(np.asarray(diffs),axis=0)
                vals.append((symbol,*map(float,x)))
        if vals:
            d=np.asarray([x[1:] for x in vals])
            lower,upper=bootstrap_symbol_ci(d[:,0],seed=BOOT_SEED+len(effects))
            effects.append(dict(rule=dimension, symbols=len(vals),
                                mean_return_effect=float(np.mean(d[:,0])),
                                median_return_effect=float(np.median(d[:,0])),
                                bootstrap_ci_low=lower,bootstrap_ci_high=upper,
                                mean_mdd_effect=float(np.mean(d[:,1])),
                                mean_exposure_effect=float(np.mean(d[:,2])),
                                positive_symbols=int(np.sum(d[:,0]>0))))
    return effects


def paired_statistics(pairs, phase='validation_2024_2025'):
    groups=defaultdict(list)
    for row in pairs:
        if row['phase']==phase:
            groups[(row['profile'],int(row['horizon_bars']),row['variant'])].append(row)
    out=[]
    for (profile,horizon,variant), rr in sorted(groups.items()):
        by_sym=defaultdict(list)
        diff=[]
        for r in rr:
            dd=float(r['excess_return'])
            diff.append(dd)
            by_sym[r['symbol']].append(dd)
        symbol_avgs=np.asarray([np.mean(x) for x in by_sym.values()],dtype=float)
        lo,hi=bootstrap_symbol_ci(symbol_avgs,seed=BOOT_SEED+horizon+sum(ord(x) for x in variant))
        out.append(dict(profile=profile,horizon_bars=horizon,variant=variant,
                        pairs=len(rr),symbols=len(by_sym),
                        mean_pair_difference=float(np.mean(diff)),
                        median_pair_difference=float(np.median(diff)),
                        equal_symbol_mean_difference=float(np.mean(symbol_avgs)),
                        ci_low=lo,ci_high=hi,
                        beat_baseline=int(np.sum(np.asarray(diff)>1e-12)),
                        equal_baseline=int(np.sum(np.abs(diff)<=1e-12)),
                        worse_than_baseline=int(np.sum(np.asarray(diff)<-1e-12)),
                        candle_rejected=int(sum(1 for r in rr if not int(r['initial_entry']))),
                        stage3_buys=int(sum(int(r['stage3_buys']) for r in rr))))
    return out


def csv_write(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as fp:
        w=csv.DictWriter(fp,fieldnames=fields,extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


SUMMARY_COLS=('phase symbol variant completed_trades open_trades winning_fraction '
    'worst_closed_trade cumulative_return cagr mdd avg_actual_exposure '
    'stage1_buys stage2_buys stage3_buys stage1_sells stage2_sells stage3_sells '
    'skipped_fundamentals').split()
PAIRED_COLS=('phase symbol profile variant candle ichimoku profit70 horizon_bars '
    'first_signal entry evaluation_date initial_entry stage3_buys account_return '
    'baseline_return excess_return account_mdd baseline_mdd avg_exposure baseline_exposure').split()
EFFECT_COLS=('rule symbols mean_return_effect median_return_effect bootstrap_ci_low '
    'bootstrap_ci_high mean_mdd_effect mean_exposure_effect positive_symbols').split()
STAT_COLS=('profile horizon_bars variant pairs symbols mean_pair_difference '
    'median_pair_difference equal_symbol_mean_difference ci_low ci_high beat_baseline '
    'equal_baseline worse_than_baseline candle_rejected stage3_buys').split()
TRADE_COLS=v6.TRADE_COLUMNS
FILL_COLS=v6.FILL_COLUMNS


def write_report(summaries, effects, paired_stats, errors, universe_len, downloaded):
    lines=[
        '# F7: factor-by-factor signal ablation — confirmatory checks, not optimization',
        '',
        f'OHLCV data through {ASOF}. Current Nasdaq market-cap rank frozen at {v3.TOP50_SNAPSHOT_DATE}, NOT point-in-time membership.',
        '2024–25 has been repeatedly evaluated in prior F3–F6 experiments, so this is NOT an untouched holdout.',
        'Fundamental point-in-time and 5-minute signals are NOT tested. No tuning based on 2026 prices.',
        'Parameters are pre-specified: 1:2:6 staged entries, RSI 14, MACD 12/26/9, max 20 bar stage gap, VP 120 bars/32 bins, fees 0.1% each side.',
        '',
        '## Factorial design: 24 strategies, no cherry-picking',
        '- Candle filter off/on: base RSI rebound versus same plus close > open on RSI signal bar.',
        '- Ichimoku stage 3: base cloud rebound (F5), strict Tenkan/Kijun + Chikou + same-day cloud breakout, trend confirmation within prior 20 bars (F6).',
        '- RSI70 take profit off/on: when on, RSI crosses upward through 70 and sells LOT1 only; regular RSI<=30 sells LOT1, MACD death sells LOT2, cloud bottom failure sells LOT3.',
        '- Volume profile off/on: profile = cloud/cloud_vp, with VP conditions identical to F5/F6.',
        '- ALL signals close[t] -> open[t+1]. Cash earns zero, missing trades count as 0 return, open positions marked at phase end (NOT forced sold).',
        '- Each symbol gets a separate self-financing account. Means across symbols are NOT pooled/pooled-balance portfolio returns.',
        '- Matched RSI cohorts selected from BASE RSI events without looking at candle or returns; candle-filtered models may make no trade at that anchor. Same 40/80/120 bar evaluation date per comparison.',
        '- The 40/80/120 cohorts overlap ACROSS horizons. Do not treat them as independent samples.',
        '- 95% bootstrap intervals resample symbols (not individual trades), but cross-symbol market correlation means intervals may still be too narrow.',
        '- Statistical significance is NOT established by exploratory intervals across 24 alternatives; multiple-comparison and previous-data-snooping risks remain.',
        '- No corporate-action, slippage, FX, dividend and tax realism; 0.1% flat commission only.',
        '',
        '## 2024–2025 whole-account comparison (same capital initialised independently for each symbol)',
        '| variant | tickers | mean cumulative | median cumulative | avg MDD | avg exposure | 3rd buys | open positions |',
        '|---|---:|---:|---:|---:|---:|---:|---:|'
    ]
    for c in all_configs():
        rr=[r for r in summaries if r['phase']=='validation_2024_2025' and r['variant']==c.name]
        if not rr:continue
        avg=lambda k:float(np.mean([float(x[k]) for x in rr]))
        med=float(np.median([float(x['cumulative_return']) for x in rr]))
        s=lambda k:sum(int(x[k]) for x in rr)
        lines.append(f'| {c.name} | {len(rr)} | {avg("cumulative_return"):+.2%} | '
                     f'{med:+.2%} | {avg("mdd"):+.2%} | {avg("avg_actual_exposure"):.2%} | '
                     f'{s("stage3_buys")} | {s("open_trades")} |')
    lines += ['', '## Main effects (average across other factors, 2024–2025)',
              'Positive MDD effect means less negative drawdown; positive exposure effect means more time invested.',
              '| experimental switch | symbols | mean return difference (pp) | cluster-bootstrap 95% interval (pp) | mean MDD difference (pp) | mean exposure difference (pp) | positive symbols |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for r in effects:
        lines.append(f'| {r["rule"]} | {r["symbols"]} | {100*r["mean_return_effect"]:+.2f} | '
                     f'[{100*r["bootstrap_ci_low"]:+.2f}, {100*r["bootstrap_ci_high"]:+.2f}] | '
                     f'{100*r["mean_mdd_effect"]:+.2f} | {100*r["mean_exposure_effect"]:+.2f} | '
                     f'{r["positive_symbols"]} |')
    lines += ['', '## Matched-cohort control (representative published variants)',
              'F7_C0_Ibase_T0 is an exact F5-A control; F7_C1_Istrict_T1 and F7_C1_Itrend_T1 are F6 controls.',
              '| profile | horizon | variant | pairs | baseline beat/tie/lose | equal-symbol mean difference (pp) | 95% interval (pp) | skipped anchor |',
              '|---|---:|---|---:|---:|---:|---:|---:|']
    show={baseline('cloud').name,f6_equivalent('cloud','strict').name,
          f6_equivalent('cloud','trend').name,
          Config(False,'base',True,'cloud').name,Config(True,'base',False,'cloud').name}
    for r in paired_stats:
        if r['variant'] not in show or r['profile']!='cloud':continue
        lines.append(f'| {r["profile"]} | {r["horizon_bars"]} | {r["variant"]} | '
                     f'{r["pairs"]} | {r["beat_baseline"]}/{r["equal_baseline"]}/{r["worse_than_baseline"]} | '
                     f'{100*r["equal_symbol_mean_difference"]:+.2f} | '
                     f'[{100*r["ci_low"]:+.2f}, {100*r["ci_high"]:+.2f}] | '
                     f'{r["candle_rejected"]} |')
    lines += ['', '## Failures and coverage',
              f'- Data downloaded: {downloaded}/{universe_len} securities',
              *[f'- {r["symbol"]}: {r["error"]}' for r in errors], '']
    return '\n'.join(lines)+'\n'


def main():
    if v6.FUNDAMENTAL_GATE != 'off':
        raise RuntimeError('Set F6_FUNDAMENTAL_GATE=off; F7 isolates ONLY technical factors')
    OUT.mkdir(parents=True,exist_ok=True)
    selected,_=v3.top50_candidates()
    universe=list(base.UNIVERSE)
    seen={x[0] for x in universe}
    for r in selected:
        if r['symbol'] not in seen:
            s=r['symbol'];universe.append((s,s,'Nasdaq_largecap','SPY'));seen.add(s)
    summaries,trades,fills,pairs,errors,downloaded=[],[],[],[],[],[]
    audit_errors=[]
    for symbol,_,_,_ in universe:
        try:
            print('Fv7',symbol,flush=True)
            p=base.fetch_prices(symbol)
            sig=v6.indicators(p)
            for phase,first,last in (list(base.PHASES)+[
                ('year_2024',pd.Timestamp('2024-01-01'),pd.Timestamp('2024-12-31')),
                ('year_2025',pd.Timestamp('2025-01-01'),pd.Timestamp('2025-12-31'))]):
                # Newer securities (e.g. DRAM) may not have any sessions in
                # historical validation/development phases. Skip such phases
                # BEFORE running reference-parity audits: the old baselines
                # correctly return None, not a comparable performance row.
                available=np.flatnonzero((p.index>=first)&(p.index<=last))
                if len(available)<2:
                    continue
                for cfg in all_configs():
                    row,tt,ff=run_config(p,sig,phase,first,last,symbol,cfg)
                    if row is not None:
                        summaries.append(row);trades.extend(tt);fills.extend(ff)
                # Outright fail on engine drift from previously published models.
                if phase=='validation_2024_2025':
                    for profile in PROFILES:
                        actual=next(x for x in summaries if x['phase']==phase and x['symbol']==symbol
                                    and x['variant']==baseline(profile).name)
                        old,_,_=v5.run_signal_lot_variant(p,sig,phase,first,last,symbol,'A',profile)
                        if not np.isclose(actual['cumulative_return'],old['cumulative_return'],atol=1e-10):
                            audit_errors.append(f'{symbol} F5 comparator differs: {profile}')
                        for mode in ('strict','trend'):
                            exp=f6_equivalent(profile,mode)
                            actual=next(x for x in summaries if x['phase']==phase and x['symbol']==symbol
                                        and x['variant']==exp.name)
                            old6,_,_=v6.run_f6(p,sig,phase,first,last,symbol,
                                               'breakout' if mode=='strict' else 'trend', profile)
                            if not np.isclose(actual['cumulative_return'],old6['cumulative_return'],atol=1e-10):
                                audit_errors.append(f'{symbol} F6 comparator differs: {profile}/{mode}')
            phase,first,last=next(x for x in base.PHASES if x[0]=='validation_2024_2025')
            pairs.extend(matched_results(p,sig,symbol,first,last))
            downloaded.append(symbol)
        except Exception as exc:
            errors.append(dict(symbol=symbol,error=str(exc)[:350]))
            print('WARN Fv7',symbol,exc,flush=True)

    effects=per_symbol_ablation(summaries)
    stats=paired_statistics(pairs)
    csv_write(OUT/'summary.csv',summaries,SUMMARY_COLS)
    csv_write(OUT/'trades.csv',trades,TRADE_COLS)
    csv_write(OUT/'fills.csv',fills,FILL_COLS)
    csv_write(OUT/'matched_cohorts.csv',pairs,PAIRED_COLS)
    csv_write(OUT/'ablation_effects.csv',effects,EFFECT_COLS)
    csv_write(OUT/'paired_statistics.csv',stats,STAT_COLS)
    csv_write(OUT/'errors.csv',errors,['symbol','error'])
    csv_write(OUT/'selected_top50.csv',selected,['symbol','market_cap'])
    ok=(len(downloaded)>=len(universe)-5 and set(base.REQUIRED).issubset(downloaded)
        and not audit_errors)
    meta={'status':'success' if ok else 'incomplete',
          'data_asof':str(ASOF),'universe_requested':len(universe),'downloaded':len(downloaded),
          'failures':errors,'audit_differences':audit_errors,
          'configs':len(all_configs()),'paired_rows':len(pairs),
          'historical_membership_point_in_time':False,
          'sample_validation_untouched':False,
          'standard_error_bootstrap_clusters':'symbols; market-wide correlations remain',
          'fundamental_filter':'off','timeframe':'daily',
          'fees':'0.10% on each buy and each sale; zero slippage assumed',
          'paired_horizons':HORIZONS,'bootstrap_iterations':BOOTSTRAPS,
          'bootstrap_seed':BOOT_SEED}
    (OUT/'run_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (OUT/'report.md').write_text(write_report(summaries,effects,stats,errors,len(universe),len(downloaded)),encoding='utf-8')
    if audit_errors:
        raise AssertionError('F5/F6 baseline parity error(s): '+str(audit_errors[:8]))
    if not ok:
        raise RuntimeError(f'F7 insufficient coverage: {len(downloaded)}/{len(universe)}; see errors.csv')
    print(f'Fv7 completed: {len(downloaded)}/{len(universe)}; '
          f'{len(summaries)} account rows; {len(pairs)} matched rows; {len(effects)} ablation effects',flush=True)

if __name__=='__main__':
    main()
