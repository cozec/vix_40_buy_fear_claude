"""
Per-trade charts for the VIX>40 buy-the-fear backtest.

For each trade, render a 3-panel chart on a daily, date-based x-axis:
  - top:    TQQQ daily candlesticks with signal / entry / exit markers + return
  - mid:    VIX (with the 40 threshold line)        <- trigger 1
  - bottom: S&P 500 weekly RSI(14) (with the 35 line) <- trigger 2

Both triggers are always shown, whether or not they fired for that trade.
Time range = signal..exit (+padding); for a still-open trade it defaults to a
full year from entry so the position's intended horizon is visible.

Saves plots/trade_01.png ... plots/trade_NN.png.
"""

import os
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(__file__))
from backtest import (  # noqa: E402
    build_signals, run_backtest, load_yf,
    DATA, PLOTS, VIX_THRESHOLD, RSI_THRESHOLD,
)

# Register a CJK-capable font so Chinese labels render (macOS).
for _fp in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Hiragino Sans GB.ttc"):
    if os.path.exists(_fp):
        font_manager.fontManager.addfont(_fp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=_fp).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

BG = "#1a2029"; GRID = "#2d333b"; INK = "#e6edf3"; MUTED = "#9aa7b4"
UP = "#3fb950"; DOWN = "#f85149"; ORANGE = "#f0883e"; BLUE = "#58a6ff"; GREY = "#6e7681"
PAD = pd.Timedelta(days=21)

# Macro "panic reason" behind each trade's signal (by trade number).
PANIC = {
    1: "2010 闪崩 / 欧债危机",
    2: "2011 美债降级 / 欧债危机",
    3: "2015 人民币贬值 / 中国股灾",
    4: "2016 美国大选前抛售",
    5: "2018 美联储加息抛售",
    6: "2020 新冠疫情崩盘",
    7: "2022 通胀加息熊市",
    8: "2023 美债收益率飙升",
    9: "2025 关税冲击",
    10: "2026 年 3 月回调",
}


def style_ax(ax):
    ax.set_facecolor(BG)
    ax.tick_params(colors=MUTED, labelsize=9)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(True, color=GRID, alpha=0.5, lw=0.6)


