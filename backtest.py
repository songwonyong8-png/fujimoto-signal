"""Three-strategy research backtest for DRAM, Samsung Electronics, NVIDIA.

A mirrors Fujimoto Signal v1 app.js GREEN rule (2026-10-23 snapshot).
B/C are *research hypotheses*, not verified proprietary Fujimoto rules.
Only daily close-data known at t is used for signals; trades at t+1 open.
Data downloaded on each run, files/report include provenance and audit trail.
"""
from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ASOF = date(2026, 10, 22)
START = "2021-01-01"
DRAM_LAUNCH = pd.Timestamp("2026-04-02")
OUT = Path("reports")
OUT.mkdir(exist_ok=True)
SYMBOLS = {"DRAM": "DRAM", "Samsung Electronics": "005930.KS", "NVIDIA": "NVDA"}
HORIZONS = (5, 20, 60)
HOLD = 20
FEE_PER_SIDE = 0.001  # 0.10% per side; synthetic same assumption for comparability
MIN_SAMPLE = 20


def normalize_prices(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        raise RuntimeError("Yahoo Finance returned no OHLCV rows")
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    cols = {x.lower(): x for x in df.columns}
    required = ("open", "high", "low", "close", "volume")
    if any(k not in cols for k in required):
        raise RuntimeError(f"Missing OHLCV fields: {df.columns}")
    d = df[[cols[x] for x in required]].copy()
    d.columns = required
    d.index = pd.DatetimeIndex(d.index).tz_localize(None).normalize() if d.index.tz is not None else pd.DatetimeIndex(d.index).normalize()
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d = d.loc[d.index.date <= ASOF]
    d = d.apply(pd.to_numeric, errors="coerce").dropna()
    d = d[(d.open > 0) & (d.close > 0) & (d.high >= d.low) & (d.volume >= 0)]
    if len(d) < 120:
        raise RuntimeError(f"Only {len(d)} valid daily bars; at least 120 expected")
    return d


def load_prices(symbol: str) -> pd.DataFrame:
    raw = yf.download(symbol, start=START, end=(ASOF + pd.Timedelta(days=1)).isoformat(),
                      auto_adjust=False, progress=False, threads=False, actions=False)
    return normalize_prices(raw)


def ema(vals: np.ndarray, n: int) -> np.ndarray:
    k = 2 / (n + 1)
    out = np.empty(len(vals), dtype=float)
    out[0] = vals[0]
    for i in range(1, len(vals)):
        out[i] = vals[i] * k + out[i - 1] * (1 - k)
    return out


def wilder_rsi(vals: np.ndarray, n: int = 14) -> float:
    if len(vals) < n + 2:
        return np.nan
    d = np.diff(vals)
    gain = sum(np.maximum(d[:n], 0)) / n
    loss = sum(np.maximum(-d[:n], 0)) / n
    for change in d[n:]:
        gain = (gain * (n - 1) + max(change, 0)) / n
        loss = (loss * (n - 1) + max(-change, 0)) / n
    return (50. if gain == 0 else 100.) if loss == 0 else 100 - 100 / (1 + gain / loss)


def indicators(d: pd.DataFrame) -> pd.DataFrame:
    """Rolling one-year history reproduces the app's ema initial seeding per day."""
    arr = d[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    rec = []
    for t in range(len(arr)):
        base = {"index": t, "date": d.index[t], "score": np.nan,
                "A": False, "B": False, "C": False,
                "rsi": np.nan, "distance": np.nan, "broken": False}
        if t < 59:
            rec.append(base)
            continue
        a = arr[max(0, t - 251):t + 1]
        closes, vols = a[:, 3], a[:, 4]
        c, prev = closes[-1], closes[-2]
        ma20, ma50 = np.mean(closes[-20:]), np.mean(closes[-50:])
        dist = (c / ma20 - 1) * 100
        rr = wilder_rsi(closes)
        mac = ema(closes, 12) - ema(closes, 26)
        hs = mac - ema(mac, 9)
        improving = bool(hs[-1] > hs[-2])
        vol_ratio = vols[-1] / np.mean(vols[-20:]) if np.mean(vols[-20:]) else 0
        support = float(np.min(a[-21:-1, 2]))
        recover = c > prev
        broken = c < support
        oversold = rr <= 35 and dist <= -5
        confirm = 30 <= rr <= 48 and dist <= 0 and improving and recover and not broken
        score = (25 if 30 <= rr <= 45 else 13 if rr < 30 else 0) + \
                (20 if -12 <= dist <= -5 else 7 if dist < -12 else 10 if dist < 0 else 0) + \
                (15 if improving else 0) + \
                (15 if vol_ratio >= 1.2 and recover else 7 if vol_ratio >= 0.8 else 0) + \
                (15 if not broken and recover else 7 if not broken else 0) + \
                (10 if c > ma50 else 5 if c > ma20 else 0)
        state = "red" if broken else ("green" if confirm and score >= 65 else
                                     "yellow" if oversold or confirm or score >= 45 else "red")
        # B: recently oversold, then positive candle + improving histogram + non-depressed volume.
        # C: B plus stronger price confirmation: previous day's HIGH break and 5-day MA reclaim.
        is_recent_oversold = False
        for k in range(max(59, t-7), t+1):
            # Use ONLY historical observations up to t. One-bar drop in RSI or MA distance
            # is sufficient to mark a recent oversold phase; no forward data referenced.
            w = arr[max(0, k-251):k+1, 3]
            if len(w) >= 60 and wilder_rsi(w) <= 35 and ((w[-1]/np.mean(w[-20:])-1)*100) <= -5:
                is_recent_oversold = True
                break
        bullish = c > a[-1, 0] and recover
        b = bool(is_recent_oversold and bullish and improving and vol_ratio >= .8 and rr <= 55 and not broken)
        c_strategy = bool(b and c > a[-2, 1] and c > np.mean(closes[-5:]) and vol_ratio >= 1.0)
        base.update(score=score, rsi=rr, distance=dist, broken=broken,
                    A=(state == "green"), B=b, C=c_strategy)
        rec.append(base)
    out = pd.DataFrame(rec).set_index("date")
    return out


def fee_return(entry: float, exit_: float) -> float:
    return (exit_ * (1 - FEE_PER_SIDE)) / (entry * (1 + FEE_PER_SIDE)) - 1


def event_rows(prices: pd.DataFrame, sig: pd.DataFrame, ticker: str, scope: str,
               start: pd.Timestamp) -> list[dict]:
    """Signal-level non-independent forwards; no fake future returns for recent signals."""
    arr = prices[["open", "close"]].to_numpy()
    events = []
    for col in ("A", "B", "C"):
        for i in np.flatnonzero(sig[col].to_numpy(dtype=bool)):
            dt = prices.index[i]
            if dt < start:
                continue
            x = {"ticker": ticker, "scope": scope, "strategy": col,
                 "signal_date": dt.date().isoformat(), "entry_date": "", "entry_price": ""}
            if i + 1 >= len(arr):
                continue
            x["entry_date"] = prices.index[i+1].date().isoformat()
            x["entry_price"] = float(arr[i+1, 0])
            for h in HORIZONS:
                # Entry at next day's open; exit after exactly h sessions, at the open.
                x[f"return_{h}d"] = (fee_return(arr[i+1, 0], arr[i+1+h, 0])
                                     if i+1+h < len(arr) else "")
            events.append(x)
    return events


def trades_for(prices: pd.DataFrame, sig: pd.DataFrame, ticker: str, scope: str,
               start: pd.Timestamp, strategy: str) -> list[dict]:
    # Keep only independent, non-overlapping 20-session positions.
    arr = prices[["open", "close"]].to_numpy()
    signal = sig[strategy].to_numpy(dtype=bool)
    rows = []
    next_eligible = 0
    for i in range(59, len(arr)):
        if i < next_eligible or prices.index[i] < start or not signal[i]:
            continue
        enter = i + 1
        exit_ = enter + HOLD
        if enter >= len(arr):
            continue  # signal on the most recent day cannot be filled yet
        open_position = exit_ >= len(arr)
        if open_position:
            exit_ = len(arr) - 1  # mark to latest close, NOT a completed trade
        entry_price = float(arr[enter, 0]); exit_price = float(arr[exit_, 0] if not open_position else prices.iloc[-1].close)
        ret = fee_return(entry_price, exit_price)
        lows = arr[enter:exit_+1, 1]
        # Daily close-to-entry adverse excursion proxy (uses only dates inside trade)
        mae = float(np.min(lows / entry_price - 1))
        rows.append({"ticker": ticker, "scope": scope, "strategy": strategy,
                     "signal_date": prices.index[i].date().isoformat(),
                     "entry_date": prices.index[enter].date().isoformat(),
                     "exit_date": prices.index[exit_].date().isoformat(),
                     "status": "OPEN_MTM" if open_position else "CLOSED",
                     "entry_price": entry_price, "exit_price": exit_price,
                     "return": float(ret), "mae": mae})
        next_eligible = enter + HOLD
    return rows


def equity_and_mdd(prices: pd.DataFrame, rows: list[dict], start: pd.Timestamp) -> tuple[float,float]:
    """Daily close-marked strategy equity incl. inactive periods and both side fees."""
    p = prices.loc[prices.index >= start]
    if p.empty:
        return 0., 0.
    eq = np.ones(len(p), dtype=float)
    ordered = sorted(rows, key=lambda x: x["entry_date"])
    capital = 1.0
    last_position_end = None
    event_index = 0
    for j, (dt, r) in enumerate(p.iterrows()):
        while event_index < len(ordered) and dt > pd.Timestamp(ordered[event_index]["exit_date"]):
            event_index += 1
        if event_index < len(ordered):
            t = ordered[event_index]
            start_date, end_date = pd.Timestamp(t["entry_date"]), pd.Timestamp(t["exit_date"])
            if start_date <= dt < end_date:
                entry = t["entry_price"]
                eq[j] = capital * ((r["close"]*(1-FEE_PER_SIDE)) / (entry*(1+FEE_PER_SIDE)))
            elif dt == end_date:
                capital *= 1 + t["return"]
                eq[j] = capital
                event_index += 1
            else:
                eq[j] = capital
        else:
            eq[j] = capital
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    mdd = float((eq / peak - 1).min())
    return float(eq[-1] - 1), mdd


def summary_stats(prices, trades, events, start, label, scope, strategy):
    tt = [x for x in trades if x["scope"] == scope and x["strategy"] == strategy and x["ticker"] == label]
    ee = [x for x in events if x["scope"] == scope and x["strategy"] == strategy and x["ticker"] == label]
    closed = [t for t in tt if t["status"] == "CLOSED"]
    returns = np.array([t["return"] for t in closed], dtype=float)
    cumulative, mdd = equity_and_mdd(prices, tt, start)
    buy_hold = fee_return(float(prices.loc[prices.index >= start].iloc[0].open), float(prices.iloc[-1].close))
    row = {"scope": scope, "ticker": label, "strategy": strategy,
           "from": prices.loc[prices.index >= start].index[0].date().isoformat(),
           "to": prices.index[-1].date().isoformat(),
           "signal_count": len(ee), "closed_trades": len(closed),
           "open_positions": len(tt)-len(closed),
           "win_rate": float(np.mean(returns > 0)) if len(returns) else None,
           "mean_trade_return": float(np.mean(returns)) if len(returns) else None,
           "median_trade_return": float(np.median(returns)) if len(returns) else None,
           "cumulative_return": cumulative, "max_drawdown": mdd,
           "buy_hold_return": buy_hold,
           "max_adverse": min([t["mae"] for t in tt], default=None)}
    for h in HORIZONS:
        rr = np.array([e[f"return_{h}d"] for e in ee if e[f"return_{h}d"] != ""], dtype=float)
        row[f"forward_{h}d_count"] = len(rr)
        row[f"forward_{h}d_mean"] = float(np.mean(rr)) if len(rr) else None
        row[f"forward_{h}d_win"] = float(np.mean(rr > 0)) if len(rr) else None
    return row


def fmtp(v):
    return "—" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:+.1%}"


def as_md(rows, cols, headers):
    body = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        body.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(body)


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("No rows\n", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader(); w.writerows(rows)


def main():
    all_summaries, all_events, all_trades, audits = [], [], [], []
    scope_defs = ["Common_DRAM_era", "Extended"]
    for label, symbol in SYMBOLS.items():
        print("Downloading", symbol, flush=True)
        prices = load_prices(symbol)
        if label == "DRAM" and prices.index[0] < DRAM_LAUNCH:
            raise RuntimeError("DRAM dataset unexpectedly predates 2026-04-02 launch")
        sig = indicators(prices)
        audits.append({"ticker": label, "symbol": symbol, "bars": len(prices),
                       "first": prices.index[0].date().isoformat(),
                       "last": prices.index[-1].date().isoformat(),
                       "source": "Yahoo Finance via yfinance; auto_adjust=False"})
        for scope in scope_defs:
            if scope == "Common_DRAM_era":
                # Fairness: starting sample common to ETF post-launch, with pre-launch warm-up for other names.
                start = max(DRAM_LAUNCH + pd.Timedelta(days=90), prices.index[59])
            else:
                start = prices.index[59]
            starts = prices.loc[prices.index >= start]
            if len(starts) < 25:
                continue
            ev = event_rows(prices, sig, label, scope, start)
            tr = [t for s in ("A", "B", "C") for t in trades_for(prices, sig, label, scope, start, s)]
            all_events.extend(ev); all_trades.extend(tr)
            for s in ("A", "B", "C"):
                all_summaries.append(summary_stats(prices, tr, ev, start, label, scope, s))
        # Last few eligible signal dates, useful for current-status checks
        recent = sig.iloc[-10:][["score", "rsi", "distance", "broken", "A", "B", "C"]].reset_index()
        recent.insert(0, "ticker", label)
        path = OUT / (symbol.replace(".", "_") + "_recent_signals.csv")
        recent.to_csv(path, index=False)
    write_csv(OUT/"backtest_summary.csv", all_summaries)
    write_csv(OUT/"backtest_trades.csv", all_trades)
    write_csv(OUT/"backtest_signal_events.csv", all_events)
    write_csv(OUT/"data_audit.csv", audits)
    md = ["# 후지모토형 매매신호 A/B/C 백테스트", "",
          f"- **마지막 인정 거래일:** {ASOF.isoformat()} (이후 데이터 사용 금지)",
          "- **A:** 현재 app.js(v1.0)의 초록불 로직 동일. 빨간불·노란불은 신규 매수 신호 아님.",
          "- **B:** 최근 7거래일 과매도(RSI ≤35, 20일선 이격도 ≤−5%) 후 양봉·전일 종가 상승, MACD 히스토그램 개선, 상대 거래량 ≥0.8, 지지선 유지.",
          "- **C:** B 및 전일 고가 돌파, 5일 이동평균선 위, 상대 거래량 ≥1.0 충족.",
          "- **진입/청산:** 신호 당일 종가 확정 뒤 다음 거래일 시가 진입, 20거래일 보유 후 시가 청산. 같은 종목·전략에서 중복 포지션 없음.",
          "- **거래 비용:** 매수·매도 각각 0.10% 가정. 환율·세금·슬리피지·배당금은 별도 처리하지 않음.",
          "- **공통 비교기간:** ETF 출시 후 90일 이후. ETF 자체 이력 부족 및 통계적 제약이 있습니다.",
          "- **확장 기간:** 각 종목별 수집 데이터의 60번째 거래일부터. NVDA·삼성은 DRAM보다 긴 과거 포함.",
          "- **현재 열린 포지션:** 청산거래 승률/평균에는 제외하고, 누적 수익률과 MDD에는 마지막 종가 평가손익(예상 청산 수수료 포함)을 반영.",
          "- **참고:** 삼성전자는 KRW, 미국 종목은 USD. 비교 수익률은 각 종목의 현지 통화 기준이며 환율을 반영하지 않음.",
          "- **리서치 주의:** B/C는 영상 또는 후지모토 원전의 정확한 공식으로 확증된 규칙이 아니라 고정된 실험가설입니다.",
          "- **기술 주의:** yfinance 비공식 데이터, DRAM 출시일 2026-04-02, 샘플 수 및 데이터 정정 가능성.",
          "", "## 수집 데이터 출처/기간", "",
          as_md(audits, ["ticker", "symbol", "bars", "first", "last"],
                ["종목", "코드", "봉 수", "최초", "마지막"]), ""]
    for scope in scope_defs:
        data = []
        for x in all_summaries:
            if x["scope"] != scope:
                continue
            data.append({"ticker": x["ticker"], "strategy": x["strategy"],
                         "count": str(x["closed_trades"]) + (f"(+{x['open_positions']}미청산)" if x["open_positions"] else ""), "win": fmtp(x["win_rate"]),
                         "avg": fmtp(x["mean_trade_return"]), "total": fmtp(x["cumulative_return"]),
                         "mdd": fmtp(x["max_drawdown"]), "hold": fmtp(x["buy_hold_return"]),
                         "forward5": f"{x['forward_5d_count']}건/{fmtp(x['forward_5d_mean'])}",
                         "forward20": f"{x['forward_20d_count']}건/{fmtp(x['forward_20d_mean'])}",
                         "forward60": f"{x['forward_60d_count']}건/{fmtp(x['forward_60d_mean'])}"})
        md.extend(["## " + ("DRAM 출시 후 공통 비교" if scope == "Common_DRAM_era" else "각 종목의 확장 분석"), "",
                   as_md(data, ["ticker", "strategy", "count", "win", "avg", "total", "mdd", "hold", "forward5", "forward20", "forward60"],
                         ["종목", "전략", "청산거래", "승률", "거래평균", "누적수익률", "최대낙폭", "단순보유", "5일 후", "20일 후", "60일 후"]), ""])
    md += ["## 유의사항", "",
           "- 5/20/60일 후 수익률은 신호별 미래 수익률이며 **서로 중복된 이벤트**가 포함될 수 있습니다. 독립 시행의 신뢰구간으로 해석하면 안 됩니다.",
           "- 청산 거래가 20건 미만이라면 승률을 안정적 통계로 해석하지 마세요. 0건의 경우 우수한 성과가 아니라 **신호 부재**입니다.",
           "- 백테스트 마지막 20·60거래일 내 발생한 신호는 충분한 미래 데이터가 없어 해당 기간의 신호별 미래 수익률에서 제외됩니다(우측 검열). 미청산 실전 포지션은 종가 시가평가합니다.",
           "- 지표/전략에 동일 종목 과거 데이터를 참고해 규칙을 선택한 설계 편향이 있을 수 있으므로 별도 후행기간 검증이 필요합니다.",
           "- 모든 전략의 최신 실거래 적용은 보류합니다. 본 결과는 전략 설계 실험이며 투자 권유가 아닙니다.",
           "", "## 재현 방법", "", "`python backtest.py` (yfinance, numpy, pandas 필요)",
           "", "상세 거래: `reports/backtest_trades.csv`, 신호별 수익률: `reports/backtest_signal_events.csv`, 원자료 검사: `reports/data_audit.csv`."]
    (OUT/"backtest_summary.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    print((OUT/"backtest_summary.md").read_text()[:5000])


if __name__ == "__main__":
    main()
