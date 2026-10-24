# F8: top-winner exclusion and indicator win rates (signal effectiveness)

OHLCV cut-off 2026-10-22, 2026 top50 survivor universe. Not independent holdout.
## Definitions / limitations
- Each F7 strategy uses RSI→MACD→Ichimoku sequence and staged weights 1:2:6.
- Outlier exclusion applies THE SAME tickers to F5 baseline and each F7 alternative.
- Exclusions are determined by baseline F5 profits OR candidate profits, separately.
- Rank top 1/3/5/10 of 2024-25 account returns; exclude them from all variants before calculating paired mean difference.
- Both winner-based exclusions are outcome-dependent diagnostics, NOT investable filters knowable at entry.
- Standalone indicator win rate: at day t signal close, buy next open, exit after 5/10/20/40 full bars at next open. Fee 0.10% each direction.
- Same-period unconditional buy-and-hold days provide a market-direction baseline. A high raw win rate alone does not prove forecasting skill.
- Indicator event samples are filtered to non-overlapping spans per horizon; successive horizons/indicators still overlap. Wilson intervals assume iid, which is imperfect.
- Indicator exit round trips are a DIFFERENT experiment: RSI exits at <=30 or upward 70 crossover; MACD exits at death cross; Ichimoku exits below cloud bottom. Unclosed trades excluded from closed win rates.
- Conditional confirmation event sample counts may be too small to interpret. Pooled rate includes all eligible signals; equal-ticker comparison requires >=5 signals per security.
- 2024-25 has already been extensively inspected. Nasdaq selection anchored to 2026, survivorship bias, cross-stock dependence, no tax/slippage/corporate action/dividend/FX realism.

## F7 top-winner sensitivity: 2024-2025
| F7 candidate | Winner ranking | Removed | Remaining | Mean return advantage (pp) | Median advantage (pp) | better/tie/worse |
|---|---|---:|---:|---:|---:|---|
| F7_C0_Istrict_T0_cloud | baseline_f5 | 0 | 56 | +7.52 | +0.00 | 10/40/6 |
| F7_C0_Istrict_T0_cloud | baseline_f5 | 1 | 55 | +7.66 | +0.00 | 10/39/6 |
| F7_C0_Istrict_T0_cloud | baseline_f5 | 3 | 53 | +7.95 | +0.00 | 10/37/6 |
| F7_C0_Istrict_T0_cloud | baseline_f5 | 5 | 51 | +5.83 | +0.00 | 9/37/5 |
| F7_C0_Istrict_T0_cloud | baseline_f5 | 10 | 46 | +1.63 | +0.00 | 7/34/5 |
| F7_C0_Istrict_T0_cloud | candidate | 0 | 56 | +7.52 | +0.00 | 10/40/6 |
| F7_C0_Istrict_T0_cloud | candidate | 1 | 55 | +4.62 | +0.00 | 9/40/6 |
| F7_C0_Istrict_T0_cloud | candidate | 3 | 53 | +2.47 | +0.00 | 8/39/6 |
| F7_C0_Istrict_T0_cloud | candidate | 5 | 51 | +0.62 | +0.00 | 7/38/6 |
| F7_C0_Istrict_T0_cloud | candidate | 10 | 46 | -0.23 | +0.00 | 6/34/6 |
| F7_C0_Itrend_T0_cloud | baseline_f5 | 0 | 56 | +7.90 | +0.00 | 11/39/6 |
| F7_C0_Itrend_T0_cloud | baseline_f5 | 1 | 55 | +8.05 | +0.00 | 11/38/6 |
| F7_C0_Itrend_T0_cloud | baseline_f5 | 3 | 53 | +8.35 | +0.00 | 11/36/6 |
| F7_C0_Itrend_T0_cloud | baseline_f5 | 5 | 51 | +5.66 | +0.00 | 10/36/5 |
| F7_C0_Itrend_T0_cloud | baseline_f5 | 10 | 46 | +1.43 | +0.00 | 8/33/5 |
| F7_C0_Itrend_T0_cloud | candidate | 0 | 56 | +7.90 | +0.00 | 11/39/6 |
| F7_C0_Itrend_T0_cloud | candidate | 1 | 55 | +5.01 | +0.00 | 10/39/6 |
| F7_C0_Itrend_T0_cloud | candidate | 3 | 53 | +2.87 | +0.00 | 9/38/6 |
| F7_C0_Itrend_T0_cloud | candidate | 5 | 51 | +1.04 | +0.00 | 8/37/6 |
| F7_C0_Itrend_T0_cloud | candidate | 10 | 46 | +0.51 | +0.00 | 7/34/5 |

## Ranking robustness: mean/median/winsor/trim of matched excess return
| Candidate | n | mean (pp) | median (pp) | winsor 10% (pp) | trimmed 10% (pp) | better/tie/worse |
|---|---:|---:|---:|---:|---:|---|
| F7_C0_Istrict_T0_cloud | 56 | +7.52 | +0.00 | +1.30 | +0.66 | 10/40/6 |
| F7_C0_Itrend_T0_cloud | 56 | +7.90 | +0.00 | +0.98 | +0.46 | 11/39/6 |

## Raw indicator signal hit rate, 20-bar horizon
| Signal | Any-signal tickers | Tickers>=5 | Nonoverlap events | Pooled win | Equal-ticker win (n>=5) | Equal-ticker mean trade (n>=5) | Unconditional win (n>=5) |
|---|---:|---:|---:|---:|---:|---:|---:|
| RSI_REBOUND | 54 | 10 | 165 | 59.4% | 60.7% | +2.27% | 51.1% |
| MACD_GOLDEN | 56 | 55 | 729 | 54.5% | 54.4% | +1.77% | 58.0% |
| ICHI_CLOUD_SUPPORT | 56 | 51 | 410 | 57.6% | 59.0% | +1.55% | 57.6% |
| ICHI_STRICT | 55 | 2 | 144 | 66.7% | 60.0% | -3.00% | 51.0% |
| ICHI_TREND | 56 | 43 | 299 | 62.9% | 61.3% | +1.92% | 58.0% |
| MACD_AFTER_RSI | 54 | 4 | 135 | 49.6% | 55.0% | +2.01% | 45.4% |
| ICHI_AFTER_RSI_MACD | 31 | 0 | 36 | 83.3% | n/a | n/a | n/a |

## Detailed ticker-by-ticker indicator effectiveness
See indicator_stock_matrix_20d.csv for RSI/MACD/cloud side-by-side 20-day win rates, net returns, sample counts and win-rate lift.
Sample size labels: NO SIGNAL, 1-9 SPARSE or 10+ EVENTS. Even 10 signals is not enough to prove a forecasting edge.

## Indicator-defined round trips (different from fixed-horizon signal success)
| Signal | Completed trades | Open MTM | Pooled win | Mean per closed trade |
|---|---:|---:|---:|---:|
| RSI_REBOUND | 228 | 14 | 42.5% | +4.15% |
| MACD_GOLDEN | 1130 | 30 | 40.6% | +1.34% |
| ICHI_CLOUD_SUPPORT | 335 | 31 | 23.0% | -0.62% |
| ICHI_STRICT | 128 | 23 | 28.9% | +2.34% |

## Data failures
- Downloaded 57/58 symbols
- SPCX: Only 92 valid daily bars; at least 120 expected

