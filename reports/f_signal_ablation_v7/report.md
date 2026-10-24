# F7: factor-by-factor signal ablation — confirmatory checks, not optimization

OHLCV data through 2026-10-22. Current Nasdaq market-cap rank frozen at 2026-10-24, NOT point-in-time membership.
2024–25 has been repeatedly evaluated in prior F3–F6 experiments, so this is NOT an untouched holdout.
Fundamental point-in-time and 5-minute signals are NOT tested. No tuning based on 2026 prices.
Parameters are pre-specified: 1:2:6 staged entries, RSI 14, MACD 12/26/9, max 20 bar stage gap, VP 120 bars/32 bins, fees 0.1% each side.

## Factorial design: 24 strategies, no cherry-picking
- Candle filter off/on: base RSI rebound versus same plus close > open on RSI signal bar.
- Ichimoku stage 3: base cloud rebound (F5), strict Tenkan/Kijun + Chikou + same-day cloud breakout, trend confirmation within prior 20 bars (F6).
- RSI70 take profit off/on: when on, RSI crosses upward through 70 and sells LOT1 only; regular RSI<=30 sells LOT1, MACD death sells LOT2, cloud bottom failure sells LOT3.
- Volume profile off/on: profile = cloud/cloud_vp, with VP conditions identical to F5/F6.
- ALL signals close[t] -> open[t+1]. Cash earns zero, missing trades count as 0 return, open positions marked at phase end (NOT forced sold).
- Each symbol gets a separate self-financing account. Means across symbols are NOT pooled/pooled-balance portfolio returns.
- Matched RSI cohorts selected from BASE RSI events without looking at candle or returns; candle-filtered models may make no trade at that anchor. Same 40/80/120 bar evaluation date per comparison.
- The 40/80/120 cohorts overlap ACROSS horizons. Do not treat them as independent samples.
- 95% bootstrap intervals resample symbols (not individual trades), but cross-symbol market correlation means intervals may still be too narrow.
- Statistical significance is NOT established by exploratory intervals across 24 alternatives; multiple-comparison and previous-data-snooping risks remain.
- No corporate-action, slippage, FX, dividend and tax realism; 0.1% flat commission only.

## 2024–2025 whole-account comparison (same capital initialised independently for each symbol)
| variant | tickers | mean cumulative | median cumulative | avg MDD | avg exposure | 3rd buys | open positions |
|---|---:|---:|---:|---:|---:|---:|---:|
| F7_C0_Ibase_T0_cloud | 56 | +11.71% | +2.70% | -11.06% | 15.19% | 36 | 51 |
| F7_C0_Ibase_T1_cloud | 56 | +8.36% | +1.27% | -9.66% | 10.52% | 33 | 20 |
| F7_C0_Istrict_T0_cloud | 56 | +19.23% | +2.96% | -11.21% | 17.41% | 42 | 51 |
| F7_C0_Istrict_T1_cloud | 56 | +12.26% | +1.62% | -9.11% | 11.57% | 33 | 20 |
| F7_C0_Itrend_T0_cloud | 56 | +19.61% | +2.96% | -11.65% | 18.01% | 46 | 51 |
| F7_C0_Itrend_T1_cloud | 56 | +12.27% | +1.47% | -9.81% | 12.19% | 38 | 21 |
| F7_C1_Ibase_T0_cloud | 56 | +8.36% | +2.12% | -10.44% | 14.09% | 33 | 49 |
| F7_C1_Ibase_T1_cloud | 56 | +5.48% | +0.33% | -9.07% | 9.65% | 30 | 19 |
| F7_C1_Istrict_T0_cloud | 56 | +16.04% | +2.45% | -10.76% | 16.44% | 40 | 49 |
| F7_C1_Istrict_T1_cloud | 56 | +9.53% | +1.19% | -8.80% | 10.83% | 31 | 19 |
| F7_C1_Itrend_T0_cloud | 56 | +16.42% | +2.45% | -11.20% | 17.04% | 44 | 49 |
| F7_C1_Itrend_T1_cloud | 56 | +9.54% | +1.23% | -9.50% | 11.45% | 36 | 20 |
| F7_C0_Ibase_T0_cloud_vp | 56 | +7.16% | +3.80% | -7.65% | 11.29% | 9 | 51 |
| F7_C0_Ibase_T1_cloud_vp | 56 | +3.98% | +1.27% | -6.50% | 6.80% | 9 | 16 |
| F7_C0_Istrict_T0_cloud_vp | 56 | +7.28% | +4.46% | -7.54% | 11.36% | 8 | 51 |
| F7_C0_Istrict_T1_cloud_vp | 56 | +4.04% | +1.40% | -6.29% | 6.64% | 7 | 16 |
| F7_C0_Itrend_T0_cloud_vp | 56 | +7.33% | +3.84% | -7.99% | 12.05% | 12 | 51 |
| F7_C0_Itrend_T1_cloud_vp | 56 | +4.08% | +1.27% | -6.76% | 7.34% | 11 | 16 |
| F7_C1_Ibase_T0_cloud_vp | 56 | +6.35% | +2.88% | -7.41% | 10.68% | 9 | 49 |
| F7_C1_Ibase_T1_cloud_vp | 56 | +3.72% | +1.04% | -6.34% | 6.47% | 9 | 16 |
| F7_C1_Istrict_T0_cloud_vp | 56 | +6.47% | +3.55% | -7.31% | 10.75% | 8 | 49 |
| F7_C1_Istrict_T1_cloud_vp | 56 | +3.77% | +1.26% | -6.13% | 6.31% | 7 | 16 |
| F7_C1_Itrend_T0_cloud_vp | 56 | +6.52% | +2.86% | -7.76% | 11.44% | 12 | 49 |
| F7_C1_Itrend_T1_cloud_vp | 56 | +3.82% | +1.23% | -6.60% | 7.01% | 11 | 16 |

