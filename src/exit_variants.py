"""
Phase 1 / Step 2 — Re-engineer the exit (IMPROVEMENT_PLAN.md).

Goal: cut intra-trade drawdown (the -46%..-58% dips below entry) without giving
up most of the upside. Each exit rule is tested as a separate variant on the
tradable strategy (real TQQQ, 2010-2026), and compared on:
  * final equity / CAGR / portfolio MaxDD / Sharpe
  * per-trade **max drawdown from buy** (worst close-to-entry dip while holding) —
    both the AVERAGE and the WORST trade (this is what Step 2 must reduce).

Variants:
  baseline        trend exit, S&P < MA100 after 1yr           (reference)
  2b_ma50         faster trend exit (MA50)
  2b_ma200        slower trend exit (MA200)
  2a_trail25/30/35   pure trailing stop, 25/30/35% from peak
  2c_scaleout     sell 1/3 at +100%, 1/3 at +200%, trail the rest (30%)
  hybrid_trail30  trend exit OR 30% trailing stop, whichever first

Success: a variant that reduces avg AND worst per-trade max-DD-from-buy
meaningfully while keeping CAGR within ~15% of baseline — AND still passes the
Step 1 long-history test. The winner is re-validated on S&P 1970-2025 (1x & 3x)
and appended to results/variants.csv.
"""

import os
import numpy as np
import pandas as pd

from backtest import (
    load_yf, load_index, build_signals, run_backtest, metrics,
    DATA, RESULTS, PLOTS,
)

BASE_CAGR = 43.33  # locked baseline CAGR (Step 0.1)


