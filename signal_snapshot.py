"""Live-screen projection of the existing F9-A engine, NOT a second trading rule.

The iPhone screen must never infer real brokerage holdings. It reconstructs a
virtual, fully rules-based campaign from F9 fill and lot ledgers, and evaluates
only today's *completed daily candle* for tomorrow's OPEN order candidates.
"""
from __future__ import annotations

from datetime import date
import math
from typing import Any

import numpy as np
import pandas as pd

import backtest_f_v6 as v6
import backtest_f_v9 as v9

ENGINE_NAME = "F9-A"
START_DATE = pd.Timestamp("2020-01-01")


def _safe_number(x: Any, digits: int = 5) -> float | None:
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, digits) if math.isfinite(x) else None


def _safe_bool(x: Any) -> bool:
    try:
        return bool(x) if pd.notna(x) else False
    except (ValueError, TypeError):
        return False


def _datespan_bars(prices: pd.DataFrame, since_date: str | None) -> int | None:
    if not since_date:
        return None
    matching = np.flatnonzero(prices.index.date == date.fromisoformat(since_date))
    if not len(matching):
        return None
    return len(prices) - 1 - int(matching[-1])


def build_strategy_snapshot(prices: pd.DataFrame, ticker: str, signals: pd.DataFrame | None = None) -> dict:
    """Simulate F9-A then project account status and end-of-day pending orders.

    Does not claim historical results are independent or account positions real.
    A close[t] signal is NOT a completed fill until open[t+1] actually arrives.
    """
    if len(prices) < 120:
        raise ValueError("F9 requires at least 120 OHLCV sessions")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("Price dates must be unique and ascending")
    if signals is None:
        signals = v6.indicators(prices)
    if len(signals) != len(prices) or not signals.index.equals(prices.index):
        raise ValueError("Signals and prices must use the same trading dates")
    last = len(prices) - 1
    mark_date = prices.index[last].date().isoformat()
    first = prices.index[0]
    result, campaigns, lots, fills, _equity = v9.simulate(
        prices, signals, "pwa", first, prices.index[-1], "WATCHLIST", ticker, "A"
    )
    if result is None:
        raise RuntimeError("F9 returned no virtual account")

    active = next((x for x in reversed(campaigns) if x["status"] == "OPEN_MTM"), None)
    active_id = active["campaign"] if active else None
    held_lots = {
        int(x["stage"]): x for x in lots
        if x["status"] == "OPEN_MTM" and x["campaign"] == active_id
    } if active else {}
    campaign_fills = [x for x in fills if x["campaign"] == active_id] if active else []
    bought_stage = {int(x["stage"]) for x in campaign_fills if x["side"] == "BUY"}
    last_signal_1 = active["first_signal"] if active else None
    last_signal_2 = next((x["signal_date"] for x in reversed(campaign_fills)
                          if x["stage"] == 2 and x["side"] == "BUY"), None)
    age1 = _datespan_bars(prices, last_signal_1)
    age2 = _datespan_bars(prices, last_signal_2)

    one = signals.iloc[-1]
    rsi_entry = _safe_bool(one["stage1"])
    macd_entry = _safe_bool(one["stage2"])
    ichi_entry = _safe_bool(one["f6_s3_breakout"])
    rsi_sell = _safe_bool(one["rsi_failure"])
    macd_sell = _safe_bool(one["macd_death"])
    ichi_sell = v9.stage3_exit(
        "A", last, prices.close.to_numpy(float),
        signals.cloud_top.to_numpy(float), signals.cloud_bottom.to_numpy(float)
    )

    next_orders: list[dict] = []
    if active:
        # Priority and entitlement exactly mirror F9.simulate.
        if 1 in held_lots and rsi_sell:
            next_orders.append(dict(side="SELL", stage=1, reason="RSI_BACK_BELOW_30", weight=1 / 9))
        if 2 in held_lots and macd_sell:
            next_orders.append(dict(side="SELL", stage=2, reason="MACD_DEATH_CROSS", weight=2 / 9))
        if 3 in held_lots and ichi_sell:
            next_orders.append(dict(side="SELL", stage=3, reason="CLOUD_BOTTOM_BREAK", weight=6 / 9))
        if not next_orders:
            if (1 in held_lots and 2 not in bought_stage and age1 is not None
                and 0 < age1 <= v9.MAX_STAGE_GAP and macd_entry):
                next_orders.append(dict(side="BUY", stage=2, reason="MACD_GOLDEN", weight=2 / 9))
            elif (1 in held_lots and 2 in held_lots and 3 not in bought_stage
                  and age2 is not None and 0 < age2 <= v9.MAX_STAGE_GAP and ichi_entry):
                next_orders.append(dict(side="BUY", stage=3, reason="ICHI_STRICT_CROSS", weight=6 / 9))
    else:
        # Same-open full-campaign exit explicitly prohibits re-entry that day.
        last_exited_today = bool(campaigns and campaigns[-1]["status"] == "CLOSED"
                                 and campaigns[-1]["last_mark_or_exit"] == mark_date)
        if not last_exited_today and last >= 78 and rsi_entry:
            next_orders.append(dict(side="BUY", stage=1, reason="RSI_REBOUND", weight=1 / 9))

    if next_orders:
        status = "SELL_SIGNAL" if next_orders[0]["side"] == "SELL" else "BUY_SIGNAL"
        headline = ("일봉 매도 신호 확정" if status == "SELL_SIGNAL" else
                    "일봉 단계별 매수 신호 확정")
        detail = "다음 거래일 시가가 확인되어야 체결됩니다. 현재 종가 체결이 아닙니다."
    elif not active:
        status, headline, detail = "WAIT_RSI", "1차 RSI 반등 대기", "현재 가상 보유 물량이 없습니다."
    elif 3 in held_lots:
        status, headline, detail = "HOLD_3", "3차 물량 보유 · A형 청산 감시", "종가가 구름대 하단 아래로 내려가면 3차 매도 후보입니다."
    elif 2 in held_lots:
        if 3 in bought_stage:
            status, headline, detail = "HOLD_2", "2차 물량 보유 · 3차는 청산", "3차는 이 매매 주기에서 다시 매수할 수 없습니다."
        elif age2 is not None and age2 > v9.MAX_STAGE_GAP:
            status, headline, detail = "HOLD_2", "2차 보유 · 3차 진입 기한 종료", "3차는 이번 매매 주기에서 더 이상 매수할 수 없습니다."
        else:
            status, headline, detail = "HOLD_2", "2차 물량 보유", "3차 일목균형표 돌파 신호를 감시합니다."
    elif 1 in held_lots:
        if 2 in bought_stage:
            status, headline, detail = "HOLD_1", "1차 물량 보유 · 2차는 청산", "2차는 이 매매 주기에서 다시 매수할 수 없습니다."
        elif age1 is not None and age1 > v9.MAX_STAGE_GAP:
            status, headline, detail = "HOLD_1", "1차 보유 · 2차 진입 기한 종료", "2차는 이번 매매 주기에서 더 이상 매수할 수 없습니다."
        else:
            status, headline, detail = "HOLD_1", "1차 물량 보유", "2차 MACD 골든크로스 신호를 감시합니다."
    else:
        status, headline, detail = "PARTIAL_HOLD", "일부 물량 보유", "매도된 물량은 같은 매매 주기에서 재매수하지 않습니다."

    closes = prices.close.astype(float)
    line = closes.ewm(span=12, adjust=False).mean() - closes.ewm(span=26, adjust=False).mean()
    signal_line = line.ewm(span=9, adjust=False).mean()
    indicators = {
        "rsi14": _safe_number(one.get("rsi"), 2),
        "macd": _safe_number(line.iloc[-1], 5),
        "macd_signal": _safe_number(signal_line.iloc[-1], 5),
        "macd_histogram": _safe_number(line.iloc[-1] - signal_line.iloc[-1], 5),
        "cloud_top": _safe_number(one.get("cloud_top"), 4),
        "cloud_bottom": _safe_number(one.get("cloud_bottom"), 4),
        "tenkan_above_rising_kijun": _safe_bool(one.get("tk_bullish", False)),
        "chikou_confirmation": _safe_bool(one.get("chikou_bullish", False)),
        "cloud_cross_up": _safe_bool(one.get("cloud_up_cross", False)),
    }
    signals_today = {
        "rsi_rebound": rsi_entry,
        "macd_golden": macd_entry,
        "ichimoku_strict": ichi_entry,
        "rsi_back_below_30": rsi_sell,
        "macd_death": macd_sell,
        "cloud_bottom_break": bool(ichi_sell),
        "cloud_top_break_comparison_only": v9.stage3_exit(
            "B", last, prices.close.to_numpy(float),
            signals.cloud_top.to_numpy(float), signals.cloud_bottom.to_numpy(float)),
        "cloud_top_two_closes_comparison_only": v9.stage3_exit(
            "C", last, prices.close.to_numpy(float),
            signals.cloud_top.to_numpy(float), signals.cloud_bottom.to_numpy(float)),
    }

    positions = {}
    for stage,weight in ((1,1/9),(2,2/9),(3,6/9)):
        x = held_lots.get(stage)
        positions[str(stage)] = {
            "held": bool(x),
            "ever_bought_in_campaign": stage in bought_stage,
            "allocation_of_starting_campaign": round(weight, 6),
            "entry_date": x["entry_date"] if x else None,
            "entry_open": _safe_number(x["entry_open"], 4) if x else None,
            "unrealized_return_net_est": _safe_number(x["net_return"], 5) if x else None,
            "exit_rule": {1:"RSI 30 이하",2:"MACD 데드크로스",3:"구름대 하단 종가 이탈 (A형)"}[stage],
        }

    return {
        "version": ENGINE_NAME,
        "asof": mark_date,
        "ticker": ticker,
        "state": status,
        "headline": headline,
        "detail": detail,
        "entry_chain": "RSI rebound → MACD golden → strict Ichimoku breakout",
        "lot3_exit": "A / cloud-bottom close break",
        "virtual_account": True,
        "account_cumulative_return": _safe_number(result["cumulative_return"], 5),
        "virtual_campaign_open": active is not None,
        "campaign_first_signal": last_signal_1,
        "stage2_signal_date": last_signal_2,
        "stage2_days_remaining": max(0,20-age1) if age1 is not None and 2 not in bought_stage else None,
        "stage3_days_remaining": max(0,20-age2) if age2 is not None and 3 not in bought_stage else None,
        "positions": positions,
        "signals_today": signals_today,
        "indicators": indicators,
        "next_open_orders": next_orders,
        "recent_fills": [dict(date=x["date"],side=x["side"],stage=x["stage"],
                              reason=x["reason"],price=_safe_number(x["price"],4))
                         for x in fills[-8:]],
        "study_limitations": "Historical backtest signals; excludes slippage, taxes, FX, and brokerage holdings.",
    }
