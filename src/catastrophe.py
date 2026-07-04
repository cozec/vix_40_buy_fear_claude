"""
Phase 2 / Step 4 — Catastrophe rule (IMPROVEMENT_PLAN.md).

Add a hard de-risk trigger for an extreme single-day move: exit the 3x position
at the close of any held day whose 3x daily return <= threshold (e.g. -30%, which
is ~a -10% day in the 1x underlying), then optionally stay flat for a cooldown.

Success criterion: NEGLIGIBLE drag in normal markets, MEANINGFUL protection in
the worst historical days. So we measure BOTH:
  * cost  — CAGR/Sharpe change on the working strategy (full 3x TQQQ, MA50).
  * tail  — worst portfolio drawdown / worst single-trade dip on the long
            history (S&P 1970-2025 synthetic 3x), which actually contains 1987,
            2000-02, 2008 and 2020.
"""

import os
import numpy as np
import pandas as pd

from backtest import (
    load_yf, load_index, build_signals, run_backtest, metrics, DATA, RESULTS, PLOTS,
)


def row(label, thr, cd, trades, equity):
    m = metrics(equity)
    ncat = int((trades["Exit_Reason"] == "catastrophe").sum()) if len(trades) else 0
    worst_day = equity.pct_change().min() * 100
    return {
        "variant": label,
        "cat_thr_3x_%": None if thr is None else round(thr * 100),
        "~underlying_%": None if thr is None else round(thr / 3 * 100, 1),
        "cooldown_d": cd,
        "trades": len(trades),
        "cat_exits": ncat,
        "CAGR_%": round(m["CAGR %"], 2),
        "MaxDD_%": round(m["Max DD %"], 2),
        "Sharpe": round(m["Sharpe"], 3),
        "Calmar": round(m["CAGR %"] / abs(m["Max DD %"]), 3) if m["Max DD %"] else np.nan,
        "worst_1day_%": round(worst_day, 1),
        "worst_trade_DD_%": round(trades["MaxDD_From_Buy_%"].min(), 1) if len(trades) else np.nan,
    }


def insample():
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))
    sig = build_signals(tqqq, spx, vix, ma_period=50)  # working strategy, full 3x

    rows = [row("baseline (no rule)", None, 0, *run_backtest(sig))]
    for thr in (-0.25, -0.30, -0.35, -0.40):
        rows.append(row(f"cat{int(thr*100)}", thr, 0, *run_backtest(sig, catastrophe_ret=thr)))
    rows.append(row("cat-30 cd60", -0.30, 60,
                    *run_backtest(sig, catastrophe_ret=-0.30, catastrophe_cooldown_days=60)))
    return pd.DataFrame(rows), sig


def longtest():
    spx = load_index(os.path.join(DATA, "sp500_index_data.csv"))
    spx = spx[spx.index >= "1970-01-01"]
    sig = build_signals(spx[["Open", "Close"]].copy(), spx, vix=None, ma_period=50)

    variants = {
        "baseline (no rule)": dict(),
        "cat-30 cd0": dict(catastrophe_ret=-0.30),
        "cat-30 cd60": dict(catastrophe_ret=-0.30, catastrophe_cooldown_days=60),
    }
    rows, tables = [], {}
    for label, extra in variants.items():
        tr, eq = run_backtest(sig, leverage=3.0, annual_drag=0.02, **extra)
        thr = extra.get("catastrophe_ret")
        rows.append(row(label, thr, extra.get("catastrophe_cooldown_days", 0), tr, eq))
        tables[label] = tr
    return pd.DataFrame(rows), tables


def main():
    ins, _ = insample()
    lng, lng_tr = longtest()
    ins.to_csv(os.path.join(RESULTS, "catastrophe_insample.csv"), index=False)
    lng.to_csv(os.path.join(RESULTS, "catastrophe_longtest.csv"), index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print("\n=== STEP 4 IN-SAMPLE (full 3x TQQQ, MA50, 2010-2026) — COST in normal markets ===")
    print(ins.to_string(index=False))

    print("\n=== STEP 4 LONG HISTORY (synthetic 3x S&P, 1970-2025) — TAIL protection ===")
    print(lng.to_string(index=False))

    # Which historical days triggered the rule?
    caught = lng_tr["cat-30 cd0"]
    caught = caught[caught["Exit_Reason"] == "catastrophe"]
    print("\nCatastrophe exits on the long history (3x day <= -30% ~ underlying <= -10%):")
    for _, t in caught.iterrows():
        print(f"  {pd.Timestamp(t['Exit_Date']).date()}  (entered {pd.Timestamp(t['Entry_Date']).date()}, "
              f"trade return {t['Return_%']:.0f}%)")

    _plot(ins, lng)


def _plot(ins, lng):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, tbl, title in [(axes[0], ins, "In-sample 2010-2026 (cost)"),
                           (axes[1], lng, "Long history 1970-2025 (protection)")]:
        x = np.arange(len(tbl))
        ax.bar(x - 0.2, tbl["CAGR_%"], 0.4, label="CAGR %", color="#0275d8")
        ax.bar(x + 0.2, tbl["MaxDD_%"].abs(), 0.4, label="|MaxDD| %", color="#d9534f")
        ax.set_xticks(x)
        ax.set_xticklabels(tbl["variant"], rotation=30, ha="right", fontsize=7)
        ax.set_title(title)
        ax.grid(True, axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Step 4 — catastrophe rule: little to gain in the V-shaped 2010s, real DD relief on the long history")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "catastrophe.png"), dpi=120)
    print(f"\nWrote {os.path.join(PLOTS, 'catastrophe.png')}")


if __name__ == "__main__":
    main()
