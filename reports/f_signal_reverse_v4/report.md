# F v4: 1:2:6 sequential buys + reverse signal exits

Data cutoff: 2026-10-22; frozen current Nasdaq top50 securities snapshot: 2026-10-24.
## Exact trading assumptions

- BUY1: v3 RSI oversold rebound (last 5 days RSI<=30, current RSI 30..48 and rising close); 1/9.
- BUY2: fresh MACD golden cross after BUY1 signal, within 20 sessions; 2/9.
- BUY3: unchanged v3 Ichimoku cloud-top test/reclaim, optional volume-profile POC match, after BUY2 signal within 20 sessions; 6/9.
- SELL3: close below cloud BOTTOM; next-session open sell exact stage-3 lot (not 66% of current portfolio market value).
- MACD death cross: next-session open sell ALL remaining lots, stage3 first then stages2+1 (3/9 if all stages previously filled).
- RSI again <=30: loss of initial entry rationale => next-session open sell all remaining lots as fail-safe.
- No re-buy of an already filled stage in one campaign. No 40-session automatic liquidation in v4.
- One position per symbol and phase; no interest on cash; 0.10% each side; fill at NEXT OPEN.
- Open positions at period cutoff are marked to last CLOSE net of hypothetical selling fee (OPEN_MTM) and excluded from closed-trade win rate.
- v3 reference rows use its ORIGINAL 40-day schedule; entry events may differ and comparisons are NOT perfectly paired.
- RSI 30, cloud-bottom exit, 20-day stage windows and other parameters are proposed experimental assumptions, not proprietary confirmed rules.
- No take-profit. Neither gap risk nor slippage, tax, foreign exchange, corporate actions or dividends are fully modeled.
- Frozen 2026 top50 securities applied historically creates survivorship bias. 2026 is not an independent holdout.

## 2024-2025 summary, simple per-ticker mean (including tickers with 0 signals)
| Variant | Tickers | closed | open MTM | avg cumulative | avg CAGR | avg MDD | pooled closed win | 3rd buys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F4_cloud_reverse | 56 | 220 | 11 | +3.3% | +1.5% | -7.1% | 32.3% | 38 |
| F4_cloud_vp_reverse | 56 | 220 | 11 | +2.8% | +1.3% | -5.5% | 35.0% | 9 |
| F3_cloud_40 | 56 | 125 | 0 | +8.1% | +3.8% | -7.5% | n/a | 36 |
| F3_cloud_vp_40 | 56 | 125 | 0 | +5.8% | +2.8% | -5.9% | n/a | 12 |

## Download / symbol analysis failures
- SPCX: Only 92 valid daily bars; at least 120 expected