## Main effects (average across other factors, 2024–2025)
Positive MDD effect means less negative drawdown; positive exposure effect means more time invested.
| experimental switch | symbols | mean return difference (pp) | cluster-bootstrap 95% interval (pp) | mean MDD difference (pp) | mean exposure difference (pp) | positive symbols |
|---|---:|---:|---:|---:|---:|---:|
| candle | 56 | -1.77 | [-5.39, +0.15] | +0.33 | -0.69 | 11 |
| RSI70 | 56 | -4.30 | [-7.99, -1.48] | +1.45 | -4.92 | 20 |
| ichi_strict | 56 | +2.94 | [+0.20, +6.87] | +0.12 | +0.83 | 11 |
| ichi_trend | 56 | +3.06 | [+0.43, +7.00] | -0.39 | +1.48 | 12 |

## Matched-cohort control (representative published variants)
F7_C0_Ibase_T0 is an exact F5-A control; F7_C1_Istrict_T1 and F7_C1_Itrend_T1 are F6 controls.
| profile | horizon | variant | pairs | baseline beat/tie/lose | equal-symbol mean difference (pp) | 95% interval (pp) | skipped anchor |
|---|---:|---|---:|---:|---:|---:|---:|
| cloud | 40 | F7_C0_Ibase_T0_cloud | 125 | 0/125/0 | +0.00 | [+0.00, +0.00] | 0 |
| cloud | 40 | F7_C0_Ibase_T1_cloud | 125 | 8/98/19 | -0.08 | [-0.30, +0.19] | 0 |
| cloud | 40 | F7_C1_Ibase_T0_cloud | 125 | 13/108/4 | -0.28 | [-0.87, +0.12] | 17 |
| cloud | 40 | F7_C1_Istrict_T1_cloud | 125 | 24/79/22 | -0.23 | [-0.92, +0.37] | 17 |
| cloud | 40 | F7_C1_Itrend_T1_cloud | 125 | 25/78/22 | -0.28 | [-0.91, +0.29] | 17 |
| cloud | 80 | F7_C0_Ibase_T0_cloud | 100 | 0/100/0 | +0.00 | [+0.00, +0.00] | 0 |
| cloud | 80 | F7_C0_Ibase_T1_cloud | 100 | 15/65/20 | -0.07 | [-0.55, +0.51] | 0 |
| cloud | 80 | F7_C1_Ibase_T0_cloud | 100 | 10/87/3 | -0.22 | [-0.93, +0.21] | 13 |
| cloud | 80 | F7_C1_Istrict_T1_cloud | 100 | 28/54/18 | -0.20 | [-1.36, +0.78] | 13 |
| cloud | 80 | F7_C1_Itrend_T1_cloud | 100 | 28/53/19 | -0.19 | [-1.10, +0.61] | 13 |
| cloud | 120 | F7_C0_Ibase_T0_cloud | 84 | 0/84/0 | +0.00 | [+0.00, +0.00] | 0 |
| cloud | 120 | F7_C0_Ibase_T1_cloud | 84 | 14/50/20 | -0.45 | [-1.11, +0.28] | 0 |
| cloud | 120 | F7_C1_Ibase_T0_cloud | 84 | 8/73/3 | -0.68 | [-2.36, +0.22] | 11 |
| cloud | 120 | F7_C1_Istrict_T1_cloud | 84 | 25/41/18 | -0.68 | [-2.75, +0.73] | 11 |
| cloud | 120 | F7_C1_Itrend_T1_cloud | 84 | 24/41/19 | -0.90 | [-2.78, +0.45] | 11 |

## Failures and coverage
- Data downloaded: 57/58 securities
- SPCX: Only 92 valid daily bars; at least 120 expected

