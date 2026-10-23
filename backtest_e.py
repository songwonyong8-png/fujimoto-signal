"""E-study: same A-green entries, paired 10/20/40-session exits.

Requires the ORIGINAL backtest.py and backtest_15.py from this repository.
Writes ONLY reports/paired_exits/*. Never alters app.js or existing reports.

Key design:
* Freeze market data at backtest_15.ASOF (2026-10-22).
* Every variant uses IDENTICAL precommitted entry sessions, selected by the
  40-session maximum horizon. No variant can reinvest earlier than another.
* All selected entries can fully exit within the phase. Incomplete 40-session
  windows are excluded from ALL arms (no unequal last-trade censoring).
* For portfolio equity, one position at a time, 100% invested while holding;
  money is otherwise cash with 0% yield. No overlapping trades. Each symbol
  independently uses a notional 1.0 account (NOT a combined portfolio).
* Entry at next-session OPEN after completed A signal; exit at OPEN on the
  10th, 20th, or 40th subsequent trading session. Daily equity marked at
  CLOSE while invested, then flat in cash. Both side fees 0.1%.
* No lookahead in signal generation. Selection for a 40-day common cohort uses
  availability of FUTURE dates only (not values); boundary excludes recent
  signals ex-post to make outcomes comparable. Treat as research, not live algo.
* Historical split/unadjusted OHLC via the existing source is maintained for
  comparability. Corporate actions, dividends, FX, slippage/taxes not modelled.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import backtest_15 as expansion

ASOF = expansion.ASOF
UNIVERSE = expansion.UNIVERSE
PHASES = expansion.PHASES
OUTPUT = Path('reports/paired_exits')
FEE = expansion.legacy.FEE_PER_SIDE
RULES = {'E10_hold10': 10, 'E20_hold20': 20, 'E40_hold40': 40}
MAX_HOLD = max(RULES.values())
SUMMARY_COLS = [
    'phase','symbol','name','group','variant','from','to','bars','eligible_common_entries',
    'excluded_recent_signal_days','closed_trades','win_rate','avg_trade','median_trade',
    'worst_trade','avg_mae_intraday','cumulative_return','cagr_252','max_drawdown',
    'exposure_bars_pct','exposed_sessions','avg_holding_sessions','buy_hold_return'
]
TRADE_COLS = [
    'phase','symbol','name','group','cohort_id','variant','signal_date','entry_date','exit_date',
    'entry_price','exit_price','holding_sessions','return','mae_intraday','mfe_intraday','regime'
]
PAIR_COLS = [
    'phase','symbol','name','group','cohort_id','signal_date','entry_date',
    'return_10','return_20','return_40','diff_10_minus_20','diff_40_minus_20',
    'winner','regime'
]
COMPARE_COLS = [
    'phase','variant','tickers','completed_trades','positive_tickers',
    'ticker_avg_return','ticker_median_return','ticker_avg_cagr',
    'ticker_avg_mdd','ticker_avg_exposure','trades_won_pct','trade_worst'
]


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def selected_cohorts(prices: pd.DataFrame, signals: pd.DataFrame,
                     first: pd.Timestamp, last: pd.Timestamp):
    """Select a *shared* nonoverlapping 40-session entry schedule.

    Identical across arms. Signal day <= end-41; entry day signal+1;
    exits entry+10/20/40 at their opens. Following potential signal is after
    40-day expiry date; no same-day signal re-entry on exit date.
    """
    dt = prices.index
    allowed = np.flatnonzero((dt >= first) & (dt <= last))
    if len(allowed) < 15:
        return None
    start = max(59, int(allowed[0]))
    end = int(allowed[-1])
    if end - start < MAX_HOLD + 1:
        return None
    sig = signals['A'].to_numpy(dtype=bool)
    if len(sig) != len(prices):
        raise ValueError('Signal/prices length mismatch')
    anchors = []
    i = start
    while i + 1 + MAX_HOLD <= end:
        if sig[i]:
            entry = i + 1
            anchors.append((i, entry))
            i = entry + MAX_HOLD + 1
        else:
            i += 1
    cut = end - (MAX_HOLD + 1)
    recent_count = int(np.count_nonzero(sig[max(start, cut + 1):end + 1]))
    return start, end, anchors, recent_count


def fee_return(entry: float, exit_price: float) -> float:
    return (exit_price * (1.0 - FEE)) / (entry * (1.0 + FEE)) - 1.0


def simulate_common(prices: pd.DataFrame, signals: pd.DataFrame,
                    symbol: str, name: str, group: str,
                    benchmark: pd.DataFrame | None, phase: str,
                    first: pd.Timestamp, last: pd.Timestamp):
    """Return summary rows, paired trades, equity, paired differences.

    Crucially portfolio paths are valid: entries are separated by >40 days,
    so long/short arms never overlap their own positions.
    """
    cohort = selected_cohorts(prices, signals, first, last)
    if cohort is None:
        return [], [], [], []
    start, end, anchors, excluded = cohort
    dt = prices.index
    oo = prices.open.to_numpy(dtype=float)
    cc = prices.close.to_numpy(dtype=float)
    hh = prices.high.to_numpy(dtype=float)
    ll = prices.low.to_numpy(dtype=float)
    if not np.isfinite(oo[start:end+1]).all() or not np.isfinite(cc[start:end+1]).all():
        raise ValueError(f'Nonfinite prices in {symbol}/{phase}')
    if np.min(oo[start:end+1]) <= 0 or np.min(cc[start:end+1]) <= 0:
        raise ValueError(f'Nonpositive prices in {symbol}/{phase}')
    bars = end - start + 1
    summaries, trades, curves = [], [], []
    cohort_returns: dict[int, dict[int, float]] = {k: {} for k in range(len(anchors))}
    cohort_regimes: dict[int, str] = {}
    for variant, hold in RULES.items():
        curve = np.ones(bars, dtype=float)
        capital = 1.0
        prior_end = start - 1
        position_count = 0
        per_trades = []
        for k, (signal_i, entry_i) in enumerate(anchors):
            exit_i = entry_i + hold
            if not (start <= signal_i < entry_i < exit_i <= end):
                raise AssertionError('Invalid precommitted cohort bounds')
            if entry_i <= prior_end:
                raise AssertionError('Overlapping entries in fixed cohort')
            entry_px, exit_px = float(oo[entry_i]), float(oo[exit_i])
            if entry_px <= 0 or exit_px <= 0:
                raise ValueError('Nonpositive entry or exit')
            # Trade is invested entry_i..exit_i-1 (exit at OPEN on exit_i).
            # Exclude the exit day's intraday range from adverse/favorable marks.
            lows = ll[entry_i:exit_i]
            highs = hh[entry_i:exit_i]
            pnl = fee_return(entry_px, exit_px)
            region = expansion.market_regime(benchmark, dt[signal_i]) if benchmark is not None else 'unclassified'
            cohort_regimes[k] = region
            rec = {
                'phase': phase, 'symbol': symbol, 'name': name, 'group': group,
                'cohort_id': f'{phase}:{symbol}:{k+1:03d}',
                'variant': variant,
                'signal_date': dt[signal_i].date().isoformat(),
                'entry_date': dt[entry_i].date().isoformat(),
                'exit_date': dt[exit_i].date().isoformat(),
                'entry_price': entry_px, 'exit_price': exit_px,
                'holding_sessions': hold, 'return': pnl,
                'mae_intraday': float(np.min(lows/entry_px-1)),
                'mfe_intraday': float(np.max(highs/entry_px-1)),
                'regime': region,
            }
            per_trades.append(rec)
            cohort_returns[k][hold] = pnl
            # Remaining cash period (if any) stays at realized capital.
            curve[prior_end+1-start:entry_i-start] = capital
            for j in range(entry_i, exit_i):
                curve[j-start] = capital * (1.0 + fee_return(entry_px, float(cc[j])))
            capital *= 1.0 + pnl
            curve[exit_i-start] = capital
            prior_end = exit_i
            position_count += hold
        if prior_end < end:
            curve[prior_end+1-start:] = capital
        peaks = np.maximum.accumulate(np.r_[1.0, curve])[1:]
        mdd = float(np.min(curve / peaks - 1.0))
        r = np.asarray([t['return'] for t in per_trades], dtype=float)
        summaries.append({
            'phase': phase, 'symbol': symbol, 'name': name, 'group': group,
            'variant': variant, 'from': dt[start].date().isoformat(),
            'to': dt[end].date().isoformat(), 'bars': bars,
            'eligible_common_entries': len(anchors),
            'excluded_recent_signal_days': excluded,
            'closed_trades': len(r),
            'win_rate': float(np.mean(r > 0)) if len(r) else None,
            'avg_trade': float(np.mean(r)) if len(r) else None,
            'median_trade': float(np.median(r)) if len(r) else None,
            'worst_trade': float(np.min(r)) if len(r) else None,
            'avg_mae_intraday': float(np.mean([t['mae_intraday'] for t in per_trades])) if len(r) else None,
            'cumulative_return': float(capital - 1.0),
            'cagr_252': float(capital**(252.0/bars) - 1.0),
            'max_drawdown': mdd,
            'exposure_bars_pct': float(position_count / bars),
            'exposed_sessions': position_count,
            'avg_holding_sessions': float(hold) if len(r) else None,
            'buy_hold_return': fee_return(float(oo[start]), float(cc[end])),
        })
        trades.extend(per_trades)
        curves.extend({'phase':phase,'symbol':symbol,'variant':variant,
                       'date':dt[start+j].date().isoformat(),'equity':float(v)}
                      for j,v in enumerate(curve))
    # Triple-check that the entry sets match exactly across every exit duration.
    all_dates = {v: [t['entry_date'] for t in trades if t['variant'] == v] for v in RULES}
    if len({tuple(v) for v in all_dates.values()}) != 1:
        raise AssertionError(f'Unequal E entry dates: {symbol}/{phase}')
    pairs = []
    for k, (signal_i, entry_i) in enumerate(anchors):
        x = cohort_returns[k]
        if set(x) != {10, 20, 40}:
            raise AssertionError('Missing exit on a matched cohort')
        winner = min((10,20,40), key=lambda d: (-x[d],d))
        pairs.append({
            'phase':phase,'symbol':symbol,'name':name,'group':group,
            'cohort_id': f'{phase}:{symbol}:{k+1:03d}',
            'signal_date':dt[signal_i].date().isoformat(),
            'entry_date':dt[entry_i].date().isoformat(),
            'return_10':x[10], 'return_20':x[20], 'return_40':x[40],
            'diff_10_minus_20':x[10]-x[20],
            'diff_40_minus_20':x[40]-x[20],
            'winner':f'E{winner}', 'regime':cohort_regimes[k],
        })
    return summaries, trades, curves, pairs


def aggregate(rows: list[dict], trades: list[dict], phase: str):
    result = []
    for v in RULES:
        rr = [r for r in rows if r['phase'] == phase and r['variant'] == v]
        if not rr:
            continue
        tr = [t for t in trades if t['phase'] == phase and t['variant'] == v]
        result.append({
            'phase':phase,'variant':v,'tickers':len(rr),
            'completed_trades':sum(x['closed_trades'] for x in rr),
            'positive_tickers':sum(x['cumulative_return'] > 0 for x in rr),
            'ticker_avg_return':float(np.mean([x['cumulative_return'] for x in rr])),
            'ticker_median_return':float(np.median([x['cumulative_return'] for x in rr])),
            'ticker_avg_cagr':float(np.mean([x['cagr_252'] for x in rr])),
            'ticker_avg_mdd':float(np.mean([x['max_drawdown'] for x in rr])),
            'ticker_avg_exposure':float(np.mean([x['exposure_bars_pct'] for x in rr])),
            'trades_won_pct':float(np.mean([t['return'] > 0 for t in tr])) if tr else None,
            'trade_worst':float(np.min([t['return'] for t in tr])) if tr else None,
        })
    return result


def fmt(v):
    if v is None or not math.isfinite(v):
        return '—'
    return f'{v:+.1%}'


def report_md(summary: list[dict], agg: list[dict], pairs: list[dict], errors: list[dict]):
    lines = [
        '# E안: 동일 A 진입 코호트에서 10·20·40일 보유 비교', '',
        f'- 데이터 기준일: **{ASOF.isoformat()}** (이후 데이터 사용하지 않음).',
        '- 기존 `backtest.py`에서 계산한 **A 초록불**만 매수 신호로 사용.',
        '- 각 종목·기간별 **40일 최대 보유기간을 기준으로 겹치지 않는 매수 일정을 먼저 고정**합니다.',
        '- 모든 규칙은 같은 날, 다음 거래일 **시가**에 매수합니다. 10/20/40거래일 후 **시가**에 청산.',
        '- 40일 후 청산일까지 데이터가 없는 신호는 **세 전략 모두** 공통 제외합니다.',
        '- 조기 청산 후 재진입하지 않고, 다음 공통 매수 날짜까지 현금으로 대기(이자 0%).',
        '- 각 종목을 100% 투자하는 독립적 가상 계정으로 계산합니다. 이 결과는 **15종목 통합 포트폴리오가 아닙니다**.',
        '- 수수료 매수/매도 각각 0.1%. 배당·환율·슬리피지·세금·시장충격 미포함.',
        '- MDD와 CAGR(252거래일 환산)은 위 **공통 진입·현금 대기** 계정의 일별 평가금액으로 산출합니다.',
        '- **D0/D4 결과와 숫자가 달라질 수 있음**: D안은 각 청산일에 따라 다음 진입일이 달라지지만 E안은 40일 공통 진입만 사용합니다.',
        '- 2026년은 이미 관찰한 데이터이므로 독립적인 전향적 검증은 아닙니다. 특히 DRAM은 표본이 극히 적습니다.',
        '- 2021~23 개발/2024~25 검증이라는 라벨도 전략 자체가 사후 설계되었으므로 통계적으로 순수한 OOS는 아닙니다.',
        '- 소수의 거래에서 승률·연환산 수익률이 크게 흔들릴 수 있으니 `eligible_common_entries`를 같이 확인하세요.',
        '', '## 2024~2025 공통 진입 비교 (DRAM 상장 전 제외)', '',
        '| 전략 | 종목 | 완료 거래 | 종목평균 누적수익 | 평균 CAGR | 평균 MDD | 평균 노출률 | 수익 종목 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for x in agg:
        if x['phase']=='validation_2024_2025':
            lines.append(f"| {x['variant']} | {x['tickers']} | {x['completed_trades']} | {fmt(x['ticker_avg_return'])} | {fmt(x['ticker_avg_cagr'])} | {fmt(x['ticker_avg_mdd'])} | {fmt(x['ticker_avg_exposure'])} | {x['positive_tickers']} |")
    lines += ['', '## 동일 거래의 수익 차이 (2024~2025)', '',
              '| 비교 | 거래 건수 | 평균 차이 | 중앙값 차이 | 20일보다 우수한 비율 |',
              '|---|---:|---:|---:|---:|']
    p = [x for x in pairs if x['phase']=='validation_2024_2025']
    for col in ['diff_10_minus_20','diff_40_minus_20']:
        vals = [x[col] for x in p]
        lines.append(f"| {col} | {len(vals)} | {fmt(float(np.mean(vals)) if vals else None)} | {fmt(float(np.median(vals)) if vals else None)} | {fmt(float(np.mean(np.asarray(vals)>0)) if vals else None)} |")
    lines += ['', '## 관심 종목 세부 (DRAM은 common_dram_era)', '',
              '| 종목 | 기간 | 보유 | 공통 거래 | 누적수익 | CAGR | MDD | 노출률 | 최악 거래 |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for symbol in ('DRAM','005930.KS','NVDA','000660.KS','MU'):
        phase = 'common_dram_era' if symbol=='DRAM' else 'validation_2024_2025'
        for x in summary:
            if x['symbol']==symbol and x['phase']==phase:
                lines.append(f"| {x['name']} | {phase} | {x['variant']} | {x['closed_trades']} | {fmt(x['cumulative_return'])} | {fmt(x['cagr_252'])} | {fmt(x['max_drawdown'])} | {fmt(x['exposure_bars_pct'])} | {fmt(x['worst_trade'])} |")
    lines += ['', '## 수집·분석 실패', '']
    lines += [f"- {x['symbol']}: {x['error']}" for x in errors] if errors else ['- 없음']
    lines += ['', '## 해석 주의', '',
              '1. 10일 보유 성과가 좋아도 현금 대기일이 길어지는 효과가 섞여 있습니다. CAGR·노출률·MDD를 함께 비교하세요.',
              '2. 개별 코호트 40일 기간을 확보하려다 거래 표본이 줄었습니다. 종목 단위로 승률이 극단적이어도 강한 증거가 아닙니다.',
              '3. E안은 청산 규칙만 공정하게 비교하기 위한 **공통 진입 일정 실험**입니다. D안의 각기 다른 재진입을 포함한 실제 운용 성과를 대신하지 않습니다.',
              '4. 시장 전체가 상승한 기간, 종목 상관성, 미반영 비용과 생존편향 가능성을 고려해야 합니다.', '']
    return '\n'.join(lines)


def main() -> None:
    OUTPUT.mkdir(parents=True,exist_ok=True)
    prices_map, errors, audit = {}, [], []
    for symbol,name,_,_ in UNIVERSE:
        try:
            print(f'E download {symbol}',flush=True)
            prices=expansion.fetch_prices(symbol)
            if symbol=='DRAM' and prices.index[0]<pd.Timestamp('2026-04-02'):
                raise ValueError('DRAM prices predating launch')
            prices_map[symbol]=prices
            audit.append({'symbol':symbol,'name':name,'first':str(prices.index[0].date()),
                          'last':str(prices.index[-1].date()),'bars':len(prices)})
        except Exception as exc:
            err=str(exc).replace('\n',' ')[:300]
            errors.append({'symbol':symbol,'error':err})
            print(f'WARNING download {symbol}: {err}',flush=True)
    summaries, trades, curves, pairs = [], [], [], []
    for symbol,name,group,benchmark_symbol in UNIVERSE:
        if symbol not in prices_map:
            continue
        try:
            print(f'E analyze {symbol}',flush=True)
            prices = prices_map[symbol]
            signals=expansion.legacy.indicators(prices)
            bench=prices_map.get(benchmark_symbol)
            for phase,first,last in PHASES:
                result=simulate_common(prices,signals,symbol,name,group,bench,
                                       phase,first,last)
                s,t,c,p=result
                summaries.extend(s);trades.extend(t);curves.extend(c);pairs.extend(p)
        except Exception as exc:
            err=str(exc).replace('\n',' ')[:300]
            errors.append({'symbol':symbol,'error':err})
            print(f'WARNING analysis {symbol}: {err}',flush=True)
            prices_map.pop(symbol,None)
            summaries=[x for x in summaries if x['symbol'] != symbol]
            trades=[x for x in trades if x['symbol'] != symbol]
            curves=[x for x in curves if x['symbol'] != symbol]
            pairs=[x for x in pairs if x['symbol'] != symbol]
    comparison=[x for phase,_,_ in PHASES for x in aggregate(summaries,trades,phase)]
    write_csv(OUTPUT/'summary.csv',summaries,SUMMARY_COLS)
    write_csv(OUTPUT/'trades.csv',trades,TRADE_COLS)
    write_csv(OUTPUT/'equity.csv',curves,['phase','symbol','variant','date','equity'])
    write_csv(OUTPUT/'paired_differences.csv',pairs,PAIR_COLS)
    write_csv(OUTPUT/'comparison.csv',comparison,COMPARE_COLS)
    write_csv(OUTPUT/'audit.csv',audit,['symbol','name','first','last','bars'])
    write_csv(OUTPUT/'errors.csv',errors,['symbol','error'])
    (OUTPUT/'report.md').write_text(report_md(summaries,comparison,pairs,errors),encoding='utf-8')
    valid=set(prices_map)
    required=expansion.REQUIRED
    ok=len(valid)>=12 and not (required-valid)
    cohorts_total = sum(x['eligible_common_entries'] for x in summaries if x['variant']=='E20_hold20')
    (OUTPUT/'run_metadata.json').write_text(json.dumps({
        'asof':ASOF.isoformat(), 'status':'success' if ok else 'incomplete',
        'study':'fixed A-entry paired 10/20/40 exits, common 40-session lockout',
        'requested':len(UNIVERSE),'downloaded_and_analyzed':len(valid),
        'failed':errors,'required_missing':sorted(required-valid),
        'paired_cohorts_across_phases':cohorts_total,
        'same_entry_assertions':'passed' if ok else 'partial',
        'fees_per_side':FEE,
    },ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'E complete: {len(valid)}/{len(UNIVERSE)} assets, {cohorts_total} matched event-phase records',flush=True)
    if not ok:
        raise RuntimeError(f'Insufficient symbol coverage: {len(valid)}/{len(UNIVERSE)} required missing={required-valid}')


if __name__=='__main__':
    main()
