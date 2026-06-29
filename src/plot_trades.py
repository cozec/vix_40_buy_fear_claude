"""
Per-trade charts for the VIX>40 buy-the-fear backtest.

For each of the 10 trades, render a 2-panel chart:
  - top:    TQQQ weekly candlesticks with signal / entry / exit markers + return
  - bottom: the triggering indicator over the same window
            (VIX with the 40 line, or S&P weekly RSI(14) with the 35 line)

Saves plots/trade_01.png ... plots/trade_NN.png.
"""

import os
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

# Register a CJK-capable font so Chinese labels render (macOS).
for _fp in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Hiragino Sans GB.ttc"):
    if os.path.exists(_fp):
        font_manager.fontManager.addfont(_fp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=_fp).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, os.path.dirname(__file__))
from backtest import (  # noqa: E402
    build_signals, run_backtest, load_yf, rsi,
    DATA, PLOTS, RSI_PERIOD, VIX_THRESHOLD, RSI_THRESHOLD,
)

BG = "#1a2029"; GRID = "#2d333b"; INK = "#e6edf3"; MUTED = "#9aa7b4"
UP = "#3fb950"; DOWN = "#f85149"; ORANGE = "#f0883e"; BLUE = "#58a6ff"


def weekly_ohlc(df):
    """Resample daily OHLC to weekly (Friday-ending) candles."""
    w = pd.DataFrame({
        "Open": df["Open"].resample("W-FRI").first(),
        "High": df["High"].resample("W-FRI").max(),
        "Low": df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
    }).dropna()
    return w


def xpos(idx, date):
    """X index of the weekly candle containing `date`."""
    pos = idx.searchsorted(pd.Timestamp(date))
    return min(int(pos), len(idx) - 1)


def style_ax(ax):
    ax.set_facecolor(BG)
    ax.tick_params(colors=MUTED, labelsize=9)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(True, color=GRID, alpha=0.5, lw=0.6)


def main():
    df = build_signals()
    trades, _ = run_backtest(df)

    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))
    weekly_rsi = rsi(spx["Close"].resample("W-FRI").last(), RSI_PERIOD)
    weekly_vix = vix["Close"].resample("W-FRI").max()
    last_date = tqqq.index[-1]

    for i, t in trades.iterrows():
        num = i + 1
        sig = pd.Timestamp(t["Signal_Date"])
        ent = pd.Timestamp(t["Entry_Date"])
        exit_d = pd.Timestamp(t["Exit_Date"])
        is_open = t.get("Open_At_End") is True

        start = sig - pd.Timedelta(weeks=4)
        end = min(exit_d + pd.Timedelta(weeks=4), last_date)
        w = weekly_ohlc(tqqq.loc[start:end])
        idx = w.index
        span = float(w["High"].max() - w["Low"].min()) or 1.0

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 6.3), sharex=True,
            gridspec_kw={"height_ratios": [3, 1.1], "hspace": 0.08})
        fig.patch.set_facecolor(BG)
        style_ax(ax1); style_ax(ax2)

        # --- candlesticks ---
        for j, (_, r) in enumerate(w.iterrows()):
            color = UP if r["Close"] >= r["Open"] else DOWN
            ax1.plot([j, j], [r["Low"], r["High"]], color=color, lw=0.9, zorder=2)
            lo, hi = sorted((r["Open"], r["Close"]))
            ax1.add_patch(Rectangle((j - 0.3, lo), 0.6, max(hi - lo, span * 0.003),
                                    facecolor=color, edgecolor=color, zorder=3))

        xs, xe = xpos(idx, sig), xpos(idx, ent)
        ax1.axvline(xs, color=ORANGE, ls=":", lw=1.3, zorder=1)
        ax1.axvline(xe, color=UP, ls="--", lw=1.3, zorder=1)
        ax1.scatter([xe], [t["Entry_Price"]], marker="^", s=110,
                    color=UP, edgecolor="white", lw=0.6, zorder=5)
        ax1.annotate("信号", (xs, w["High"].max()), color=ORANGE, fontsize=9,
                     ha="center", va="bottom")
        ax1.annotate(f"买入 ${t['Entry_Price']:.2f}", (xe, t["Entry_Price"]),
                     color=UP, fontsize=9, ha="center", va="top",
                     xytext=(0, -14), textcoords="offset points")

        if not is_open:
            xx = xpos(idx, exit_d)
            ax1.axvline(xx, color=DOWN, ls="--", lw=1.3, zorder=1)
            ax1.scatter([xx], [t["Exit_Price"]], marker="v", s=110,
                        color=DOWN, edgecolor="white", lw=0.6, zorder=5)
            ax1.annotate(f"卖出 ${t['Exit_Price']:.2f}", (xx, t["Exit_Price"]),
                         color=DOWN, fontsize=9, ha="center", va="bottom",
                         xytext=(0, 12), textcoords="offset points")
            exit_lbl = exit_d.strftime("%Y-%m-%d")
        else:
            exit_lbl = "持仓中"

        status = "（持仓中）" if is_open else ""
        ax1.set_title(
            f"交易 #{num}  ·  {t['Trigger']}  ·  收益 {t['Return_%']:+.1f}%{status}\n"
            f"信号 {sig:%Y-%m-%d}   买入 {ent:%Y-%m-%d}   卖出 {exit_lbl}   "
            f"持有 {int(t['Hold_Days'])} 天",
            color=INK, fontsize=12, pad=12)
        ax1.set_ylabel("TQQQ 价格 ($)", color=MUTED, fontsize=10)

        # --- trigger indicator panel ---
        if "VIX" in t["Trigger"]:
            series = weekly_vix.reindex(idx)
            ax2.plot(range(len(idx)), series.values, color=ORANGE, lw=1.4)
            ax2.axhline(VIX_THRESHOLD, color=DOWN, ls="--", lw=1)
            ax2.set_ylabel("VIX", color=MUTED, fontsize=10)
            ax2.annotate("40", (0, VIX_THRESHOLD), color=DOWN, fontsize=8,
                         va="bottom", ha="left")
        else:
            series = weekly_rsi.reindex(idx)
            ax2.plot(range(len(idx)), series.values, color=BLUE, lw=1.4)
            ax2.axhline(RSI_THRESHOLD, color=DOWN, ls="--", lw=1)
            ax2.set_ylabel("标普 RSI(14)", color=MUTED, fontsize=10)
            ax2.annotate("35", (0, RSI_THRESHOLD), color=DOWN, fontsize=8,
                         va="bottom", ha="left")
        ax2.axvline(xs, color=ORANGE, ls=":", lw=1.3)

        step = max(1, len(idx) // 8)
        ticks = list(range(0, len(idx), step))
        ax2.set_xticks(ticks)
        ax2.set_xticklabels([idx[k].strftime("%b-%y") for k in ticks], fontsize=8)
        ax1.set_xlim(-1, len(idx))

        fig.savefig(os.path.join(PLOTS, f"trade_{num:02d}.png"),
                    dpi=110, bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        print(f"trade_{num:02d}.png  {t['Trigger']:<22s} {t['Return_%']:+6.1f}%  "
              f"({len(idx)} weekly candles)")


if __name__ == "__main__":
    main()
