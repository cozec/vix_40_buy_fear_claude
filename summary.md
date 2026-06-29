# Backtest Summary — VIX > 40 "Buy the Fear" (TQQQ)

**Window:** 2010-02-11 → 2026-06-26  ·  **Start capital:** $10,000  ·  **Trades:** 10 (100% win rate)

Data refreshed from Yahoo Finance (split/dividend-adjusted) through 2026-06-26. RSI(14) uses a **simple moving average** of gains/losses (not Wilder's smoothing).

## Performance vs Benchmarks

Ordered by final equity. Alpha/Beta measured against Buy & Hold TQQQ.

| Strategy | Final Equity | Return % | CAGR % | Max DD % | Sharpe | Alpha | Beta |
|---|---:|---:|---:|---:|---:|---:|---:|
| **VIX40 Strategy (TQQQ)** | **$3,623,260** | **36,132.6** | **43.33** | **-61.57** | **0.97** | **0.11** | **0.69** |
| Buy & Hold TQQQ | $3,485,958 | 34,759.6 | 42.99 | -81.66 | 0.90 | -0.00 | 1.00 |

### Takeaways
- With the **SMA-based RSI**, the strategy still **beats** buy-&-hold TQQQ on every axis: higher final equity (**$3.62M vs $3.49M**), higher CAGR (43.3% vs 43.0%), much smaller max drawdown (**-62% vs -82%**), and a higher Sharpe (0.97 vs 0.90) — all at a beta of 0.69 with positive alpha. The equity edge narrowed as TQQQ rallied hard into 2026, but the **risk-adjusted edge is intact**.
- The less-smoothed SMA RSI is **more sensitive** than Wilder's, firing on more capitulation events.
- Every one of the 10 entries was profitable.
- **The 9-trading-day entry delay helps**: waiting ~2 weeks after the panic signal repeatedly bought lower (e.g. COVID at $5.34 vs $9.49 on the signal day).

## Trade Log (all 10 trades)

Signal Date = day the condition fired (on close). Entry Date = the close **9 trading days later**, where the position is actually bought. Trigger shows the condition and its value on the signal day.

| # | Signal Date | Entry Date | Trigger | Entry $ | Exit Date | Exit $ | Return % | Hold Days | Capital After |
|---|---|---|---|---:|---|---:|---:|---:|---:|
| 1 | 2010-05-07 | 2010-05-20 | VIX 41.0 > 40 | 0.21 | 2011-06-01 | 0.41 | +94.3 | 377 | $19,427 |
| 2 | 2011-08-05 | 2011-08-18 | RSI 28.0 < 35 | 0.28 | 2012-11-07 | 0.49 | +77.2 | 447 | $34,429 |
| 3 | 2015-08-21 | 2015-09-03 | RSI 29.4 < 35 | 1.82 | 2016-10-11 | 2.48 | +35.9 | 404 | $46,804 |
| 4 | 2016-11-04 | 2016-11-17 | RSI 30.7 < 35 | 2.47 | 2018-02-08 | 5.16 | +108.8 | 448 | $97,727 |
| 5 | 2018-10-26 | 2018-11-08 | RSI 34.9 < 35 | 6.73 | 2020-02-25 | 10.50 | +56.0 | 474 | $152,450 |
| 6 | 2020-02-28 | 2020-03-12 | VIX 40.1 > 40 | 5.34 | 2021-09-30 | 29.75 | +456.6 | 567 | $848,556 |
| 7 | 2022-05-13 | 2022-05-26 | RSI 30.6 < 35 | 14.48 | 2023-09-21 | 17.30 | +19.5 | 483 | $1,014,081 |
| 8 | 2023-10-20 | 2023-11-02 | RSI 32.6 < 35 | 17.64 | 2025-02-27 | 35.47 | +101.0 | 483 | $2,038,371 |
| 9 | 2025-03-14 | 2025-03-27 | RSI 32.0 < 35 | 30.93 | 2026-03-27 | 38.78 | +25.4 | 365 | $2,555,399 |
| 10 | 2026-03-30 | 2026-04-13 | RSI 28.2 < 35 | 50.66 | *open* 2026-06-26 | 71.83 | +41.8 | 74 | $3,623,260 |

*Trade 10 is still open at the end of the window — held 74 days (< 365-day minimum), so the exit condition cannot yet trigger; it is marked-to-market at the final close.*

### Notes on signal timing
- Most entries are **RSI-driven** under the SMA method; only the May-2010 and Mar-2020 (COVID) panics tripped the VIX>40 condition.
- The refreshed data **closed trade 9**: held exactly 365 days from the Mar-2025 entry, then S&P closed below MA100 on 2026-03-27, triggering the exit (+25.4%).
- A **new trade 10** opened on the late-Mar-2026 capitulation (SMA RSI 28.2), entering 2026-04-13 at $50.66; up +41.8% and still held at the data cutoff.
- The ≥1-year hold + "S&P below MA100" exit keeps each position through the full recovery rather than selling early, which is the main source of the large per-trade returns on the leveraged ETF.

## Files
- `results/tqqq_vix40_trades.csv` — full trade detail
- `results/performance_summary.csv` — metrics table
- `plots/equity_curve.png` — equity curves (log scale)
