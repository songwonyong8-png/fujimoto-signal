"""Fujimoto Signal research: 15-asset, fixed-rule A/B/C validation.

Runs alongside existing backtest.py. DOES NOT change the iPhone PWA.
All rules A/B/C are imported from the original backtest.py (fixed 2026-10-23),
not reoptimized for the new stocks. No same-bar fills or future-dated input.

Output: reports/expanded/ (never overwrites reports/backtest_summary.csv).
"""
from __future__ import annotations

import csv
import json
import math
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import backtest as legacy  # MUST be the original already-present backtest.py

ASOF = date(2026, 10, 22)  # freeze study; change only for a newly versioned study
START = "2020-01-01"      # warm-up for the earliest 2021 signal; no data used after ASOF
OUTPUT = Path("reports/expanded")
OUTPUT.mkdir(parents=True, exist_ok=True)
HOLD = 20
FEE = .001  # each side, same as original
HORIZONS = (5, 20, 60)

# (ticker, Korean display label, group, benchmark ticker)
UNIVERSE = [
    ("DRAM", "DRAM ETF", "Memory", "SPY"),
    ("005930.KS", "삼성전자", "Memory", "069500.KS"),
    ("000660.KS", "SK하이닉스", "Memory", "069500.KS"),
    ("MU", "마이크론", "Memory", "SPY"),
    ("NVDA", "엔비디아", "Semiconductor", "SPY"),
    ("AMD", "AMD", "Semiconductor", "SPY"),
    ("INTC", "인텔", "Semiconductor", "SPY"),
    ("AVGO", "브로드컴", "Semiconductor", "SPY"),
    ("SOXX", "SOXX", "Semiconductor_ETF", "SPY"),
    ("SMH", "SMH", "Semiconductor_ETF", "SPY"),
    ("MSFT", "마이크로소프트", "BigTech", "SPY"),
    ("AMZN", "아마존", "BigTech", "SPY"),
    ("QQQ", "QQQ", "Market_ETF", "SPY"),
    ("SPY", "SPY", "Market_ETF", "SPY"),
    ("069500.KS", "KODEX 200", "Market_ETF", "069500.KS"),
]

