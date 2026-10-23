"""D0-D4: A-green entry, alternative exit rules (fixed as of 2026-10-23).

Requires the existing backtest.py and backtest_15.py in the repo root.
Produces only reports/exit_rules/*; never changes the iPhone PWA or A/B/C results.

Implementation assumptions:
- A signal is observed at completed day t close; fill t+1 OPEN.
- Stops are live from entry open using information known at signal day.
- If a future day's open gaps beyond an existing stop, fill at the OPEN.
- Otherwise an intraday stop fills at stop price, with no optimistic same-day
  stop tightening. Trailing stop ratchets only AFTER the day's close for t+1.
- At the expiry open, time exits precede intraday stop checks.
- 0.1% fee on each side. No taxes, dividends, slippage or partial fills.
- Each variant is independently non-overlapping; early exits can change
  subsequent signals/entry dates. Results are portfolio paths, NOT paired trades.
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
OUTPUT = Path("reports/exit_rules")
FEE = expansion.legacy.FEE_PER_SIDE
VERSIONS = {
    "D0_hold20": ("time", 20, 0.0),
    "D1_stop5": ("fixed", 20, .05),
    "D2_atr2": ("atr", 20, 2.0),
    "D3_trail2p5atr": ("trail", 20, 2.5),
    "D4_hold10": ("time", 10, 0.0),
    "D4_hold40": ("time", 40, 0.0),
}


def wilder_atr(prices: pd.DataFrame, n: int = 14) -> np.ndarray:
    """Historical Wilder ATR, known after each session close; no lookahead."""
    high = prices.high.to_numpy(dtype=float)
    low = prices.low.to_numpy(dtype=float)
    close = prices.close.to_numpy(dtype=float)
    tr = np.full(len(prices), np.nan)
    for i in range(1, len(prices)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
    out = np.full(len(prices), np.nan)
    if len(prices) <= n:
        return out
    out[n] = float(np.mean(tr[1:n + 1]))
    for i in range(n + 1, len(prices)):
        out[i] = (out[i-1] * (n - 1) + tr[i]) / n
    return out


def fee_return(entry: float, exit_price: float) -> float:
    return (exit_price * (1 - FEE)) / (entry * (1 + FEE)) - 1


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def simulate(prices: pd.DataFrame, signals: pd.DataFrame, symbol: str,
             name: str, group: str, benchmark: pd.DataFrame | None,
             phase: str, first: pd.Timestamp, last: pd.Timestamp, variant: str,
             atr_values: np.ndarray | None = None):
    """Trade one full-notional position at a time, with daily EOD equity marks.

    Returns summary, ledger, equity path. Returns (None,[],[]) if not enough data.
    Every variant scans A signals independently after its last position closed.
    """
    rule, hold, mult = VERSIONS[variant]
    dt = prices.index
    allowed = np.flatnonzero((dt >= first) & (dt <= last))
    if len(allowed) < 15:
        return None, [], []
    start = max(int(allowed[0]), 59)
    end = int(allowed[-1])
    if end - start < 15:
        return None, [], []
    oo = prices.open.to_numpy(dtype=float)
    hh = prices.high.to_numpy(dtype=float)
    ll = prices.low.to_numpy(dtype=float)
    cc = prices.close.to_numpy(dtype=float)
    aa = atr_values if atr_values is not None else wilder_atr(prices)
    sig = signals["A"].to_numpy(dtype=bool)
    equity = np.ones(end - start + 1, dtype=float)
    cap = 1.0
    ledger = []
    # This matches backtest_15.build_one D0 indexing exactly.
    next_check = start
    while next_check < end:
        if not sig[next_check]:
            next_check += 1
            continue
        sig_i = next_check
        entry_i = sig_i + 1
        entry = float(oo[entry_i])
        if not math.isfinite(entry) or entry <= 0:
            raise ValueError(f"invalid entry: {symbol} {dt[entry_i]}")
        known_atr = float(aa[sig_i])
        if rule in ("atr", "trail") and (not math.isfinite(known_atr) or known_atr <= 0):
            raise ValueError(f"ATR missing on A signal: {symbol} {dt[sig_i]}")
        init_stop = (entry * (1 - mult) if rule == "fixed" else
                     entry - mult * known_atr if rule in ("atr", "trail") else float("nan"))
        if math.isfinite(init_stop):
            init_stop = max(0.0, init_stop)
        live_stop = init_stop
        # The current session's high can only affect the NEXT session's stop.
        high_water = entry
        exp_i = entry_i + hold
        exit_i = None
        exit_px = None
        why = None
        for j in range(entry_i, end + 1):
            # An expiry-open exit is processed before that day's high/low.
            if j == exp_i:
                exit_i, exit_px, why = j, float(oo[j]), "time_open"
            elif rule != "time" and math.isfinite(live_stop):
                if oo[j] <= live_stop:
                    exit_i, exit_px, why = j, float(oo[j]), "stop_gap_open"
                elif ll[j] <= live_stop:
                    exit_i, exit_px, why = j, float(live_stop), "stop_intraday"
            if exit_i is not None:
                pnl = fee_return(entry, exit_px)
                cap *= 1 + pnl
                equity[j - start] = cap
                break
            # Open position: value it at hypothetical close liquidation, both fees.
            equity[j - start] = cap * (1 + fee_return(entry, float(cc[j])))
            if rule == "trail":
                high_water = max(high_water, float(hh[j]))
                live_stop = max(live_stop, max(0.0, high_water - mult * known_atr))
        completed = exit_i is not None
        if not completed:
            exit_i = end
            exit_px = float(cc[end])
            why = "phase_end_mark"
            pnl = fee_return(entry, exit_px)
            # Marking at the phase end is NOT a realized closed trade.
            cap *= 1 + pnl
        # Closed positions can restart signal scanning on the NEXT session.
        low_end = exit_i if why == "time_open" else exit_i + 1
        lows = ll[entry_i:low_end]
        mae = float(np.min(lows / entry - 1)) if len(lows) else None
        record = {
            "phase": phase, "symbol": symbol, "name": name, "group": group,
            "variant": variant, "signal_date": dt[sig_i].date().isoformat(),
            "entry_date": dt[entry_i].date().isoformat(),
            "exit_date": dt[exit_i].date().isoformat(),
            "entry_price": entry, "exit_price": exit_px,
            "initial_atr": known_atr if math.isfinite(known_atr) else None,
            "initial_stop": init_stop if math.isfinite(init_stop) else None,
            "exit_reason": why, "status": "CLOSED" if completed else "OPEN_MTM",
            "holding_sessions": exit_i - entry_i,
            "return": pnl, "mae_intraday": mae,
            "regime": expansion.market_regime(benchmark, dt[sig_i])
                      if benchmark is not None else "unclassified",
        }
        ledger.append(record)
        next_check = exit_i + 1 if completed else end + 1
        if next_check <= end:
            equity[next_check - start:] = cap

    peaks = np.maximum.accumulate(np.r_[1., equity])[1:]
    mdd = float(np.min(equity / peaks - 1))
    closed = [r for r in ledger if r["status"] == "CLOSED"]
    rr = np.array([r["return"] for r in closed], dtype=float)
    # Exposed-session count: inclusive entry day until exit day before open exits.
    pos_bars = 0
    date_to_i = {d.date().isoformat(): i for i, d in enumerate(dt)}
    for r in ledger:
        a = date_to_i[r["entry_date"]]
        b = date_to_i[r["exit_date"]]
        pos_bars += max(0, b - a) if r["exit_reason"] == "time_open" else b - a + 1
    row = {
        "phase": phase, "symbol": symbol, "name": name, "group": group,
        "variant": variant, "from": dt[start].date().isoformat(),
        "to": dt[end].date().isoformat(), "bars": len(equity),
        "closed_trades": len(closed),
        "open_positions": len(ledger) - len(closed),
        "win_rate": float(np.mean(rr > 0)) if len(rr) else None,
        "avg_trade": float(np.mean(rr)) if len(rr) else None,
        "median_trade": float(np.median(rr)) if len(rr) else None,
        "worst_trade": float(np.min(rr)) if len(rr) else None,
        "cumulative_return": float(equity[-1] - 1),
        "max_drawdown": mdd,
        "exposure_bars_pct": min(1.0, pos_bars / len(equity)),
        "trade_stop_count": sum(r["exit_reason"] in ("stop_gap_open", "stop_intraday") for r in closed),
        "gap_stop_count": sum(r["exit_reason"] == "stop_gap_open" for r in closed),
        "buy_hold_return": fee_return(float(oo[start]), float(cc[end])),
        "avg_holding_sessions": float(np.mean([r["holding_sessions"] for r in closed]))
                                 if closed else None,
        "total_entry_count": len(ledger),
    }
    curve = [{"phase": phase, "symbol": symbol, "variant": variant,
              "date": dt[start + j].date().isoformat(), "equity": float(value)}
             for j, value in enumerate(equity)]
    return row, ledger, curve


def compare_a_baseline(prices: pd.DataFrame, signals: pd.DataFrame, symbol: str,
                       label: str, group: str, benchmark: pd.DataFrame | None,
                       phase: str, start: pd.Timestamp, end: pd.Timestamp,
                       new_row: dict, new_trades: list[dict]) -> None:
    """Fail rather than report incorrect D0 if it diverges from published A."""
    old_row, old_trades, _ = expansion.build_one(prices, signals, symbol, label,
                                                 group, benchmark, phase, start, end, "A")
    if old_row is None or new_row is None:
        if old_row is not None or new_row is not None:
            raise AssertionError("D0/A sample mismatch")
        return
    cols = ("closed_trades", "open_positions", "cumulative_return", "max_drawdown")
    for c in cols:
        x, y = old_row[c], new_row[c]
        if not math.isclose(x, y, rel_tol=0, abs_tol=1e-9):
            raise AssertionError(f"{symbol} {phase}: D0 vs A {c} {y} != {x}")
    if [r["entry_date"] for r in new_trades] != [r["entry_date"] for r in old_trades]:
        raise AssertionError(f"{symbol} {phase}: D0 entry dates != A")


def summarize_groups(rows: list[dict], phase: str) -> list[dict]:
    output = []
    for variant in VERSIONS:
        rr = [r for r in rows if r["phase"] == phase and r["variant"] == variant]
        if not rr:
            continue
        output.append({"phase": phase, "variant": variant, "tickers": len(rr),
                       "ticker_avg_return": float(np.mean([r["cumulative_return"] for r in rr])),
                       "ticker_med_return": float(np.median([r["cumulative_return"] for r in rr])),
                       "ticker_avg_mdd": float(np.mean([r["max_drawdown"] for r in rr])),
                       "positive_tickers": sum(r["cumulative_return"] > 0 for r in rr),
                       "completed_trades": sum(r["closed_trades"] for r in rr),
                       "stops": sum(r["trade_stop_count"] for r in rr),
                       "ticker_avg_exposure": float(np.mean([r["exposure_bars_pct"] for r in rr]))})
    return output


def fmt_pct(v) -> str:
    return "—" if v is None or not math.isfinite(v) else f"{v:+.1%}"


def render_report(summary: list[dict], groups: list[dict], errors: list[dict]) -> str:
    lines = ["# D안: A 진입 유지, 청산 규칙 비교", "",
             f"- 기준일: **{ASOF.isoformat()}**, 이후 정보 사용하지 않음.",
             "- **실험 규칙 확정**: D0 20일 시가 청산; D1 고정 -5% 손절; D2 진입 전 ATR14×2 손절; D3 진입 전 ATR14×2.5 추적손절(상향 조정은 다음 날부터); D4는 10일/40일 시가 청산.",
             "- 신호: 기존 `backtest.py`의 A 초록불만 사용, 진입은 다음 거래일 시가.",
             "- 손절: 갭하락이면 실제 시가, 장중 손절선 하회면 손절선 체결 가정. 체결 슬리피지/시장충격 미반영. STOP 체결은 보장되지 않음.",
             "- 당일 최고가를 사용하여 당일 저가 손절선을 수정하지 않음(추적손절은 종가 확정 후 **다음 날** 적용).",
             "- 수수료: 매수·매도 각각 0.1%; 현금 구간 포함, 종목별 100% 진입 가정; 배당/환율/세금 미반영.",
             "- **중요:** 청산이 빨라진 규칙은 다시 발생한 A 신호에 더 일찍 재진입할 수 있어, D0와 거래 수/진입일이 달라집니다. 이 결과는 동일 진입 코호트의 순수 청산효과가 아니라 **전체 운용 규칙 비교**입니다.",
             "- 기간 경계에서 포지션은 종료 종가로 시가평가하고 OPEN_MTM으로 표시, 완료 거래 승률에서는 제외합니다.",
             "- 2026년은 이미 연구 아이디어 설계에 참고했으므로 진정한 독립 검증이 아닙니다. 15개 자산도 특히 반도체끼리는 독립 표본이 아닙니다.",
             "- D0와 기존 15종목 A 결과는 코드를 이용해 개별 종목·기간별 수익률/MDD/진입일까지 자동 일치 검사합니다.",
             "- D1/D2/D3의 정지조건은 예시 가설이며, 과거 데이터에 맞춰 조정하지 않았습니다.", "",
             "## 2024–2025 검증기간: 14개 종목", "",
             "| 규칙 | 종목 수 | 완료 거래 수 | 종목별 평균 누적수익 | 평균 MDD | 플러스 종목 | 평균 시장 노출 |",
             "|---|---:|---:|---:|---:|---:|---:|",]
    for r in groups:
        if r["phase"] == "validation_2024_2025":
            lines.append(f"| {r['variant']} | {r['tickers']} | {r['completed_trades']} | {fmt_pct(r['ticker_avg_return'])} | {fmt_pct(r['ticker_avg_mdd'])} | {r['positive_tickers']} | {r['ticker_avg_exposure']:.1%} |")
    lines += ["", "## 관심 종목 상세: 2024–2025 (DRAM은 별도 2026년)", "",
              "| 종목 | 기간 | 규칙 | 완료 거래 | 누적수익 | MDD | 손절 체결 수 |", "|---|---|---|---:|---:|---:|---:|",]
    for symbol in ("DRAM", "005930.KS", "NVDA", "000660.KS", "MU"):
        period = "common_dram_era" if symbol == "DRAM" else "validation_2024_2025"
        for r in summary:
            if r["symbol"] == symbol and r["phase"] == period:
                lines.append(f"| {r['name']} | {period} | {r['variant']} | {r['closed_trades']} | {fmt_pct(r['cumulative_return'])} | {fmt_pct(r['max_drawdown'])} | {r['trade_stop_count']} |")
    lines += ["", "## 데이터 실패", ""]
    lines += [f"- {r['symbol']}: {r['error']}" for r in errors] if errors else ["- 없음"]
    lines += ["", "## 주의", "",
              "1. 이 파일의 숫자는 완료 실행 후 생성됩니다. 코드를 올리거나 워크플로를 등록한 것만으로 실제 백테스트를 돌린 것은 아닙니다.",
              "2. 종목별 평균 누적수익률은 실제 15종목 포트폴리오 수익률이 아닙니다.",
              "3. 과거 실험 결과로 매수·매도 타이밍이나 수익을 보장할 수 없습니다.",
              "4. 거래가 거의 없는 DRAM에서는 결론을 내리지 않습니다.", ""]
    return "\n".join(lines)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prices_map, errors, audit = {}, [], []
    for symbol, name, _, _ in UNIVERSE:
        try:
            print(f"Download {symbol}", flush=True)
            prices = expansion.fetch_prices(symbol)
            if symbol == "DRAM" and prices.index[0] < pd.Timestamp("2026-04-02"):
                raise ValueError("DRAM data predates launch")
            prices_map[symbol] = prices
            audit.append({"symbol": symbol, "name": name, "first": str(prices.index[0].date()),
                          "last": str(prices.index[-1].date()), "bars": len(prices)})
        except Exception as exc:
            msg = str(exc).replace("\n", " ")[:300]
            errors.append({"symbol": symbol, "error": msg})
            print(f"WARNING {symbol}: {msg}", flush=True)
    rows, trades, curves = [], [], []
    for symbol, name, group, benchmark_symbol in UNIVERSE:
        if symbol not in prices_map:
            continue
        print(f"Analyze {symbol}", flush=True)
        prices = prices_map[symbol]
        signals = expansion.legacy.indicators(prices)
        benchmark = prices_map.get(benchmark_symbol)
        atr_values = wilder_atr(prices)
        for phase, first, last in PHASES:
            for variant in VERSIONS:
                s, tt, cc = simulate(prices, signals, symbol, name, group, benchmark,
                                     phase, first, last, variant, atr_values)
                if s is None:
                    continue
                if variant == "D0_hold20":
                    compare_a_baseline(prices, signals, symbol, name, group, benchmark,
                                       phase, first, last, s, tt)
                rows.append(s)
                trades.extend(tt)
                curves.extend(cc)
    groups = [x for phase, _, _ in PHASES for x in summarize_groups(rows, phase)]
    write_csv(OUTPUT / "summary.csv", rows,
              ["phase", "symbol", "name", "group", "variant", "from", "to", "bars",
               "closed_trades", "open_positions", "win_rate", "avg_trade", "median_trade",
               "worst_trade", "cumulative_return", "max_drawdown", "exposure_bars_pct",
               "trade_stop_count", "gap_stop_count", "buy_hold_return", "avg_holding_sessions", "total_entry_count"])
    write_csv(OUTPUT / "trades.csv", trades,
              ["phase", "symbol", "name", "group", "variant", "signal_date", "entry_date",
               "exit_date", "entry_price", "exit_price", "initial_atr", "initial_stop",
               "exit_reason", "status", "holding_sessions", "return", "mae_intraday", "regime"])
    write_csv(OUTPUT / "equity.csv", curves, ["phase", "symbol", "variant", "date", "equity"])
    write_csv(OUTPUT / "comparison.csv", groups,
              ["phase", "variant", "tickers", "ticker_avg_return", "ticker_med_return",
               "ticker_avg_mdd", "positive_tickers", "completed_trades", "stops", "ticker_avg_exposure"])
    write_csv(OUTPUT / "audit.csv", audit, ["symbol", "name", "first", "last", "bars"])
    write_csv(OUTPUT / "errors.csv", errors, ["symbol", "error"])
    (OUTPUT / "report.md").write_text(render_report(rows, groups, errors), encoding="utf-8")
    required = expansion.REQUIRED
    coverage_ok = len(prices_map) >= 12 and not (required - set(prices_map))
    (OUTPUT / "run_metadata.json").write_text(json.dumps({
        "asof": ASOF.isoformat(), "strategy": "A signals with D0-D4 exit models",
        "requested": len(UNIVERSE), "downloaded": len(prices_map),
        "failed_symbols": [r["symbol"] for r in errors], "coverage_ok": coverage_ok,
        "D0_A_assertions": "passed" if coverage_ok else "partial",
        "status": "success" if coverage_ok else "incomplete",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"D study: {len(prices_map)}/{len(UNIVERSE)} assets, {len(rows)} strategy-period rows")
    if not coverage_ok:
        raise RuntimeError(f"Insufficient coverage: {len(prices_map)}/15; required missing {required-set(prices_map)}")


if __name__ == "__main__":
    main()
