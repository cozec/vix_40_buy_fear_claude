"""
Phase 2 / Step 6 — Portfolio framing (IMPROVEMENT_PLAN.md), slim version.

Adam has already fixed the sleeve size (30% of assets in the 3x buy-the-fear
strategy), so we skip the sleeve-size sweep. What remains is the number that
actually matters: the BLENDED drawdown of 30% strategy + 70% core.

Key point: it is NOT 30% x strategy-DD, because the core and the 3x sleeve crash
together (2008, COVID, 2022). The blended drawdown depends entirely on what the
70% core is, so we run three standard cores to bracket the range:
  * 100% S&P 500      (all-equity core — worst, fully correlated crash)
  * 60/40 S&P + cash  (balanced)
  * 100% cash @ 4%/yr (uncorrelated buffer — best case)

Model: constant-mix, daily-rebalanced (r_p = 0.30*r_strategy + 0.70*r_core).
S&P is price-only (dividends omitted -> core CAGR ~2%/yr conservative; drawdown
essentially unaffected). Reported on the honest long window (synthetic 3x S&P
1970-2025) and the modern real-TQQQ window (2010-2026).
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

SLEEVE = 0.30
CASH_YR = 0.04
CASH_DAILY = (1 + CASH_YR) ** (1 / 252) - 1


def blend(strat_eq, sp_close, w_sp):
    """Daily-rebalanced 30% strategy + 70% core; core = w_sp S&P + (1-w_sp) cash."""
    r_strat = strat_eq.pct_change()
    r_sp = sp_close.reindex(strat_eq.index).ffill().pct_change()
    r_core = w_sp * r_sp + (1 - w_sp) * CASH_DAILY
    r_p = (SLEEVE * r_strat + (1 - SLEEVE) * r_core).fillna(0.0)
    return START_CAPITAL * (1 + r_p).cumprod()


def core_equity(sp_close, w_sp):
    r_sp = sp_close.pct_change()
    r_core = (w_sp * r_sp + (1 - w_sp) * CASH_DAILY).fillna(0.0)
    return START_CAPITAL * (1 + r_core).cumprod()


def blend_norebal(strat_eq, sp_close, w_sp):
    """Set-and-forget: fund 30/70 once, let each side ride (never rebalance).
    Over long horizons the 3x sleeve balloons to dominate -> inherits its crash."""
    core = core_equity(sp_close, w_sp).reindex(strat_eq.index).ffill()
    return (SLEEVE * START_CAPITAL * (strat_eq / strat_eq.iloc[0])
            + (1 - SLEEVE) * START_CAPITAL * (core / core.iloc[0]))


def blend_annual(strat_eq, sp_close, w_sp):
    """Realistic: rebalance back to 30/70 once a year (the sensible middle ground
    between set-and-forget ballooning and daily-rebal feeding the crash)."""
    r_strat = strat_eq.pct_change().fillna(0.0)
    r_sp = sp_close.reindex(strat_eq.index).ffill().pct_change()
    r_core = (w_sp * r_sp + (1 - w_sp) * CASH_DAILY).fillna(0.0)
    yr = strat_eq.index.year
    sleeve, core = SLEEVE * START_CAPITAL, (1 - SLEEVE) * START_CAPITAL
    port = np.empty(len(strat_eq))
    for k in range(len(strat_eq)):
        if k > 0:
            sleeve *= 1 + r_strat.iloc[k]
            core *= 1 + r_core.iloc[k]
            if yr[k] != yr[k - 1]:                 # new year -> rebalance to 30/70
                tot = sleeve + core
                sleeve, core = SLEEVE * tot, (1 - SLEEVE) * tot
        port[k] = sleeve + core
    return pd.Series(port, index=strat_eq.index)


def summarize(label, eq):
    m = metrics(eq)
    return {"portfolio": label, "CAGR_%": round(m["CAGR %"], 2),
            "MaxDD_%": round(m["Max DD %"], 2),
            "Calmar": round(m["CAGR %"] / abs(m["Max DD %"]), 3) if m["Max DD %"] else np.nan,
            "final_equity": round(m["Final Equity"], 0)}


def window(name, strat_eq, sp_close):
    """Headline table: 30/70 with annual rebalancing (the realistic policy)."""
    rows = [summarize(f"[{name}] 100% strategy (3x sleeve)", strat_eq)]
    for wlabel, w in [("100% S&P", 1.0), ("60/40", 0.6), ("100% cash@4%", 0.0)]:
        rows.append(summarize(f"[{name}] 100% core = {wlabel}", core_equity(sp_close, w)))
        rows.append(summarize(f"[{name}] 30/70 {wlabel} (annual rebal)", blend_annual(strat_eq, sp_close, w)))
    return pd.DataFrame(rows)


def rebal_sensitivity(name, strat_eq, sp_close, w_sp=1.0):
    """How much rebalancing policy alone moves the blended drawdown (S&P core)."""
    return pd.DataFrame([
        summarize(f"[{name}] 30/70 S&P — set&forget", blend_norebal(strat_eq, sp_close, w_sp)),
        summarize(f"[{name}] 30/70 S&P — annual rebal", blend_annual(strat_eq, sp_close, w_sp)),
        summarize(f"[{name}] 30/70 S&P — daily rebal", blend(strat_eq, sp_close, w_sp)),
    ])


def main():
    # Long, honest window: synthetic 3x S&P, MA50.
    sp_long = load_index(os.path.join(DATA, "sp500_index_data.csv"))
    sp_long = sp_long[sp_long.index >= "1970-01-01"]
    _, strat_long = run_backtest(build_signals(sp_long[["Open", "Close"]].copy(), sp_long,
                                               vix=None, ma_period=50), leverage=3.0, annual_drag=0.02)
    long_tbl = window("1970-2025", strat_long, sp_long["Close"])

    # Modern window: real TQQQ, MA50, real S&P core.
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))
    _, strat_mod = run_backtest(build_signals(tqqq, spx, vix, ma_period=50))
    mod_tbl = window("2010-2026", strat_mod, spx["Close"])

    out = pd.concat([long_tbl, mod_tbl], ignore_index=True)
    out.to_csv(os.path.join(RESULTS, "portfolio_blend.csv"), index=False)
    pd.set_option("display.width", 200)
    print("=== STEP 6 — BLENDED PORTFOLIO: 30% strategy + 70% core, ANNUAL rebalance ===\n")
    print(out.to_string(index=False))

    print("\n--- Rebalancing policy sensitivity (30/70 with 100% S&P core) ---")
    rs = pd.concat([rebal_sensitivity("1970-2025", strat_long, sp_long["Close"]),
                    rebal_sensitivity("2010-2026", strat_mod, spx["Close"])], ignore_index=True)
    print(rs.to_string(index=False))

    _plot(strat_long, sp_long["Close"], "1970-2025")


def _plot(strat_eq, sp_close, name):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[2, 1], sharex=True)
    curves = {
        "30/70 S&P (annual rebal)": (blend_annual(strat_eq, sp_close, 1.0), "#d9534f"),
        "30/70 60/40 (annual rebal)": (blend_annual(strat_eq, sp_close, 0.6), "#f0ad4e"),
        "30/70 cash (annual rebal)": (blend_annual(strat_eq, sp_close, 0.0), "#5cb85c"),
        "100% S&P (core only)": (core_equity(sp_close, 1.0), "gray"),
    }
    for label, (eq, c) in curves.items():
        ax1.plot(eq.index, eq, label=label, color=c, lw=1.3)
        dd = eq / eq.cummax() - 1
        ax2.plot(dd.index, dd * 100, color=c, lw=1.0)
    ax1.set_yscale("log")
    ax1.set_ylabel("Equity ($, log)")
    ax1.set_title(f"Step 6 — blended portfolio: 30% buy-the-fear 3x sleeve + 70% core ({name})")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, which="both", alpha=0.25)
    ax2.set_ylabel("Drawdown %")
    ax2.axhline(-30, color="k", ls="--", lw=0.8)
    ax2.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "portfolio_blend.png"), dpi=120)
    print(f"\nWrote {os.path.join(PLOTS, 'portfolio_blend.png')}")


if __name__ == "__main__":
    main()