def _plot_tradeoff(tbl):
    """Scatter: CAGR vs worst intra-trade DD — visualises the 'no free lunch'."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6.5))
    for _, r in tbl.iterrows():
        is_base = r["variant"] == "baseline"
        is_pick = r["variant"] == "2b_ma50"
        color = "#d9534f" if is_base else ("#5cb85c" if is_pick else "#0275d8")
        ax.scatter(r["worst_trade_DDfromBuy_%"], r["CAGR_%"], s=140 if (is_base or is_pick) else 90,
                   color=color, zorder=3, edgecolor="k", linewidth=0.6)
        ax.annotate(r["variant"], (r["worst_trade_DDfromBuy_%"], r["CAGR_%"]),
                    textcoords="offset points", xytext=(7, 5), fontsize=8)
    ax.axhline(BASE_CAGR * 0.85, color="gray", ls="--", lw=1)
    ax.text(ax.get_xlim()[0], BASE_CAGR * 0.85, " CAGR = baseline −15% (min to keep)",
            color="gray", fontsize=8, va="bottom")
    ax.set_xlabel("Worst per-trade drawdown from buy %  (→ right = shallower = better)")
    ax.set_ylabel("CAGR %")
    ax.set_title("Step 2: exit tradeoff — cutting the intra-trade dip costs CAGR (real TQQQ 2010-2026)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "exit_variants_tradeoff.png"), dpi=120)
    print(f"Wrote {os.path.join(PLOTS, 'exit_variants_tradeoff.png')}")


def dd_stats(trades):
    """Average and worst per-trade max-drawdown-from-buy (%)."""
    col = trades["MaxDD_From_Buy_%"]
    return col.mean(), col.min()


def evaluate(label, trades, equity):
    m = metrics(equity)
    avg_dd, worst_dd = dd_stats(trades)
    wins = (trades["Return_%"] > 0).mean() * 100 if len(trades) else np.nan
    return {
        "variant": label,
        "trades": len(trades),
        "win_%": round(wins, 1),
        "final_equity": round(m["Final Equity"], 0),
        "CAGR_%": round(m["CAGR %"], 2),
        "port_MaxDD_%": round(m["Max DD %"], 2),
        "Sharpe": round(m["Sharpe"], 2),
        "avg_trade_DDfromBuy_%": round(avg_dd, 1),
        "worst_trade_DDfromBuy_%": round(worst_dd, 1),
    }


def main():
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))

    # Signal frames differ only by the exit MA period.
    sig = {ma: build_signals(tqqq, spx, vix, ma_period=ma) for ma in (50, 100, 200)}

    specs = [
        ("baseline",       sig[100], dict(exit_mode="trend")),
        ("2b_ma50",        sig[50],  dict(exit_mode="trend")),
        ("2b_ma200",       sig[200], dict(exit_mode="trend")),
        ("2a_trail25",     sig[100], dict(exit_mode="trail", trail_pct=0.25)),
        ("2a_trail30",     sig[100], dict(exit_mode="trail", trail_pct=0.30)),
        ("2a_trail35",     sig[100], dict(exit_mode="trail", trail_pct=0.35)),
        ("2c_scaleout",    sig[100], dict(exit_mode="scaleout", trail_pct=0.30)),
        ("hybrid_trail30", sig[100], dict(exit_mode="trend_trail", trail_pct=0.30)),
    ]

    rows, trade_tables = [], {}
    for label, df, kw in specs:
        trades, equity = run_backtest(df, **kw)
        rows.append(evaluate(label, trades, equity))
        trade_tables[label] = (trades, kw)

    tbl = pd.DataFrame(rows)
    tbl["CAGR_vs_base_%"] = (tbl["CAGR_%"] / BASE_CAGR - 1) * 100  # relative CAGR change
    tbl.to_csv(os.path.join(RESULTS, "exit_variants.csv"), index=False)
    _plot_tradeoff(tbl)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print("\n=== STEP 2 — EXIT VARIANTS (real TQQQ, 2010-2026) ===")
    print(tbl.to_string(index=False))

    base = tbl[tbl["variant"] == "baseline"].iloc[0]
    print(f"\nBaseline: CAGR {base['CAGR_%']}%, avg DD-from-buy {base['avg_trade_DDfromBuy_%']}%, "
          f"worst {base['worst_trade_DDfromBuy_%']}%, port MaxDD {base['port_MaxDD_%']}%")

    # Strict Step-2 bar: reduce BOTH avg & worst DD-from-buy AND keep CAGR within -15%.
    cand = tbl[
        (tbl["variant"] != "baseline")
        & (tbl["avg_trade_DDfromBuy_%"] > base["avg_trade_DDfromBuy_%"])   # less negative = smaller dip
        & (tbl["worst_trade_DDfromBuy_%"] > base["worst_trade_DDfromBuy_%"])
        & (tbl["CAGR_vs_base_%"] >= -15.0)
    ].copy()
    print("\n=== Strict Step-2 bar (cut both DD-from-buy AND CAGR within -15%) ===")
    print("  candidates:", "none" if len(cand) == 0 else ", ".join(cand["variant"]))
    print("  -> The intra-trade dip below entry is where the recovery edge lives:")
    print("     every trailing stop that cuts it also cuts the recovery (CAGR 43%->23-36%,")
    print("     win 100%->59-67%). No exit rule cuts intra-trade DD cheaply. See Step 3 (sizing).")

    # Fold in the best *free* exit upgrade (MA50: better CAGR/MaxDD/Sharpe, same DD profile)
    # and validate it OOS. Also validate the best DD-reducer (trail35) for the record.
    _validate_oos("2b_ma50", dict(trade_tables["2b_ma50"][1]), ma_period=50)
    _validate_oos("2a_trail35", dict(trade_tables["2a_trail35"][1]), ma_period=100)
    _append_to_variants("2b_ma50", tbl[tbl["variant"] == "2b_ma50"].iloc[0])


def _validate_oos(winner, kw, ma_period=100):
    """Re-run the winning exit on the long S&P history (Step 1 re-validation)."""
    spx = load_index(os.path.join(DATA, "sp500_index_data.csv"))
    spx = spx[spx.index >= "1970-01-01"]
    df = build_signals(spx[["Open", "Close"]].copy(), spx, vix=None, ma_period=ma_period)  # RSI-only
    print(f"\n=== Step-1 re-validation: '{winner}' on S&P 1970-2025 ===")
    for lev, drag, tag in [(1.0, 0.0, "1x"), (3.0, 0.01, "3x")]:
        trades, eq = run_backtest(df, leverage=lev, annual_drag=drag, **kw)
        m = metrics(eq)
        wr = (trades["Return_%"] > 0).mean() * 100
        avg_dd, worst_dd = dd_stats(trades)
        split = pd.Timestamp("2010-01-01")
        pre = trades[trades["Entry_Date"] < split]
        wr_pre = (pre["Return_%"] > 0).mean() * 100 if len(pre) else np.nan
        print(f"  {tag}: {len(trades)} trades, win {wr:.1f}% (pre-2010 {wr_pre:.1f}%), "
              f"CAGR {m['CAGR %']:.2f}%, port MaxDD {m['Max DD %']:.1f}%, "
              f"avg/worst DD-from-buy {avg_dd:.1f}%/{worst_dd:.1f}%")


def _append_to_variants(winner, row):
    """Fold the winning exit into the master ledger results/variants.csv."""
    path = os.path.join(RESULTS, "variants.csv")
    master = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    tag = f"step2_{winner}_tqqq"
    master = master[master["variant"] != tag]
    new = {
        "variant": tag, "start": "2010-02-11", "end": "2026-06-26",
        "trades": int(row["trades"]), "win_rate_%": row["win_%"],
        "final_equity": row["final_equity"], "CAGR_%": row["CAGR_%"],
        "MaxDD_%": row["port_MaxDD_%"], "Sharpe": row["Sharpe"],
        "avg_DDfromBuy_%": row["avg_trade_DDfromBuy_%"],
        "worst_DDfromBuy_%": row["worst_trade_DDfromBuy_%"],
    }
    master = pd.concat([master, pd.DataFrame([new])], ignore_index=True)
    master.to_csv(path, index=False)
    print(f"\nAppended '{tag}' to {path}")


if __name__ == "__main__":
    main()
