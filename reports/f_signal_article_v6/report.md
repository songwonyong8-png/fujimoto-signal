# F6 — Blog-informed Ichimoku confirmation + RSI profit-taking, daily-bar research

Article: https://myrichlife.tistory.com/643 (secondary blog summary, NOT verified discretionary source-code).
OHLCV ends 2026-10-22; large-cap ranking snapshot 2026-10-24.
## Verified implementation versus research hypotheses
- Article-derived principles: stage up 1:2:6; RSI oversold, MACD cross, Ichimoku Tenkan/Kijun, cloud breakout, Chikou confirmation; RSI >=70 profit consideration.
- Experimental choices: entry 1 RSI 30..48 rebound with green daily candle; entry 2 MACD cross within 20 bars; entry3 rising Kijun and Tenkan>Kijun, Chikou close[t]>high[t-26], plus cloud cross on the day (STRICT) or within past 20 bars (TREND).
- VP alternative adds previous-120-session volume-at-typical-price POC (32 bins) within 4% of cloud top and current close; optional research choice.
- Sell 1/9 RSI <=30 thesis break OR upward RSI cross 70 profit take, sell 2/9 MACD death, sell 6/9 close below cloud bottom. Independent lots only; no cascading forced sell.
- Every signal closes at t; executed next-day OPEN, 0.1% commission each side; no time-based exit or rebuy of sold lot in same campaign.
- F5-A reference uses ORIGINAL F5 entry/exit implementation without added candlestick, RSI70 or stricter Ichimoku constraints.
- 40/80/120-day matched studies are evaluation cutoffs, not exit rules. Open lots marked to close less hypothetical sale fee.
- Fundamental historical growth gate: off. Strict mode requires point-in-time verified CSV inputs (by PUBLICATION date).
- 5-minute/day-trading validation NOT performed: only daily bars available for full multi-year backtest.
- Live earnings growth screening NOT faked from modern data. No slippage, tax, dividend or FX; survivorship bias persists.

## 2024-2025 account study (mean of per-ticker outcomes; not pooled portfolio)
| strategy | tickers | closed | open | mean cumulative | median cumulative | avg MDD | avg exposure | third fills | RSI70 profit sells |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F5_A_cloud | 56 | 167 | 51 | +11.71% | +2.70% | -11.06% | 15.19% | 36 | 0 |
| F5_A_cloud_vp | 56 | 167 | 51 | +7.16% | +3.80% | -7.65% | 11.29% | 9 | 0 |
| F6_breakout_cloud | 56 | 192 | 19 | +9.53% | +1.19% | -8.80% | 10.83% | 31 | 84 |
| F6_breakout_cloud_vp | 56 | 195 | 16 | +3.77% | +1.26% | -6.13% | 6.31% | 7 | 84 |
| F6_trend_cloud | 56 | 191 | 20 | +9.54% | +1.23% | -9.50% | 11.45% | 36 | 84 |
| F6_trend_cloud_vp | 56 | 195 | 16 | +3.82% | +1.23% | -6.60% | 7.01% | 11 | 84 |

## Matched first RSI+candle cohorts — 2024-2025 (40/80/120 bars)
| evaluation bars | profile | F6 stage3 | matched cases | avg F5 | avg F6 | mean difference | F6 strictly better | F6 stage3 fills |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 40 | cloud | breakout | 122 | +1.55% | +1.32% | -0.23% | 9.0% | 19 |
| 40 | cloud | trend | 122 | +1.55% | +1.42% | -0.13% | 9.8% | 25 |
| 40 | cloud_vp | breakout | 122 | +0.89% | +0.74% | -0.15% | 6.6% | 5 |
| 40 | cloud_vp | trend | 122 | +0.89% | +0.82% | -0.08% | 8.2% | 8 |
| 80 | cloud | breakout | 98 | +1.61% | +1.44% | -0.17% | 20.4% | 17 |
| 80 | cloud | trend | 98 | +1.61% | +1.55% | -0.05% | 20.4% | 22 |
| 80 | cloud_vp | breakout | 98 | +1.06% | +1.03% | -0.03% | 17.3% | 3 |
| 80 | cloud_vp | trend | 98 | +1.06% | +0.97% | -0.09% | 17.3% | 6 |
| 120 | cloud | breakout | 82 | +2.11% | +2.28% | +0.17% | 22.0% | 17 |
| 120 | cloud | trend | 82 | +2.11% | +1.89% | -0.22% | 20.7% | 20 |
| 120 | cloud_vp | breakout | 82 | +1.50% | +1.16% | -0.35% | 19.5% | 3 |
| 120 | cloud_vp | trend | 82 | +1.50% | +1.01% | -0.49% | 18.3% | 5 |

## Price and coverage failures

- SPCX: Only 92 valid daily bars; at least 120 expected
