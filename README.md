# VIX > 40 "Buy the Fear" — TQQQ Backtest

Systematic strategy that buys leveraged exposure (TQQQ) during extreme market
panic and holds through the recovery.

## Strategy

| | Rule |
|---|---|
| **Signal** | Fire on the day **VIX close > 40** OR **S&P 500 weekly RSI(14) < 35** |
| **Entry**  | Buy TQQQ at the **close 9 trading days after** the signal |
| **Exit**   | Hold **≥ 1 year** from entry, then exit at the **close** of the first day **S&P 500 close < MA100** |
| **Sizing** | Full capital each trade, compounded. One position at a time. |

## Assumptions

- Signals evaluated on the daily close; entry fills at the close **9 trading days** later, exit at the trigger-day close (no look-ahead).
- Weekly RSI(14) uses a **simple moving average** of gains/losses (not Wilder's exponential smoothing).
- Start capital **$10,000**.
- Tradable window bounded by TQQQ & VIX data availability: **2010-02-11 → 2026-06-26**.
- Signals firing while already invested are ignored.
- Benchmark: buy & hold TQQQ over the same window.

## Layout

```
data/      input CSVs (yfinance) — not regenerated
src/       backtest.py
results/   trades + performance summary CSVs
plots/     equity_curve.png
logs/      run output
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas numpy matplotlib
python src/backtest.py
```

See [summary.md](summary.md) for results.
