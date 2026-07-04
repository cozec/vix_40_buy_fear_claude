"""
Phase 1 / Step 1 — Out-of-sample validation (IMPROVEMENT_PLAN.md).

Question: is the "buy the fear" edge real, or an artifact of the post-2010 tech
bull? We run the SAME entry/exit logic on the long S&P 500 history (1990->2026):

  Signal : S&P 500 weekly RSI(14) < 35   (VIX leg dropped — VIX only exists from
           2010, so the long test relies on the RSI leg alone).
  Entry  : buy at the close 9 trading days after the signal.
  Exit   : hold >= 1 year, then exit on the first S&P close < MA100.

Traded instruments:
  * spx_1x  — the S&P 500 index itself (leverage 1x).
  * spx_3x  — synthetic 3x daily-rebalanced S&P (3 x daily return - 1%/yr drag),
              a proxy for how a leveraged ETF would have behaved.

Signal/trend indicators are always computed on the 1x index. We report win rate
and CAGR for 1990-2010 and 2010-2026 SEPARATELY, plus a per-trade return
histogram, and append the variants to results/variants.csv.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backtest import (
    load_yf, load_index, build_signals, run_backtest, metrics, buy_hold_equity,
    DATA, RESULTS, PLOTS, START_CAPITAL,
)

# Start at 1970 so the weekly-RSI + 1yr-hold logic yields >= 30 trades (the
# statistical bar); the plan's 1990 start gives only 19. Regime split at 2010.
START = "1970-01-01"
SPLIT = pd.Timestamp("2010-01-01")   # regime boundary: pre-2010 vs post-2010
LEV = 3.0
DRAG = 0.01                          # ~1%/yr fee/decay drag for the 3x proxy


def period_cagr(equity, lo, hi):
    """CAGR of the equity curve restricted to [lo, hi)."""
    seg = equity[(equity.index >= lo) & (equity.index < hi)]
    if len(seg) < 2:
        return np.nan
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    return ((seg.iloc[-1] / seg.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else np.nan


def win_rate(trades, lo=None, hi=None):
    """Win rate over trades whose Entry_Date is in [lo, hi)."""
    t = trades
    if lo is not None:
        t = t[t["Entry_Date"] >= lo]
    if hi is not None:
        t = t[t["Entry_Date"] < hi]
    if len(t) == 0:
        return np.nan, 0
    return (t["Return_%"] > 0).mean() * 100, len(t)


def summarize(label, trades, equity):
    """Print and return a metrics dict split across the two regimes."""
    m = metrics(equity)
    wr_all, n_all = win_rate(trades)
    wr_early, n_early = win_rate(trades, hi=SPLIT)
    wr_late, n_late = win_rate(trades, lo=SPLIT)
    row = {
        "variant": label,
        "start": equity.index[0].date(),
        "end": equity.index[-1].date(),
        "trades": len(trades),
        "win_rate_%": round(wr_all, 1),
        "final_equity": round(m["Final Equity"], 2),
        "CAGR_%": round(m["CAGR %"], 2),
        "MaxDD_%": round(m["Max DD %"], 2),
        "Sharpe": round(m["Sharpe"], 2),
        "trades_pre2010": n_early,
        "win_pre2010_%": round(wr_early, 1) if n_early else np.nan,
        "CAGR_pre2010_%": round(period_cagr(equity, equity.index[0], SPLIT), 2),
        "trades_post2010": n_late,
        "win_post2010_%": round(wr_late, 1) if n_late else np.nan,
        "CAGR_post2010_%": round(period_cagr(equity, SPLIT, equity.index[-1] + pd.Timedelta(days=1)), 2),
    }
    print(f"\n=== {label} ===  {row['start']} -> {row['end']}")
    print(f"  trades: {row['trades']}  win: {row['win_rate_%']}%  "
          f"CAGR: {row['CAGR_%']}%  MaxDD: {row['MaxDD_%']}%  Sharpe: {row['Sharpe']}")
    print(f"  pre-2010:  {n_early} trades, win {row['win_pre2010_%']}%, CAGR {row['CAGR_pre2010_%']}%")
    print(f"  post-2010: {n_late} trades, win {row['win_post2010_%']}%, CAGR {row['CAGR_post2010_%']}%")
    return row


def main():
    spx = load_index(os.path.join(DATA, "sp500_index_data.csv"))
    spx = spx[spx.index >= START]
    # Traded frame needs Open/Close; the index has both.
    trade = spx[["Open", "Close"]].copy()

    # Same RSI<35 / MA100 logic, VIX disabled (vix=None).
    df = build_signals(trade, spx, vix=None)

    trades_1x, eq_1x = run_backtest(df, leverage=1.0, annual_drag=0.0)
    trades_3x, eq_3x = run_backtest(df, leverage=LEV, annual_drag=DRAG)

    row_1x = summarize("oos_spx_1x", trades_1x, eq_1x)
    row_3x = summarize(f"oos_spx_{LEV:.0f}x", trades_3x, eq_3x)

    os.makedirs(RESULTS, exist_ok=True)
    trades_1x.to_csv(os.path.join(RESULTS, "oos_spx_1x_trades.csv"), index=False)
    trades_3x.to_csv(os.path.join(RESULTS, "oos_spx_3x_trades.csv"), index=False)

    # --- variants.csv: baseline (from performance_summary) + the two OOS rows ---
    baseline = {
        "variant": "baseline_tqqq_2010",
        "start": pd.Timestamp("2010-02-11").date(),
        "end": df.index[-1].date() if False else pd.Timestamp("2026-06-26").date(),
        "trades": 10, "win_rate_%": 100.0,
        "final_equity": 3623259.51, "CAGR_%": 43.33, "MaxDD_%": -61.57, "Sharpe": 0.97,
        "trades_pre2010": 0, "win_pre2010_%": np.nan, "CAGR_pre2010_%": np.nan,
        "trades_post2010": 10, "win_post2010_%": 100.0, "CAGR_post2010_%": 43.33,
    }
    variants = pd.DataFrame([baseline, row_1x, row_3x])
    variants.to_csv(os.path.join(RESULTS, "variants.csv"), index=False)
    print(f"\nWrote {os.path.join(RESULTS, 'variants.csv')}")

    # --- Per-trade return histogram (long sample, 1x) ---
    start_yr, end_yr = eq_1x.index[0].year, eq_1x.index[-1].year
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, (lbl, tr) in zip(axes, [("S&P 1x", trades_1x), (f"S&P {LEV:.0f}x", trades_3x)]):
        early = tr[tr["Entry_Date"] < SPLIT]["Return_%"]
        late = tr[tr["Entry_Date"] >= SPLIT]["Return_%"]
        bins = np.linspace(min(tr["Return_%"].min(), -50), tr["Return_%"].max() + 10, 25)
        ax.hist([early, late], bins=bins, stacked=True,
                label=[f"pre-2010 (n={len(early)})", f"post-2010 (n={len(late)})"],
                color=["#d9534f", "#0275d8"])
        ax.axvline(0, color="k", lw=0.8)
        ax.set_title(f"Per-trade return — {lbl}")
        ax.set_xlabel("Return %")
        ax.set_ylabel("Trades")
        ax.legend()
        ax.grid(True, alpha=0.25)
    fig.suptitle(f"Out-of-sample per-trade returns (RSI<35 buy-the-fear, S&P {start_yr}-{end_yr})")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "oos_trade_histogram.png"), dpi=120)
    print(f"Wrote {os.path.join(PLOTS, 'oos_trade_histogram.png')}")

    # --- Equity curves ---
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(eq_1x.index, eq_1x, label="Strategy on S&P 1x", lw=1.5)
    ax.plot(eq_3x.index, eq_3x, label=f"Strategy on S&P {LEV:.0f}x", lw=1.5)
    bh = buy_hold_equity(spx["Close"])
    ax.plot(bh.index, bh, label="Buy & Hold S&P 1x", lw=1.0, alpha=0.7, color="gray")
    ax.set_yscale("log")
    ax.set_title(f"Out-of-sample equity — buy-the-fear on S&P 500 ({start_yr}-{end_yr}, start $10,000)")
    ax.set_ylabel("Equity ($, log)")
    ax.legend()
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "oos_equity.png"), dpi=120)
    print(f"Wrote {os.path.join(PLOTS, 'oos_equity.png')}")


if __name__ == "__main__":
    main()