# Split into calendar phases, *never fit/tune on validation outcomes*.
# NOTE: original B/C hypotheses had been informed by observation of 2026 DRAM;
# hence '2026 exploratory' is NOT an untouched prospective test.
PHASES = [
    ("development_2021_2023", pd.Timestamp("2021-01-01"), pd.Timestamp("2023-12-31")),
    ("validation_2024_2025", pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")),
    ("exploratory_2026", pd.Timestamp("2026-01-01"), pd.Timestamp(ASOF)),
    ("full_2021_2026", pd.Timestamp("2021-01-01"), pd.Timestamp(ASOF)),
    ("common_dram_era", pd.Timestamp("2026-07-01"), pd.Timestamp(ASOF)),
]
REQUIRED = {"DRAM", "005930.KS", "NVDA"}


def fetch_prices(symbol: str) -> pd.DataFrame:
    last_error = None
    for attempt in range(3):
        try:
            raw = yf.download(symbol, start=START,
                              end=(ASOF + pd.Timedelta(days=1)).isoformat(),
                              auto_adjust=False, progress=False, threads=False, actions=False)
            # Normalize with same rules/thresholds as initial report.
            frame = legacy.normalize_prices(raw)
            if frame.index[-1].date() > ASOF:
                raise ValueError("future bar detected")
            return frame
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(last_error)


def write_csv(path: Path, records: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def pct(x) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.1%}"


def market_regime(benchmark: pd.DataFrame, day: pd.Timestamp) -> str:
    # No peeking: take the benchmark's last completed close on or BEFORE signal day.
    b = benchmark.loc[benchmark.index <= day]
    if len(b) < 200 or (day - b.index[-1]).days > 5:
        return "unclassified"
    close, ma200 = float(b.close.iloc[-1]), float(b.close.iloc[-200:].mean())
    return "above_200d" if close >= ma200 else "below_200d"


def build_one(prices: pd.DataFrame, signals: pd.DataFrame, symbol: str, label: str,
              group: str, benchmark: pd.DataFrame | None, phase: str,
              window_start: pd.Timestamp, window_end: pd.Timestamp, strategy: str):
    """One non-overlapping 20-session portfolio per symbol-strategy-phase.

    Dates are cut at each phase boundary. Positions entering within that phase
    but still open at the boundary are valued at that boundary's close.
    Signals whose next open falls outside the phase are not traded.
    """
    indices = prices.index
    idx = np.flatnonzero((indices >= window_start) & (indices <= window_end))
    if len(idx) < 15:
        return None, [], []
    start_i, end_i = int(idx[0]), int(idx[-1])
    if start_i < 59:
        # Data history is preserved, but minimum signal warmup is 60 sessions.
        start_i = 59
    if end_i - start_i < 15:
        return None, [], []
    price_open = prices.open.to_numpy(dtype=float)
    price_close = prices.close.to_numpy(dtype=float)
    price_high = prices.high.to_numpy(dtype=float)
    price_low = prices.low.to_numpy(dtype=float)
    sig = signals[strategy].to_numpy(dtype=bool)
    events, trades = [], []
    for i in range(start_i, end_i + 1):
        if not sig[i] or i + 1 > end_i:
            continue
        region = market_regime(benchmark, indices[i]) if benchmark is not None else "unclassified"
        ev = {"phase": phase, "symbol": symbol, "name": label, "group": group,
              "strategy": strategy, "signal_date": indices[i].date().isoformat(),
              "regime": region, "entry_date": indices[i+1].date().isoformat()}
        for days in HORIZONS:
            due = i + 1 + days
            ev[f"forward_{days}d"] = (float(legacy.fee_return(price_open[i+1], price_open[due]))
                                       if due <= end_i else "")
        events.append(ev)

    i = start_i
    while i < end_i:
        if not sig[i]:
            i += 1
            continue
        entry = i + 1
        if entry > end_i:
            break
        intended_exit = entry + HOLD
        closed = intended_exit <= end_i
        exit_index = intended_exit if closed else end_i
        e = float(price_open[entry])
        x = float(price_open[exit_index] if closed else price_close[exit_index])
        actual_ret = float(legacy.fee_return(e, x))
        # Intraday MAE: exit-open day's low is EXCLUDED for completed trades.
        adverse_end = exit_index if closed else exit_index + 1
        lows = price_low[entry:adverse_end]
        highs = price_high[entry:adverse_end]
        row = {"phase": phase, "symbol": symbol, "name": label, "group": group,
               "strategy": strategy, "signal_date": indices[i].date().isoformat(),
               "entry_date": indices[entry].date().isoformat(),
               "exit_date": indices[exit_index].date().isoformat(),
               "entry_price": e, "exit_price": x,
               "status": "CLOSED" if closed else "OPEN_MTM",
               "return": actual_ret,
               "mae_intraday": float(np.min(lows / e - 1)) if len(lows) else None,
               "mfe_intraday": float(np.max(highs / e - 1)) if len(highs) else None,
               "regime": market_regime(benchmark, indices[i]) if benchmark is not None else "unclassified",
               "entry_index": entry, "exit_index": exit_index}
        trades.append(row)
        # Next signal checked AFTER exit session; no overlap or same-day re-entry.
        if closed:
            i = exit_index + 1
        else:
            break

    # End-of-day liquidation-value portfolio equity, incl both side fees.
    equity = np.ones(end_i - start_i + 1)
    capital = 1.0
    cursor = start_i
    for tr in trades:
        e_i = tr["entry_index"]
        x_i = tr["exit_index"]
        equity[cursor - start_i:e_i - start_i] = capital
        if tr["status"] == "CLOSED":
            for j in range(e_i, x_i):
                equity[j - start_i] = capital * (1 + legacy.fee_return(tr["entry_price"], price_close[j]))
            capital *= 1 + tr["return"]
            equity[x_i - start_i] = capital
            cursor = x_i + 1
        else:
            for j in range(e_i, x_i + 1):
                equity[j - start_i] = capital * (1 + legacy.fee_return(tr["entry_price"], price_close[j]))
            capital *= 1 + tr["return"]
            cursor = x_i + 1
    if cursor <= end_i:
        equity[cursor - start_i:] = capital
    peak = np.maximum.accumulate(np.r_[1.0, equity])[1:]
    mdd = float(np.min(equity / peak - 1))
    closed_trades = [t for t in trades if t["status"] == "CLOSED"]
    returns = np.array([t["return"] for t in closed_trades], dtype=float)
    holdret = float(legacy.fee_return(float(price_open[start_i]), float(price_close[end_i])))
    record = {"phase": phase, "symbol": symbol, "name": label, "group": group,
              "strategy": strategy, "from": indices[start_i].date().isoformat(),
              "to": indices[end_i].date().isoformat(), "bars": end_i-start_i+1,
              "signals": len(events), "closed_trades": len(closed_trades),
              "open_positions": len(trades) - len(closed_trades),
              "win_rate": float(np.mean(returns > 0)) if len(returns) else None,
              "avg_trade": float(np.mean(returns)) if len(returns) else None,
              "median_trade": float(np.median(returns)) if len(returns) else None,
              "cumulative_return": float(equity[-1] - 1),
              "max_drawdown": mdd, "buy_hold_return": holdret,
              "max_mae": min((t["mae_intraday"] for t in trades if t["mae_intraday"] is not None), default=None),
              "regime_above_closed": sum(t["status"] == "CLOSED" and t["regime"] == "above_200d" for t in trades),
              "regime_below_closed": sum(t["status"] == "CLOSED" and t["regime"] == "below_200d" for t in trades)}
    for days in HORIZONS:
        vals = np.array([ev[f"forward_{days}d"] for ev in events if ev[f"forward_{days}d"] != ""], dtype=float)
        record[f"fwd_{days}_n"] = len(vals)
        record[f"fwd_{days}_mean"] = float(np.mean(vals)) if len(vals) else None
    # Avoid emitting internal array indices in published ledger.
    for tr in trades:
        tr.pop("entry_index"); tr.pop("exit_index")
    return record, trades, events


def aggregate_groups(summary: list[dict]) -> list[dict]:
    """Unweighted ticker-level means; NOT a realistic multi-stock portfolio."""
    output = []
    combos = sorted({(r["phase"], r["group"], r["strategy"]) for r in summary})
    for phase, group, strategy in combos:
        rs = [r for r in summary if (r["phase"], r["group"], r["strategy"]) == (phase, group, strategy)]
        cs = [r["cumulative_return"] for r in rs]
        ds = [r["max_drawdown"] for r in rs]
        ntr = sum(r["closed_trades"] for r in rs)
        output.append({"phase": phase, "group": group, "strategy": strategy,
                       "tickers": len(rs), "total_closed_trades": ntr,
                       "mean_ticker_return": float(np.mean(cs)),
                       "median_ticker_return": float(np.median(cs)),
                       "mean_ticker_mdd": float(np.mean(ds)),
                       "positive_return_tickers": sum(r > 0 for r in cs),
                       "sufficient_trade_tickers": sum(r["closed_trades"] >= 20 for r in rs)})
    return output


def aggregate_regimes(trades: list[dict]) -> list[dict]:
    """Completed-trade stats by symbol/phase/strategy/known-at-signal regime.

    These are CONDITIONAL trade outcomes, not investable regime portfolios.
    Multiple stocks and signals can overlap (non-independent observations).
    """
    closed = [t for t in trades if t["status"] == "CLOSED"]
    keys = sorted({(t["phase"], t["group"], t["symbol"], t["strategy"], t["regime"])
                   for t in closed})
    out = []
    for phase, group, symbol, strategy, regime in keys:
        rr = np.array([t["return"] for t in closed
                       if (t["phase"], t["group"], t["symbol"], t["strategy"], t["regime"])
                       == (phase, group, symbol, strategy, regime)], dtype=float)
        out.append({"phase": phase, "group": group, "symbol": symbol,
                    "strategy": strategy, "regime": regime, "closed_trades": len(rr),
                    "win_rate": float(np.mean(rr > 0)),
                    "mean_trade_return": float(np.mean(rr)),
                    "median_trade_return": float(np.median(rr)),
                    "worst_trade_return": float(np.min(rr))})
    return out


def render_report(summary: list[dict], groups: list[dict], errors: list[dict], regimes: list[dict]) -> str:
    lines = ["# 후지모토 신호 A/B/C — 15종목 확장 검증", "",
             f"- 데이터 절단 기준: **{ASOF.isoformat()}** (그 이후 데이터 사용 금지)",
             "- 기존 v1 `backtest.py`의 **A/B/C 신호 규칙 변경 없음**. 기존 PWA 파일 수정 없음.",
             "- 진입: 신호 다음 거래일 시가. 청산: 20거래일 이후 시가.",
             "- 각각 매수·매도 비용 0.1% 가정, 100% 단일 종목 익스포저, 비중 미조정.",
             "- 기간 경계에서 신규 진입과 포워드 수익률은 각 기간 밖 데이터를 참조하지 않음; 미청산은 기간 말 종가 시가평가.",
             "- 개발 구간(2021–23), 검증 구간(2024–25), 탐색 구간(2026), 전체 구간, DRAM 시기(2026-07~).",
             "- **주의:** B/C 규칙은 2026년 시세를 참고해 설계됐으므로 2026년은 완전히 독립적인 홀드아웃이 아님.",
             "- **주의:** 한국·미국 거래소의 거래일은 서로 다름. 모든 거래일 계산은 각 종목의 고유 거래일 기준.",
             "- 결과는 종목별 현지 통화 수익률, 환율·배당·세금·슬리피지 제외; `auto_adjust=False`의 배당 처리 한계 있음.",
             "- `DRAM`의 짧은 상장 이력은 삼성전자·MU 등으로 대체할 수 없으며 각자 별도 해석 필요.",
             "", "## 2024–2025 검증 결과 (종목별)", "",
             "| 종목 | A 거래/누적/MDD | B 거래/누적/MDD | C 거래/누적/MDD |",
             "|---|---|---|---|" ]
    for _, name, _, _ in UNIVERSE:
        rs = [r for r in summary if r["phase"] == "validation_2024_2025" and r["name"] == name]
        if not rs:
            continue
        d = {r["strategy"]: f"{r['closed_trades']}건 / {pct(r['cumulative_return'])} / {pct(r['max_drawdown'])}" for r in rs}
        lines.append(f"| {name} | {d.get('A','—')} | {d.get('B','—')} | {d.get('C','—')} |")
    lines += ["", "## 섹터별 요약 (2024–2025)", "",
              "_각 종목의 단독매매 성과를 단순평균한 값입니다. 실제 동일가중 포트폴리오 성과가 아닙니다._", "",
              "| 섹터 | 전략 | 종목 수 | 종료 거래 | 종목별 평균 누적 | 평균 MDD |",
              "|---|---|---:|---:|---:|---:|"]
    for row in groups:
        if row["phase"] != "validation_2024_2025":
            continue
        lines.append(f"| {row['group']} | {row['strategy']} | {row['tickers']} | {row['total_closed_trades']} | {pct(row['mean_ticker_return'])} | {pct(row['mean_ticker_mdd'])} |")
    lines += ["", "## 상승장/하락장 조건별 거래 성과 (2024–2025)", "",
              "_시장 대표 ETF의 신호일 200일선 위·아래 상태로 구분한 **완료 거래**만 집계한 결과입니다. 장세별 누적수익률이 아닙니다._", "",
              "| 전략 | 시장 상태 | 완료 거래(15종목 합계) | 승률 | 거래당 평균 |",
              "|---|---|---:|---:|---:|"]
    for strategy in ("A", "B", "C"):
        for regime in ("above_200d", "below_200d", "unclassified"):
            matching = [r for r in regimes if r["phase"] == "validation_2024_2025"
                        and r["strategy"] == strategy and r["regime"] == regime]
            count = sum(r["closed_trades"] for r in matching)
            if count == 0:
                continue
            # Aggregate mean weighted by number of completed trades, not ticker counts.
            wins = sum(r["win_rate"] * r["closed_trades"] for r in matching)
            ret = sum(r["mean_trade_return"] * r["closed_trades"] for r in matching)
            lines.append(f"| {strategy} | {regime} | {count} | {wins/count:.1%} | {pct(ret/count)} |")
    lines += ["", "## 품질·한계 및 다음 실험", "",
              "- 거래 건수가 적으면 승률을 우수성의 근거로 삼지 않습니다. `closed_trades < 20`은 특히 주의.",
              "- 신호별 5/20/60일 수익률은 겹치는 구간이 있으므로 통계적으로 독립 표본이 아닙니다.",
              "- 200일선 시장상태(`above_200d` / `below_200d`)는 신호일에 알려진 데이터만 사용했습니다. `unclassified`는 기초시세 부족/휴일 차이.",
              "- 기술적 분석은 동일 업종/주식에서 서로 높은 상관관계. 15개 종목이 15개 독립 실험은 아닙니다.",
              "- 본 단계는 **전략 A/B/C 고정 규칙의 외연확장 검증**. 손절·익절/추세필터와 1:1:1/1:2:6은 결과 검토 후 별도 실험 예정.",
              "- v1 초기 보고서와는 기간 절단 규칙(특히 2024/25 말의 미청산 마크 방식)이 달라 동일 행을 1:1 대조하면 안 됩니다.",
              "- 내역: `summary.csv`, `trades.csv`, `signals.csv`, `sector_summary.csv`, `regime_stats.csv`, `data_audit.csv`, `errors.csv`.",
              "", "## 시세 다운로드 실패/경고", ""]
    if errors:
        for x in errors:
            lines.append(f"- **{x['symbol']}**: {x['error']}")
    else:
        lines.append("- 없음")
    return "\n".join(lines) + "\n"


def main():
    prices_map, sig_map, data_audit, errors = {}, {}, [], []
    for symbol, name, group, benchmark in UNIVERSE:
        print(f"Download: {symbol}", flush=True)
        try:
            prices = fetch_prices(symbol)
            # Sanity check for no phantom pre-listing DRAM data.
            if symbol == "DRAM" and prices.index[0] < pd.Timestamp("2026-04-02"):
                raise RuntimeError("Unexpected pre-launch DRAM data")
            prices_map[symbol] = prices
            data_audit.append({"symbol": symbol, "name": name, "bars": len(prices),
                               "first": str(prices.index[0].date()), "last": str(prices.index[-1].date()),
                               "benchmark": benchmark, "source": "Yahoo Finance/yfinance auto_adjust=False"})
        except Exception as exc:
            msg = str(exc).replace("\n", " ")[:300]
            errors.append({"symbol": symbol, "error": msg})
            print(f"WARNING {symbol}: {msg}", flush=True)
    all_summary, all_trades, all_events = [], [], []
    for symbol, name, group, bench_symbol in UNIVERSE:
        if symbol not in prices_map:
            continue
        print(f"Signals: {symbol}", flush=True)
        prices = prices_map[symbol]
        signals = legacy.indicators(prices)
        benchmark = prices_map.get(bench_symbol)
        for phase, first, last in PHASES:
            for strategy in ("A", "B", "C"):
                s, tr, ev = build_one(prices, signals, symbol, name, group, benchmark,
                                      phase, first, last, strategy)
                if s is not None:
                    all_summary.append(s)
                    all_trades.extend(tr)
                    all_events.extend(ev)
    sectors = aggregate_groups(all_summary)
    regimes = aggregate_regimes(all_trades)
    sum_cols = ["phase", "symbol", "name", "group", "strategy", "from", "to", "bars",
                "signals", "closed_trades", "open_positions", "win_rate", "avg_trade", "median_trade",
                "cumulative_return", "max_drawdown", "buy_hold_return", "max_mae",
                "regime_above_closed", "regime_below_closed", "fwd_5_n", "fwd_5_mean",
                "fwd_20_n", "fwd_20_mean", "fwd_60_n", "fwd_60_mean"]
    trade_cols = ["phase", "symbol", "name", "group", "strategy", "signal_date", "entry_date",
                  "exit_date", "entry_price", "exit_price", "status", "return", "mae_intraday",
                  "mfe_intraday", "regime"]
    event_cols = ["phase", "symbol", "name", "group", "strategy", "signal_date", "regime",
                  "entry_date", "forward_5d", "forward_20d", "forward_60d"]
    sector_cols = ["phase", "group", "strategy", "tickers", "total_closed_trades",
                   "mean_ticker_return", "median_ticker_return", "mean_ticker_mdd",
                   "positive_return_tickers", "sufficient_trade_tickers"]
    write_csv(OUTPUT/"summary.csv", all_summary, sum_cols)
    write_csv(OUTPUT/"trades.csv", all_trades, trade_cols)
    write_csv(OUTPUT/"signals.csv", all_events, event_cols)
    write_csv(OUTPUT/"sector_summary.csv", sectors, sector_cols)
    write_csv(OUTPUT/"regime_stats.csv", regimes,
              ["phase", "group", "symbol", "strategy", "regime", "closed_trades",
               "win_rate", "mean_trade_return", "median_trade_return", "worst_trade_return"])
    write_csv(OUTPUT/"data_audit.csv", data_audit,
              ["symbol", "name", "bars", "first", "last", "benchmark", "source"])
    write_csv(OUTPUT/"errors.csv", errors, ["symbol", "error"])
    (OUTPUT/"report.md").write_text(render_report(all_summary, sectors, errors, regimes), encoding="utf-8")
    (OUTPUT/"run_metadata.json").write_text(json.dumps({
        "asof": ASOF.isoformat(), "strategy_version": "original-backtest.py-fixed-2026-10-23",
        "requested": len(UNIVERSE), "downloaded": len(prices_map),
        "failed_symbols": [e["symbol"] for e in errors],
        "success": len(prices_map) >= 12 and not (REQUIRED - set(prices_map)),
        "notes": "No strategy tuning; exploratory 2026 is not untouched holdout"},
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Finished: {len(prices_map)}/{len(UNIVERSE)} assets; {len(all_summary)} phase-strategy rows")
    missing_required = REQUIRED - set(prices_map)
    if missing_required or len(prices_map) < 12:
        raise RuntimeError(f"Insufficient price coverage: required missing {missing_required}; assets {len(prices_map)}/15. See reports/expanded/errors.csv")


if __name__ == "__main__":
    main()
