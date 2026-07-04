"""
Phase 1 / Step 3 — Size for survival (IMPROVEMENT_PLAN.md).

Steps 1-2 established the signal is real but full-capital 3x courts ruin
(-92% out-of-sample). Step 3 asks: what SIZE / LEVERAGE survives the worst case
while keeping a good risk-adjusted return (Sharpe / Calmar)?

Working strategy is fixed from Steps 1-2: S&P weekly RSI(14)<35 (+VIX where it
exists) signal, 9-day entry delay, 1-year min hold, **MA50** trend exit. We vary
only sizing:

  3a scale-in   : buy in 3 equal tranches vs one lump (entry-timing luck).
  3b fractional : deploy 100/75/50/25% of equity in the 3x ETF, rest in cash.
  3c leverage   : 1x / 2x / 3x exposure (synthetic, daily-rebalanced).

CRUCIAL: the 2010-2026 window is a near-uninterrupted bull, so in-sample metrics
*reward maximum leverage* — the exact overfit trap Step 1 warned about. The real
test of "size for survival" is the LONG history (S&P 1970-2025) where the crashes
live. We report BOTH windows and decide on the long one.
"""

import os
import numpy as np
import pandas as pd

from backtest import (
    load_yf, load_index, build_signals, run_backtest, metrics,
    DATA, RESULTS, PLOTS,
)

WIN_START = "2010-02-11"      # real-TQQQ tradable window
LONG_START = "1970-01-01"     # long survival test
SPLIT = pd.Timestamp("2010-01-01")


def calmar(m):
    return m["CAGR %"] / abs(m["Max DD %"]) if m["Max DD %"] else np.nan


def evaluate(label, exposure, trades, equity, split_pre=False):
    m = metrics(equity)
    wins = (trades["Return_%"] > 0).mean() * 100 if len(trades) else np.nan
    worst_dd = trades["MaxDD_From_Buy_%"].min() if len(trades) else np.nan
    row = {
        "variant": label, "exposure": exposure, "trades": len(trades),
        "win_%": round(wins, 1), "final_equity": round(m["Final Equity"], 0),
        "CAGR_%": round(m["CAGR %"], 2), "MaxDD_%": round(m["Max DD %"], 2),
        "Sharpe": round(m["Sharpe"], 3), "Calmar": round(calmar(m), 3),
        "worst_DDfromBuy_%": round(worst_dd, 1),
    }
    if split_pre:
        # Max drawdown restricted to the pre-2010 (true out-of-sample) segment.
        eq_pre = equity[equity.index < SPLIT]
        row["pre2010_MaxDD_%"] = round((eq_pre / eq_pre.cummax() - 1).min() * 100, 2) if len(eq_pre) else np.nan
    return row


def insample():
    """2010-2026, real TQQQ + synthetic QQQ leverage. Shows the bull-market trap."""
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))
    qqq = pd.read_csv(os.path.join(DATA, "qqq_adj_data.csv"), index_col="Date", parse_dates=True)
    qqq = qqq[qqq.index >= WIN_START]

    sig_tqqq = build_signals(tqqq, spx, vix, ma_period=50)
    sig_qqq = build_signals(qqq[["Open", "Close"]].copy(), spx, vix, ma_period=50)

    rows = [evaluate("ref_3x_full (TQQQ)", "3.0x", *run_backtest(sig_tqqq))]
    for label, offs in [("3a_tranche_0_9_18", (0, 9, 18)), ("3a_tranche_0_5_10", (0, 5, 10))]:
        rows.append(evaluate(label, "3.0x", *run_backtest(sig_tqqq, entry_offsets=offs)))
    for f in (0.75, 0.50, 0.25):
        rows.append(evaluate(f"3b_frac_{int(f*100)}", f"{3*f:.2f}x", *run_backtest(sig_tqqq, capital_fraction=f)))
    for L in (1.0, 2.0, 3.0):
        rows.append(evaluate(f"3c_lev_{L:.0f}x (QQQ)", f"{L:.1f}x",
                             *run_backtest(sig_qqq, leverage=L, annual_drag=(L - 1) * 0.01)))
    return pd.DataFrame(rows)


def longtest():
    """S&P 1970-2025 synthetic leverage. The survival test (crashes included)."""
    spx = load_index(os.path.join(DATA, "sp500_index_data.csv"))
    spx = spx[spx.index >= LONG_START]
    sig = build_signals(spx[["Open", "Close"]].copy(), spx, vix=None, ma_period=50)

    rows = []
    for L in (1.0, 2.0, 3.0):
        rows.append(evaluate(f"lev_{L:.0f}x", f"{L:.1f}x",
                             *run_backtest(sig, leverage=L, annual_drag=(L - 1) * 0.01), split_pre=True))
    for f in (0.75, 0.50):   # fractional on synthetic 3x
        tr, eq = run_backtest(sig, leverage=3.0, annual_drag=0.02, capital_fraction=f)
        rows.append(evaluate(f"3x_frac_{int(f*100)}", f"{3*f:.2f}x", tr, eq, split_pre=True))
    return pd.DataFrame(rows)


