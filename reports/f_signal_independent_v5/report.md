# F v5: Independent signal-based exits versus F4 and hierarchical exits

OHLCV cutoff: 2026-10-22. Large-cap universe selected using 2026-10-24 snapshot.
Historical membership is NOT point-in-time; survivorship bias remains.

## Exact rules

- BUY1 1/9: original v3 RSI oversold rebound; BUY2 2/9: later MACD golden-cross <=20 sessions; BUY3 6/9: later cloud / cloud+VP support <=20 sessions.
- F4 baseline: ORIGINAL v4 exits, MACD death or RSI<=30 liquidates every owned lot; cloud bottom breakdown sells lot3 only.
- V5-A: sell LOT3 below cloud BOTTOM; LOT2 at MACD death-cross; LOT1 at RSI<=30. Other owned lots stay open.
- V5-B: below cloud bottom sell lot3; MACD death sell lot2 AND lot3; RSI<=30 sell all lots.
- V5-C: like V5-A, but sell lot3 when close below cloud TOP instead of bottom.
- If different exit signals occur on one bar, all applicable lots are sold at the NEXT open, stage3 first.
- No re-buy within a campaign; no entry into a later stage after any prerequisite lot has been sold.
- Every decision at today CLOSE, every fill tomorrow OPEN. Fee=0.1% each side, no slippage, FX, dividend/tax modelling.
- No fixed-day exit in v5; positions at phase end marked to close less a hypothetical 0.1% sale fee, excluded from closed-trade win-rate.
- Profits include idle cash (0% cash yield). Summary means average equal-weight per-symbol RESULTS, not a pooled investable portfolio.

## 2024-2025 whole-account strategies (different entry dates possible)
| strategy | tickers | closed | open MTM | average cumulative return | avg CAGR | avg MDD | worst closed trade | win on closed trades | avg daily exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F4_cloud_reverse | 56 | 220 | 11 | +3.3% | +1.5% | -7.1% | -28.7% | 32.3% | 5.2% |
| F5_A_cloud | 56 | 167 | 51 | +11.7% | +5.2% | -11.1% | -8.9% | 24.0% | 15.2% |
| F5_B_cloud | 56 | 171 | 51 | +7.4% | +3.5% | -8.1% | -8.9% | 25.7% | 11.1% |
| F5_C_cloud | 56 | 169 | 51 | +9.0% | +4.2% | -9.1% | -8.9% | 26.0% | 13.2% |
| F4_cloud_vp_reverse | 56 | 220 | 11 | +2.8% | +1.3% | -5.5% | -8.2% | 35.0% | 4.4% |
| F5_A_cloud_vp | 56 | 167 | 51 | +7.2% | +3.4% | -7.6% | -8.4% | 27.5% | 11.3% |
| F5_B_cloud_vp | 56 | 171 | 51 | +6.7% | +3.2% | -6.9% | -8.1% | 28.1% | 10.3% |
| F5_C_cloud_vp | 56 | 169 | 51 | +6.9% | +3.3% | -7.3% | -8.4% | 28.4% | 10.8% |

## Matched RSI-entry cohorts — common 40/80/120-bar EVALUATION only

Greedy non-overlapping eligible RSI signals: chosen without reference to any exit return.
All 4 variants start from same RSI signal on same symbol, enter at same next open,
have no other entry campaign during the window, and are marked on the same final date.
A fixed EVALUATION horizon does **not** force a sell; open lots are marked to market.
A paired cohort is one security and a fixed horizon; do NOT treat horizons as independent.
| window | entry profile | pairs | avg F4 return | avg V5-A | avg V5-B | avg V5-C | avg A-F4 difference | win A vs F4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 40 | cloud | 125 | +0.8% | +1.7% | +1.1% | +1.4% | +0.9% | 36.0% |
| 40 | cloud_vp | 125 | +0.6% | +1.0% | +0.9% | +1.0% | +0.4% | 36.0% |
| 80 | cloud | 100 | +1.1% | +2.0% | +1.5% | +2.2% | +0.9% | 30.0% |
| 80 | cloud_vp | 100 | +0.9% | +1.3% | +1.3% | +1.4% | +0.4% | 30.0% |
| 120 | cloud | 84 | +1.1% | +3.2% | +1.8% | +2.8% | +2.1% | 29.8% |
| 120 | cloud_vp | 84 | +1.0% | +1.9% | +1.7% | +1.8% | +0.9% | 29.8% |

## Price/data failures

- SPCX: Only 92 valid daily bars; at least 120 expected

