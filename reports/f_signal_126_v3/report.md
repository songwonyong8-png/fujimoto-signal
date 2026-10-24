# F v3 RSI → MACD → Ichimoku/Volume Profile, 1:2:6

Price-data cutoff: 2026-10-22. Frozen market-cap snapshot observed 2026-10-24.
Selection: Nasdaq-100 market-cap top 50 securities, source: https://www.slickcharts.com/nasdaq100/marketcap. NOT historical membership.
Stage 1 RSI rebound; stage 2 strict MACD golden cross after stage 1; stage 3 cloud support after stage 2.
F_cloud_vp also requires prior-120-bar POC proximity to cloud top and close.
Stages execute next-session OPEN. Fees 0.1% each side. Unused cash earns 0%. Fixed 40-session exit.
Parameters (RSI <=30 within 5 bars, stage gap <=20, cloud touch 1%, VP distance 4%) are hypotheses.
No lookahead in indicator construction. Split/dividend/FX/tax/slippage not fully modeled.
Current ranking backtested historically creates survivorship/selection bias; not out-of-sample.

## 2024-2025 group-level summary (independent symbols, simple average)
| variant | tickers | trades | avg cumulative return | avg MDD | win rate | stage 3 fills |
|---|---:|---:|---:|---:|---:|---:|
| F_lump | 56 | 125 | +18.7% | -16.6% | 68.0% | 0 |
| F_cloud | 56 | 125 | +8.1% | -7.5% | 61.6% | 36 |
| F_cloud_vp | 56 | 125 | +5.8% | -5.9% | 64.0% | 12 |

## Download/analysis failures
- SPCX: Only 92 valid daily bars; at least 120 expected
