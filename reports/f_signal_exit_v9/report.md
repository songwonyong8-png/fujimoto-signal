# F9: 1:2:6 fixed BUY, three stage-3 EXIT alternatives, 200-stock ranking snapshot

OHLCV price cut-off: **2026-10-22**; market-cap snapshot from published ranking sources, not point-in-time 2024 constituents.
KOSPI market-cap top100 common equities (Korea Stock Exchange list), NASDAQ100 top100 listed share classes by weight.
Sources: https://stockanalysis.com/list/korea-stock-exchange/ ; https://www.slickcharts.com/nasdaq100 .
**Survivorship bias:** current top100 lists projected backward; NOT prospective out-of-sample.

## Frozen entry logic (identical across all A/B/C)
- 1/9: RSI(14) <=30 in preceding 5 trading days; today RSI 30..48 and close>prior close.
- 2/9: MACD(12/26/9) golden-cross after first RSI within 20 trading days, while lot1 held.
- 6/9: strict Ichimoku breakout: Tenkan>Kijun and rising Kijun; Chikou close[t]>high[t-26]; close crosses ABOVE visible cloud top at t; <=20 sessions after MACD and both lots held.
- RSI <=30 exits lot1 only; MACD death exits lot2 only; no RSI 70 profit sale, no VP condition.
- A: close below cloud BOTTOM exits lot3; B: close below cloud TOP exits lot3; C: TWO consecutive closes below cloud TOP exit lot3.
- Orders fill on next session OPEN, 0.1% fees on each buy/sell. No slippage, dividends, taxes, currency FX, stock-borrow, live liquidity simulation.
- Closed campaign win rate is based on *entire campaign* return; lot3 win rate is calculated on actually exited lot3 positions.
- OPEN_MTM campaigns mark the last known close less estimated selling fee; open lots are NOT counted as closed wins.
- Market equal-initial-weight portfolios use 1/100 allocation each; unavailable and newly listed historical names remain in cash, NOT silently replaced.
- Report periods are measured independently, NOT continuously carried over across phase boundaries.
- Daily source is yfinance auto_adjust=False. Historical splits and corporate actions may influence results. KOSPI and US trading calendars are independent.

## Per-market account results (per-symbol mean/median vs equal-weight portfolio)
| Phase | Market | Exit model | Coverage | Avg ticker return | Median ticker return | Avg ticker MDD | 3rd buys | Campaign win | Portfolio return | Portfolio MDD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development_2021_2023 | KOSPI | A | 95/100 | +2.90% | -1.96% | -14.14% | 102 | +20.19% | +2.76% | -4.29% |
| development_2021_2023 | KOSPI | B | 95/100 | +2.90% | -1.43% | -12.54% | 102 | +20.33% | +2.76% | -4.11% |
| development_2021_2023 | KOSPI | C | 95/100 | +3.56% | -1.43% | -13.18% | 102 | +20.89% | +3.38% | -3.83% |
| development_2021_2023 | NASDAQ100 | A | 93/100 | +3.93% | +2.64% | -12.51% | 75 | +22.31% | +3.66% | -6.32% |
| development_2021_2023 | NASDAQ100 | B | 93/100 | +3.94% | +2.82% | -11.13% | 75 | +24.06% | +3.66% | -5.73% |
| development_2021_2023 | NASDAQ100 | C | 93/100 | +3.74% | +2.64% | -11.60% | 75 | +22.86% | +3.48% | -5.92% |
| validation_2024_2025 | KOSPI | A | 100/100 | +17.04% | +6.21% | -9.65% | 40 | +22.61% | +17.04% | -2.39% |
| validation_2024_2025 | KOSPI | B | 100/100 | +14.88% | +6.24% | -8.67% | 40 | +23.04% | +14.88% | -2.19% |
| validation_2024_2025 | KOSPI | C | 100/100 | +15.18% | +6.17% | -9.04% | 40 | +22.61% | +15.18% | -2.30% |
| validation_2024_2025 | NASDAQ100 | A | 97/100 | +13.62% | +0.52% | -11.09% | 70 | +25.57% | +13.21% | -5.93% |
| validation_2024_2025 | NASDAQ100 | B | 97/100 | +9.21% | +1.94% | -9.10% | 70 | +25.93% | +8.94% | -3.81% |
| validation_2024_2025 | NASDAQ100 | C | 97/100 | +9.36% | +2.28% | -9.51% | 70 | +25.36% | +9.08% | -3.83% |
| year_2024 | KOSPI | A | 98/100 | -0.40% | +0.00% | -6.11% | 15 | +15.86% | -0.39% | -2.39% |
| year_2024 | KOSPI | B | 98/100 | -0.15% | +0.00% | -5.76% | 15 | +16.55% | -0.15% | -2.19% |
| year_2024 | KOSPI | C | 98/100 | -0.16% | +0.00% | -5.89% | 15 | +15.86% | -0.16% | -2.30% |
| year_2024 | NASDAQ100 | A | 95/100 | +6.07% | +0.00% | -4.31% | 22 | +18.55% | +5.76% | -1.30% |
| year_2024 | NASDAQ100 | B | 95/100 | +1.82% | +0.00% | -3.55% | 22 | +19.35% | +1.73% | -0.75% |
| year_2024 | NASDAQ100 | C | 95/100 | +1.93% | +0.00% | -3.69% | 22 | +18.55% | +1.83% | -0.76% |
| year_2025 | KOSPI | A | 100/100 | +14.86% | +4.04% | -5.29% | 25 | +15.91% | +14.86% | -1.98% |
| year_2025 | KOSPI | B | 100/100 | +12.36% | +3.21% | -4.56% | 25 | +15.91% | +12.36% | -1.49% |
| year_2025 | KOSPI | C | 100/100 | +12.65% | +3.21% | -4.87% | 25 | +15.91% | +12.65% | -1.72% |
| year_2025 | NASDAQ100 | A | 97/100 | +9.78% | +0.04% | -7.88% | 44 | +18.56% | +9.49% | -2.64% |
| year_2025 | NASDAQ100 | B | 97/100 | +8.08% | +0.37% | -6.86% | 44 | +18.82% | +7.84% | -2.61% |
| year_2025 | NASDAQ100 | C | 97/100 | +8.18% | +0.00% | -7.24% | 44 | +18.24% | +7.93% | -2.58% |
| exploratory_2026 | KOSPI | A | 100/100 | -0.98% | -0.06% | -4.05% | 2 | +7.69% | -0.98% | -2.27% |
| exploratory_2026 | KOSPI | B | 100/100 | -1.04% | -0.06% | -4.05% | 2 | +7.69% | -1.04% | -2.33% |
| exploratory_2026 | KOSPI | C | 100/100 | -1.05% | -0.06% | -4.05% | 2 | +7.69% | -1.05% | -2.33% |
| exploratory_2026 | NASDAQ100 | A | 97/100 | +1.67% | +0.12% | -4.62% | 19 | +18.12% | +1.62% | -0.97% |
| exploratory_2026 | NASDAQ100 | B | 97/100 | +2.01% | +0.15% | -4.13% | 19 | +20.29% | +1.95% | -0.88% |
| exploratory_2026 | NASDAQ100 | C | 97/100 | +1.94% | +0.12% | -4.25% | 19 | +19.57% | +1.89% | -0.94% |