def main():
    ins = insample()
    lng = longtest()
    ins.to_csv(os.path.join(RESULTS, "sizing_insample.csv"), index=False)
    lng.to_csv(os.path.join(RESULTS, "sizing_longtest.csv"), index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print("\n=== STEP 3a/b/c IN-SAMPLE (MA50, 2010-2026) — the bull-market trap ===")
    print(ins.to_string(index=False))
    print("  NOTE: in this all-bull window, Sharpe/Calmar RISE with leverage. Do not")
    print("        pick leverage here — 2010-2026 never saw a 3x-killing crash.")

    print("\n=== STEP 3 SURVIVAL TEST (MA50 synthetic, S&P 1970-2025) ===")
    print(lng.to_string(index=False))

    # Gate: on the long history, among all sizings whose worst-case is survivable
    # (pre-2010 MaxDD better than -80%), take the best long-run Calmar.
    survivable = lng[lng["pre2010_MaxDD_%"] > -80.0]
    ruin = lng[lng["pre2010_MaxDD_%"] <= -80.0]
    print("\n=== Gate: survive the worst case (pre-2010 MaxDD) ===")
    print("  RUINOUS (pre-2010 DD <= -80%):", ", ".join(
        f"{r['variant']} {r['pre2010_MaxDD_%']}%" for _, r in ruin.iterrows()) or "none")
    print("  SURVIVABLE                    :", ", ".join(
        f"{r['variant']}({r['exposure']}) {r['pre2010_MaxDD_%']}% Calmar {r['Calmar']}"
        for _, r in survivable.iterrows()) or "none")
    ref3x = lng[lng["variant"] == "lev_3x"].iloc[0]
    if len(survivable):
        best = survivable.sort_values("Calmar", ascending=False).iloc[0]
        print(f"\n>>> Adopt {best['variant']} ({best['exposure']} effective) — worst case "
              f"pre-2010 MaxDD {best['pre2010_MaxDD_%']}% (vs full-3x {ref3x['pre2010_MaxDD_%']}% = ruin), "
              f"and best long-run Calmar {best['Calmar']} (Sharpe {best['Sharpe']}) — both beat full-3x "
              f"(Calmar {ref3x['Calmar']}, Sharpe {ref3x['Sharpe']}).")
        _append_to_variants(best)

    _plot(ins, lng)


def _append_to_variants(best):
    path = os.path.join(RESULTS, "variants.csv")
    master = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    tag = f"step3_{best['variant']}_longOOS"
    master = master[master["variant"] != tag]
    new = {"variant": tag, "start": "1970-01-02", "end": "2025-11-24",
           "trades": int(best["trades"]), "win_rate_%": best["win_%"],
           "final_equity": best["final_equity"], "CAGR_%": best["CAGR_%"],
           "MaxDD_%": best["MaxDD_%"], "Sharpe": best["Sharpe"], "Calmar": best["Calmar"],
           "worst_DDfromBuy_%": best["worst_DDfromBuy_%"]}
    master = pd.concat([master, pd.DataFrame([new])], ignore_index=True)
    master.to_csv(path, index=False)
    print(f"Appended '{tag}' to {path}")


def _plot(ins, lng):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
    for ax, (tbl, title) in zip(axes, [(ins, "In-sample 2010-2026 (bull trap)"),
                                        (lng, "Long survival test S&P 1970-2025")]):
        for _, r in tbl.iterrows():
            is_ref = "ref" in r["variant"] or r["variant"] == "lev_3x"
            ax.scatter(abs(r["MaxDD_%"]), r["CAGR_%"], s=150 if is_ref else 80,
                       color="#d9534f" if is_ref else "#0275d8", edgecolor="k", linewidth=0.6, zorder=3)
            ax.annotate(r["variant"], (abs(r["MaxDD_%"]), r["CAGR_%"]),
                        textcoords="offset points", xytext=(6, 4), fontsize=7)
        xs = np.linspace(5, abs(tbl["MaxDD_%"]).max() * 1.05, 50)
        for c in (0.2, 0.5, 0.8):
            ax.plot(xs, c * xs, ls=":", color="gray", lw=0.8)
            ax.text(xs[-1], c * xs[-1], f" Calmar {c}", color="gray", fontsize=7, va="center")
        ax.axvline(80, color="crimson", ls="--", lw=1)
        ax.text(80, ax.get_ylim()[1], " ruin line (-80%)", color="crimson", fontsize=7, va="top", rotation=90)
        ax.set_xlabel("Max drawdown %  (← left = safer)")
        ax.set_ylabel("CAGR %")
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
    fig.suptitle("Step 3 — sizing/leverage: the 2010s bull rewards max leverage; the long history punishes it")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "sizing_risk_return.png"), dpi=120)
    print(f"Wrote {os.path.join(PLOTS, 'sizing_risk_return.png')}")


if __name__ == "__main__":
    main()
