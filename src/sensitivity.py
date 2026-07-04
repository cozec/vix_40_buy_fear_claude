"""
Phase 2 / Step 5 — Robustness / sensitivity analysis (IMPROVEMENT_PLAN.md).

5a. Parameter sweep: VIX {35,40,45} x RSI {30,35,40} x hold {180,270,365,540 d}
    x delay {0,5,9,15 d} = 144 configs on the working strategy (full 3x TQQQ,
    MA50 exit). Heatmaps show whether the adopted config sits on a PLATEAU
    (neighbours similar => robust) or a knife-edge (=> overfit).

5b. Bootstrap the trade sequence: resample trades with replacement (10,000x),
    compounding each path and applying every trade's own intra-trade dip
    (MaxDD_From_Buy) so the drawdown distribution is realistic. Done for the
    10 in-sample TQQQ trades AND the 32-trade long-OOS set (S&P 1970-2025, 3x).
    Success: the bootstrap median is acceptable and the spread isn't a knife-edge.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backtest import (
    load_yf, load_index, build_signals, run_backtest, metrics, DATA, RESULTS, PLOTS,
)

np.random.seed(42)

VIXES = [35, 40, 45]
RSIS = [30, 35, 40]
HOLDS = [180, 270, 365, 540]     # ~6, 9, 12, 18 months
DELAYS = [0, 5, 9, 15]
ADOPTED = dict(vix=40, rsi=35, hold=365, delay=9)


# ---------------------------------------------------------------- 5a: grid sweep
def grid_5a():
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))

    # Signal frames depend only on (vix_thr, rsi_thr); cache them.
    sig_cache = {}
    for v in VIXES:
        for r in RSIS:
            sig_cache[(v, r)] = build_signals(tqqq, spx, vix, vix_threshold=v,
                                              rsi_threshold=r, ma_period=50)
    rows = []
    for v in VIXES:
        for r in RSIS:
            for h in HOLDS:
                for dl in DELAYS:
                    tr, eq = run_backtest(sig_cache[(v, r)], min_hold_days=h,
                                          entry_delay_days=dl, vix_threshold=v, rsi_threshold=r)
                    m = metrics(eq)
                    rows.append({
                        "vix": v, "rsi": r, "hold": h, "delay": dl,
                        "trades": len(tr),
                        "win_%": round((tr["Return_%"] > 0).mean() * 100, 1) if len(tr) else np.nan,
                        "CAGR_%": round(m["CAGR %"], 2),
                        "MaxDD_%": round(m["Max DD %"], 2),
                        "Sharpe": round(m["Sharpe"], 3),
                    })
    grid = pd.DataFrame(rows)
    grid.to_csv(os.path.join(RESULTS, "sensitivity_grid.csv"), index=False)
    return grid


def heatmap(ax, piv, title, fmt="{:.0f}", adopted_cell=None, cmap="viridis"):
    data = piv.values.astype(float)
    im = ax.imshow(data, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels(piv.index)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(j, i, fmt.format(data[i, j]), ha="center", va="center",
                    color="white", fontsize=8)
    if adopted_cell is not None:
        i, j = adopted_cell
        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                   edgecolor="red", lw=2.5))
    ax.set_title(title, fontsize=10)
    return im


def plot_5a(grid):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Slice 1: RSI x hold at adopted VIX & delay.
    s1 = grid[(grid.vix == ADOPTED["vix"]) & (grid.delay == ADOPTED["delay"])]
    p_cagr = s1.pivot(index="rsi", columns="hold", values="CAGR_%")
    p_dd = s1.pivot(index="rsi", columns="hold", values="MaxDD_%")
    ai = (list(p_cagr.index).index(ADOPTED["rsi"]), list(p_cagr.columns).index(ADOPTED["hold"]))
    heatmap(axes[0, 0], p_cagr, "CAGR % — RSI x hold (VIX=40, delay=9)", "{:.0f}", ai)
    heatmap(axes[0, 1], p_dd, "MaxDD % — RSI x hold (VIX=40, delay=9)", "{:.0f}", ai, cmap="magma")
    axes[0, 0].set_xlabel("hold (days)"); axes[0, 0].set_ylabel("RSI thr")
    axes[0, 1].set_xlabel("hold (days)"); axes[0, 1].set_ylabel("RSI thr")

    # Slice 2: VIX x delay at adopted RSI & hold.
    s2 = grid[(grid.rsi == ADOPTED["rsi"]) & (grid.hold == ADOPTED["hold"])]
    p_cagr2 = s2.pivot(index="vix", columns="delay", values="CAGR_%")
    p_dd2 = s2.pivot(index="vix", columns="delay", values="MaxDD_%")
    ai2 = (list(p_cagr2.index).index(ADOPTED["vix"]), list(p_cagr2.columns).index(ADOPTED["delay"]))
    heatmap(axes[1, 0], p_cagr2, "CAGR % — VIX x delay (RSI=35, hold=365)", "{:.0f}", ai2)
    heatmap(axes[1, 1], p_dd2, "MaxDD % — VIX x delay (RSI=35, hold=365)", "{:.0f}", ai2, cmap="magma")
    axes[1, 0].set_xlabel("entry delay (days)"); axes[1, 0].set_ylabel("VIX thr")
    axes[1, 1].set_xlabel("entry delay (days)"); axes[1, 1].set_ylabel("VIX thr")

    fig.suptitle("Step 5a — parameter sensitivity (red = adopted config). Smooth colour = plateau = robust.")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "sensitivity_heatmaps.png"), dpi=120)
    print(f"Wrote {os.path.join(PLOTS, 'sensitivity_heatmaps.png')}")


# ---------------------------------------------------------------- 5b: bootstrap
def bootstrap(returns, dds, horizon_years, n_iter=10000):
    """Resample the trade sequence; compound with each trade's intra-trade dip."""
    n = len(returns)
    cagrs = np.empty(n_iter)
    maxdds = np.empty(n_iter)
    for k in range(n_iter):
        idx = np.random.randint(0, n, size=n)
        r = returns[idx] / 100.0
        dd = dds[idx] / 100.0
        eq, peak, mdd = 1.0, 1.0, 0.0
        for ri, ddi in zip(r, dd):
            trough = eq * (1.0 + ddi)              # worst intra-trade point
            mdd = min(mdd, trough / peak - 1.0)
            eq *= (1.0 + ri)                        # trade closes
            peak = max(peak, eq)
        cagrs[k] = eq ** (1.0 / horizon_years) - 1.0
        maxdds[k] = mdd
    return cagrs * 100, maxdds * 100