def main():
    df = build_signals()                       # daily: vix_close, weekly_rsi, ...
    trades, _ = run_backtest(df)
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    last_date = tqqq.index[-1]

    for i, t in trades.iterrows():
        num = i + 1
        sig = pd.Timestamp(t["Signal_Date"])
        ent = pd.Timestamp(t["Entry_Date"])
        exit_d = pd.Timestamp(t["Exit_Date"])
        is_open = t.get("Open_At_End") is True

        if is_open:
            # show the trailing 1 year of data, latest date flush to the right border
            end = last_date
            start = last_date - pd.Timedelta(days=365)
        else:
            start = sig - PAD
            end = exit_d + PAD
        data_end = min(end, last_date)
        tq = tqqq.loc[start:data_end]
        dd = df.loc[start:data_end]
        span = float(tq["High"].max() - tq["Low"].min()) or 1.0

        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, figsize=(10, 7.2), sharex=True,
            gridspec_kw={"height_ratios": [3, 1, 1], "hspace": 0.10})
        fig.patch.set_facecolor(BG)
        for ax in (ax1, ax2, ax3):
            style_ax(ax)

        # --- daily candlesticks ---
        for dt, r in tq.iterrows():
            x = mdates.date2num(dt)
            color = UP if r["Close"] >= r["Open"] else DOWN
            ax1.plot([x, x], [r["Low"], r["High"]], color=color, lw=0.5, zorder=2)
            lo, hi = sorted((r["Open"], r["Close"]))
            ax1.add_patch(Rectangle((x - 0.35, lo), 0.7, max(hi - lo, span * 0.002),
                                    facecolor=color, edgecolor=color, lw=0, zorder=3))

        ax1.axvline(sig, color=ORANGE, ls=":", lw=1.3)
        ax1.axvline(ent, color=UP, ls="--", lw=1.3)
        ax1.scatter([ent], [t["Entry_Price"]], marker="^", s=120,
                    color=UP, edgecolor="white", lw=0.6, zorder=5)
        ax1.annotate(f"买入 ${t['Entry_Price']:.2f}", xy=(ent, t["Entry_Price"]),
                     xytext=(-58, -44), textcoords="offset points",
                     color=UP, fontsize=9, ha="center", va="center", zorder=6,
                     arrowprops=dict(arrowstyle="->", color=UP, lw=1.1),
                     bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=UP, lw=0.9))
        ax1.annotate("信号", (sig, tq["High"].max()), color=ORANGE, fontsize=9,
                     ha="center", va="bottom")

        if not is_open:
            ax1.axvline(exit_d, color=DOWN, ls="--", lw=1.3)
            ax1.scatter([exit_d], [t["Exit_Price"]], marker="v", s=120,
                        color=DOWN, edgecolor="white", lw=0.6, zorder=5)
            ax1.annotate(f"卖出 ${t['Exit_Price']:.2f}", xy=(exit_d, t["Exit_Price"]),
                         xytext=(-58, 40), textcoords="offset points",
                         color=DOWN, fontsize=9, ha="center", va="center", zorder=6,
                         arrowprops=dict(arrowstyle="->", color=DOWN, lw=1.1),
                         bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=DOWN, lw=0.9))
            exit_lbl = exit_d.strftime("%Y-%m-%d")
        else:
            hold_end = ent + pd.Timedelta(days=365)
            ax1.axvline(hold_end, color=GREY, ls=":", lw=1.2)
            ax1.annotate("1 年最低持有", (hold_end, tq["Low"].min()), color=GREY,
                         fontsize=8, ha="right", va="bottom",
                         xytext=(-4, 2), textcoords="offset points")
            exit_lbl = "持仓中"

        status = "（持仓中）" if is_open else ""
        panic = PANIC.get(num)
        head = f"交易 #{num}" + (f"  ·  {panic}" if panic else "")
        ax1.set_title(
            f"{head}  ·  收益 {t['Return_%']:+.1f}%{status}\n"
            f"触发 {t['Trigger']}   信号 {sig:%Y-%m-%d}   买入 {ent:%Y-%m-%d}   "
            f"卖出 {exit_lbl}   持有 {int(t['Hold_Days'])} 天",
            color=INK, fontsize=12, pad=12)
        ax1.set_ylabel("TQQQ 价格 ($)", color=MUTED, fontsize=10)

        # --- trigger 1: VIX ---
        ax2.plot(dd.index, dd["vix_close"], color=ORANGE, lw=1.2)
        ax2.axhline(VIX_THRESHOLD, color=DOWN, ls="--", lw=1)
        ax2.fill_between(dd.index, VIX_THRESHOLD, dd["vix_close"],
                         where=dd["vix_close"] > VIX_THRESHOLD,
                         color=DOWN, alpha=0.25)
        ax2.set_ylabel("VIX", color=MUTED, fontsize=10)
        ax2.annotate("40", (dd.index[0], VIX_THRESHOLD), color=DOWN, fontsize=8,
                     va="bottom", ha="left")

        # --- trigger 2: S&P weekly RSI(14) ---
        ax3.plot(dd.index, dd["weekly_rsi"], color=BLUE, lw=1.2)
        ax3.axhline(RSI_THRESHOLD, color=DOWN, ls="--", lw=1)
        ax3.fill_between(dd.index, RSI_THRESHOLD, dd["weekly_rsi"],
                         where=dd["weekly_rsi"] < RSI_THRESHOLD,
                         color=DOWN, alpha=0.25)
        ax3.set_ylabel("标普 RSI(14)", color=MUTED, fontsize=10)
        ax3.annotate("35", (dd.index[0], RSI_THRESHOLD), color=DOWN, fontsize=8,
                     va="top", ha="left")

        for ax in (ax2, ax3):
            ax.axvline(sig, color=ORANGE, ls=":", lw=1.0)

        # date axis spanning the full intended range (blank after data for open trades)
        ax1.set_xlim(mdates.date2num(start), mdates.date2num(end))
        loc = mdates.AutoDateLocator()
        ax3.xaxis.set_major_locator(loc)
        ax3.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))

        fig.savefig(os.path.join(PLOTS, f"trade_{num:02d}.png"),
                    dpi=110, bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        print(f"trade_{num:02d}.png  {t['Trigger']:<22s} {t['Return_%']:+6.1f}%  "
              f"{start.date()}..{end.date()}{' (open/1yr)' if is_open else ''}")


if __name__ == "__main__":
    main()