## Remove top 5 performers on SAME remaining names, by market (2024-2025)
| Market | Candidate | Ranking by | Remaining | Mean strategy advantage | Better / tie / worse |
|---|---|---|---:|---:|---:|
| KOSPI | B | baseline | 95 | -0.33 pp | 18/69/8 |
| KOSPI | B | candidate | 95 | -1.79 pp | 17/69/9 |
| KOSPI | C | baseline | 95 | -0.22 pp | 18/68/9 |
| KOSPI | C | candidate | 95 | -1.58 pp | 17/68/10 |
| NASDAQ100 | B | baseline | 92 | -0.54 pp | 25/54/13 |
| NASDAQ100 | B | candidate | 92 | -2.42 pp | 24/53/15 |
| NASDAQ100 | C | baseline | 92 | -0.31 pp | 27/50/15 |
| NASDAQ100 | C | candidate | 92 | -2.23 pp | 26/49/17 |

## Matching actual stage-3 entries, 2024-2025
Matched only when the exact same ticker/date entered lot3 AND all models closed it before the window end.
- KOSPI: 34 matched exits; mean lot3 net A +2.46%; B +3.33%; C +3.74%.
- NASDAQ100: 61 matched exits; mean lot3 net A +6.40%; B +0.83%; C +1.34%.

## Data coverage and errors
- Failures/warnings: 3.
- NASDAQ100/SPCX: Only 92 valid daily bars; at least 120 expected
- NASDAQ100/WBD: Yahoo Finance returned no OHLCV rows
- NASDAQ100/HONA: Only 91 valid daily bars; at least 120 expected
- See data_audit.csv and errors.csv for ALL names and coverage issues.
- Preferred shares, ETF share classes and Nasdaq-listed non-index stocks are not included: the selection definition is in the locked universe CSV.
- 2024-25 has been explored repeatedly in earlier F3-F8; metrics are retrospective research, not fresh unbiased validation.
- One symbol can contribute multiple campaigns and lots; correlation across stock/industry exists.

## Output files
- universe_snapshot.csv, data_audit.csv, account_summary.csv, campaign_trades.csv, lot_trades.csv, fills.csv
- market_summary.csv, market_portfolio.csv, market_daily_equity.csv, outlier_sensitivity.csv, matched_stage3.csv, errors.csv, run_metadata.json.