def pct(a):
    return {p: round(np.percentile(a, p), 1) for p in (5, 25, 50, 75, 95)}


def run_5b():
    # In-sample MA50 TQQQ trades.
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))
    tr_in, _ = run_backtest(build_signals(tqqq, spx, vix, ma_period=50))
    yrs_in = (tr_in["Exit_Date"].max() - tr_in["Entry_Date"].min()).days / 365.25

    # Long-OOS synthetic 3x S&P trades (the honest sample, with losers).
    sp = load_index(os.path.join(DATA, "sp500_index_data.csv"))
    sp = sp[sp.index >= "1970-01-01"]
    tr_oos, _ = run_backtest(build_signals(sp[["Open", "Close"]].copy(), sp, vix=None, ma_period=50),
                             leverage=3.0, annual_drag=0.02)
    yrs_oos = (tr_oos["Exit_Date"].max() - tr_oos["Entry_Date"].min()).days / 365.25

    out = {}
    for name, tr, yrs in [("insample_10", tr_in, yrs_in), ("longOOS_32", tr_oos, yrs_oos)]:
        c, d = bootstrap(tr["Return_%"].to_numpy(), tr["MaxDD_From_Buy_%"].to_numpy(), yrs)
        out[name] = (c, d, len(tr), yrs)
        print(f"\n[{name}]  {len(tr)} trades over {yrs:.1f}y  (actual CAGR "
              f"{metrics_cagr(tr, yrs):.1f}%)")
        print(f"  bootstrap CAGR %:  {pct(c)}")
        print(f"  bootstrap MaxDD %: {pct(d)}")
        print(f"  P(CAGR>0): {np.mean(c>0)*100:.0f}%   P(MaxDD worse than -80%): {np.mean(d< -80)*100:.0f}%")
    _plot_5b(out)
    return out


def metrics_cagr(tr, yrs):
    eq = np.prod(1 + tr["Return_%"].to_numpy() / 100)
    return (eq ** (1 / yrs) - 1) * 100


def _plot_5b(out):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    for col, (name, (c, d, n, yrs)) in enumerate(out.items()):
        axes[0, col].hist(c, bins=60, color="#0275d8")
        axes[0, col].axvline(np.median(c), color="red", lw=1.5, label=f"median {np.median(c):.1f}%")
        axes[0, col].axvline(np.percentile(c, 5), color="gray", ls="--", lw=1, label="5th/95th")
        axes[0, col].axvline(np.percentile(c, 95), color="gray", ls="--", lw=1)
        axes[0, col].set_title(f"{name}: bootstrap CAGR ({n} trades, {yrs:.0f}y)")
        axes[0, col].set_xlabel("CAGR %"); axes[0, col].legend(fontsize=8)
        axes[1, col].hist(d, bins=60, color="#d9534f")
        axes[1, col].axvline(np.median(d), color="black", lw=1.5, label=f"median {np.median(d):.1f}%")
        axes[1, col].axvline(-80, color="crimson", ls="--", lw=1, label="ruin -80%")
        axes[1, col].set_title(f"{name}: bootstrap MaxDD")
        axes[1, col].set_xlabel("MaxDD %"); axes[1, col].legend(fontsize=8)
    fig.suptitle("Step 5b — trade-sequence bootstrap (10,000 resamples): outcome distribution, not one path")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "sensitivity_bootstrap.png"), dpi=120)
    print(f"\nWrote {os.path.join(PLOTS, 'sensitivity_bootstrap.png')}")


def main():
    grid = grid_5a()
    adopted = grid[(grid.vix == ADOPTED["vix"]) & (grid.rsi == ADOPTED["rsi"])
                   & (grid.hold == ADOPTED["hold"]) & (grid.delay == ADOPTED["delay"])].iloc[0]
    print("=== STEP 5a — PARAMETER SWEEP (144 configs, full 3x TQQQ MA50) ===")
    print(f"Adopted config (VIX40/RSI35/hold365/delay9): CAGR {adopted['CAGR_%']}%, "
          f"MaxDD {adopted['MaxDD_%']}%, {adopted['trades']} trades, win {adopted['win_%']}%")
    cagr = grid["CAGR_%"]
    print(f"Grid CAGR %: min {cagr.min():.1f} / median {cagr.median():.1f} / "
          f"max {cagr.max():.1f}   (adopted at {adopted['CAGR_%']})")
    print(f"Configs with CAGR > 30%: {(cagr > 30).mean()*100:.0f}% ;  "
          f"CAGR > 20%: {(cagr > 20).mean()*100:.0f}% ;  all positive: {(cagr > 0).all()}")
    print(f"Adopted CAGR percentile within grid: "
          f"{(cagr < adopted['CAGR_%']).mean()*100:.0f}th")
    plot_5a(grid)

    print("\n=== STEP 5b — TRADE-SEQUENCE BOOTSTRAP ===")
    run_5b()


if __name__ == "__main__":
    main()
