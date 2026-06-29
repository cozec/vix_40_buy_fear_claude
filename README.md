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
src/       backtest.py · download_data.py · plot_trades.py · dashboard.py
results/   trades + performance summary CSVs
plots/     equity_curve.png · trade_NN.png
logs/      run output
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas numpy matplotlib yfinance flask

python src/download_data.py   # refresh TQQQ/VIX/S&P from Yahoo Finance
python src/backtest.py        # run backtest -> results/ + summary
python src/plot_trades.py     # per-trade candlestick charts -> plots/
```

See [summary.md](summary.md) for results.

## Live dashboard

A local, interactive monitoring page (price + VIX + RSI triggers, current
position status, zoomable charts with 3M/6M/1Y/3Y/Max buttons):

```bash
python src/dashboard.py        # then open http://localhost:8000
# PORT=8050 python src/dashboard.py   # macOS reserves 5000 for AirPlay
```

Data is read fresh on each page load, so re-running `download_data.py` then
refreshing the browser updates the view.
