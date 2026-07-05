"""
One candlestick chart per trade, ~3 months centered on the signal, so each
entry can be inspected and compared. Panels: TQQQ daily candles (+ MA5, signal
day, fixed +9 entry, MA5-confirmation entry), VIX (40 line), S&P weekly RSI(14)
(35 line). Saves plots/signal_trade_NN.png.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from backtest import load_yf, build_signals, run_backtest, DATA, PLOTS

HALF = 31  # trading days each side of the signal (~3 months total)
UP, DOWN, ORANGE, BLUE, GREEN, RED = "#3fb950", "#f85149", "#f0ad4e", "#5b8def", "#2e8b3f", "#d9534f"


def confirm_entry(close, ma5, dates, sig_date, cap=20):
    """First close back above MA5 after the signal, else the cap day (fallback)."""
    si = dates.index(pd.Timestamp(sig_date))
    for j in range(si + 1, min(si + cap + 1, len(dates))):
        if close.iloc[j] > ma5.iloc[j]:
            return j, close.iloc[j], False
    j = min(si + cap, len(dates) - 1)
    return j, close.iloc[j], True


def candles(ax, sub):
    for k, (_, r) in enumerate(sub.iterrows()):
        up = r["Close"] >= r["Open"]
        c = UP if up else DOWN
        ax.plot([k, k], [r["Low"], r["High"]], color=c, lw=0.9, zorder=2)
        lo = min(r["Open"], r["Close"])
        ax.add_patch(Rectangle((k - 0.3, lo), 0.6, max(abs(r["Close"] - r["Open"]), 1e-9),
                               facecolor=c, edgecolor=c, zorder=3))


def main():
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))
    sig = build_signals(tqqq, spx, vix, ma_period=50)
    tr, _ = run_backtest(sig)                      # fixed +9 trades
    close = tqqq["Close"]
    ma5 = close.rolling(5).mean()
    dates = close.index.to_list()

    for n in range(1, len(tr) + 1):
        t = tr.iloc[n - 1]
        sd = pd.Timestamp(t["Signal_Date"])
        ed = pd.Timestamp(t["Entry_Date"])
        si = dates.index(sd)
        ei = dates.index(ed)
        ci, cp, capped = confirm_entry(close, ma5, dates, sd)
        lo, hi = max(0, si - HALF), min(len(dates), si + HALF + 1)
        sub = tqqq.iloc[lo:hi]
        sigsub = sig.reindex(sub.index)
        xs = np.arange(len(sub))
        pos = {idx: k for k, idx in enumerate(range(lo, hi))}

        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, figsize=(13, 9), height_ratios=[3, 1, 1], sharex=True)

        candles(ax1, sub)
        ax1.plot(xs, ma5.iloc[lo:hi].values, color=ORANGE, lw=1.3, ls="--", label="MA5", zorder=4)
        # markers
        ax1.axvline(pos[si], color=BLUE, ls=":", lw=1.4)
        ax1.annotate(f"SIGNAL {sd.date()}\n{t['Trigger']}", xy=(pos[si], sub['High'].iloc[pos[si]]),
                     xytext=(6, 14), textcoords="offset points", color=BLUE, fontsize=9, fontweight="bold")
        if ei in pos:
            ax1.scatter([pos[ei]], [t["Entry_Price"]], marker="v", s=210, color=RED, edgecolor="k", zorder=6)
            ax1.annotate(f"fixed +9d  ${t['Entry_Price']:.2f}", xy=(pos[ei], t["Entry_Price"]),
                         xytext=(6, -34), textcoords="offset points", color=RED, fontsize=9, fontweight="bold")
        if ci in pos:
            ax1.scatter([pos[ci]], [cp], marker="^", s=210, color=UP, edgecolor="k", zorder=6)
            ax1.annotate(f"MA5 confirm{' (cap)' if capped else ''}  ${cp:.2f}", xy=(pos[ci], cp),
                         xytext=(6, 18), textcoords="offset points", color=GREEN, fontsize=9, fontweight="bold")
        diff = (t["Entry_Price"] / cp - 1) * 100
        ax1.set_title(f"Trade #{n} — signal {sd.date()} ({t['Trigger']})   ·   "
                      f"fixed+9 ${t['Entry_Price']:.2f}  vs  MA5-confirm ${cp:.2f}  "
                      f"(fixed {diff:+.1f}%)", fontsize=11)
        ax1.set_ylabel("TQQQ $")
        ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(True, alpha=0.2)

        # VIX
        ax2.plot(xs, sigsub["vix_close"].values, color=ORANGE, lw=1.2)
        ax2.axhline(40, color=DOWN, lw=0.9, ls="--")
        ax2.fill_between(xs, 40, sigsub["vix_close"].values,
                         where=sigsub["vix_close"].values > 40, color=DOWN, alpha=0.25)
        ax2.axvline(pos[si], color=BLUE, ls=":", lw=1.0)
        ax2.set_ylabel("VIX")
        ax2.grid(True, alpha=0.2)

        # weekly RSI
        ax3.plot(xs, sigsub["rsi"].values, color=BLUE, lw=1.2)
        ax3.axhline(35, color=DOWN, lw=0.9, ls="--")
        ax3.fill_between(xs, 35, sigsub["rsi"].values,
                         where=sigsub["rsi"].values < 35, color=DOWN, alpha=0.25)
        ax3.axvline(pos[si], color=BLUE, ls=":", lw=1.0)
        ax3.set_ylabel("S&P wk RSI")
        ax3.grid(True, alpha=0.2)

        # date ticks
        ticks = np.linspace(0, len(sub) - 1, 8, dtype=int)
        ax3.set_xticks(ticks)
        ax3.set_xticklabels([sub.index[k].strftime("%Y-%m-%d") for k in ticks], rotation=30, ha="right", fontsize=8)

        fig.suptitle(f"Trade #{n}: signal & entry (candlesticks, ~3 months around signal)", fontsize=13)
        fig.tight_layout()
        out = os.path.join(PLOTS, f"signal_trade_{n:02d}.png")
        fig.savefig(out, dpi=125)
        plt.close(fig)
        print(f"#{n:2d} {sd.date()} | fixed+9 {ed.date()} ${t['Entry_Price']:.2f} | "
              f"MA5-confirm {dates[ci].date()} ${cp:.2f}{' (cap)' if capped else ''} -> {out}")


if __name__ == "__main__":
    main()
