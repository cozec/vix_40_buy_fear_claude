# Backtest Summary — VIX > 40 "Buy the Fear" (TQQQ)

**Window:** 2010-02-11 → 2025-12-18  ·  **Start capital:** $10,000  ·  **Trades:** 9 (100% win rate)

RSI(14) uses a **simple moving average** of gains/losses (not Wilder's smoothing).

## Performance vs Benchmarks

Ordered by final equity. Alpha/Beta measured against Buy & Hold TQQQ.

| Strategy | Final Equity | Return % | CAGR % | Max DD % | Sharpe | Alpha | Beta |
|---|---:|---:|---:|---:|---:|---:|---:|
| **VIX40 Strategy (TQQQ)** | **$3,383,336** | **33,733.4** | **44.41** | **-61.57** | **0.98** | **0.13** | **0.68** |
| Buy & Hold TQQQ | $2,491,786 | 24,817.9 | 41.65 | -81.66 | 0.88 | 0.00 | 1.00 |

### Takeaways
- With the **SMA-based RSI**, the strategy now **beats** buy-&-hold TQQQ on every axis: higher final equity (**$3.38M vs $2.49M**), higher CAGR (44.4% vs 41.7%), much smaller max drawdown (**-62% vs -82%**), and a higher Sharpe (0.98 vs 0.88) — all at a beta of 0.68 with positive alpha.
- The less-smoothed SMA RSI is **more sensitive** than Wilder's, firing on more capitulation events: trade count rose from 7 to **9**, adding the Nov-2016 and Oct-2023 entries that Wilder's RSI smoothed away.
- Every one of the 9 entries was profitable.
- **The 9-trading-day entry delay helps**: waiting ~2 weeks after the panic signal repeatedly bought lower (e.g. COVID at $5.36 vs $9.49 on the signal day).

## Trade Log (all 9 trades)

Signal Date = day the condition fired (on close). Entry Date = the close **9 trading days later**, where the position is actually bought. Trigger shows the condition and its value on the signal day.

| # | Signal Date | Entry Date | Trigger | Entry $ | Exit Date | Exit $ | Return % | Hold Days | Capital After |
|---|---|---|---|---:|---|---:|---:|---:|---:|
| 1 | 2010-05-07 | 2010-05-20 | VIX 41.0 > 40 | 0.21 | 2011-06-01 | 0.41 | +94.3 | 377 | $19,427 |
| 2 | 2011-08-05 | 2011-08-18 | RSI 28.0 < 35 | 0.28 | 2012-11-07 | 0.49 | +77.2 | 447 | $34,429 |
| 3 | 2015-08-21 | 2015-09-03 | RSI 29.4 < 35 | 1.83 | 2016-10-11 | 2.49 | +35.9 | 404 | $46,804 |
| 4 | 2016-11-04 | 2016-11-17 | RSI 30.7 < 35 | 2.48 | 2018-02-08 | 5.18 | +108.8 | 448 | $97,727 |
| 5 | 2018-10-26 | 2018-11-08 | RSI 34.9 < 35 | 6.75 | 2020-02-25 | 10.53 | +56.0 | 474 | $152,450 |
| 6 | 2020-02-28 | 2020-03-12 | VIX 40.1 > 40 | 5.36 | 2021-09-30 | 29.84 | +456.6 | 567 | $848,555 |
| 7 | 2022-05-13 | 2022-05-26 | RSI 30.6 < 35 | 14.53 | 2023-09-21 | 17.36 | +19.5 | 483 | $1,014,080 |
| 8 | 2023-10-20 | 2023-11-02 | RSI 32.6 < 35 | 17.70 | 2025-02-27 | 35.58 | +101.0 | 483 | $2,038,369 |
| 9 | 2025-03-14 | 2025-03-27 | RSI 32.0 < 35 | 31.03 | *open* 2025-12-18 | 51.51 | +66.0 | 266 | $3,383,336 |

*Trade 9 is still open at the end of the window — held 266 days (< 365-day minimum), so the exit condition cannot yet trigger; it is marked-to-market at the final close.*

### Notes on signal timing
- Most entries are **RSI-driven** under the SMA method; only the May-2010 and Mar-2020 (COVID) panics tripped the VIX>40 condition.
- The Oct-2023 entry (#8) is the signal flagged during review — SMA RSI hit 32.6, below 35, where Wilder's RSI (38.9) would have missed it.
- The ≥1-year hold + "S&P below MA100" exit keeps each position through the full recovery rather than selling early, which is the main source of the large per-trade returns on the leveraged ETF.

## Files
- `results/tqqq_vix40_trades.csv` — full trade detail
- `results/performance_summary.csv` — metrics table
- `plots/equity_curve.png` — equity curves (log scale)
