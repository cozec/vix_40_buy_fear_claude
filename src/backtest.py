"""
VIX > 40 "Buy the Fear" backtest on TQQQ.

Strategy
--------
Signal : VIX close > 40 OR S&P 500 weekly RSI(14) < 35.
Entry  : Buy TQQQ at the close 9 trading days after the signal.
Exit   : Hold at least 1 year, then exit on the first day S&P 500 close < MA100.

Rules / assumptions
-------------------
- One position at a time. Signals that fire while already invested (or while an
  entry is already scheduled) are ignored.
- Signals are evaluated on the daily close; the entry fills at the close 9
  trading days later; the exit fills at the close of the trigger day.
- Full capital is deployed each trade and compounds. Start capital $10,000.
- Benchmark: buy & hold TQQQ over the same window.
- Tradable window is bounded by TQQQ / VIX data: 2010-02-11 onward.

Engine parameters
-----------------
`run_strategy` separates the *trend/signal* instrument (RSI + MA exit are
computed on it — the S&P 500 by default) from the *traded* instrument (TQQQ by
default), and exposes every knob as an argument so variants can be swept without
copy-pasting code (see IMPROVEMENT_PLAN.md Step 0.2). Calling it with the module
defaults reproduces the locked baseline.
"""

import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
PLOTS = os.path.join(os.path.dirname(__file__), "..", "plots")
LOGS = os.path.join(os.path.dirname(__file__), "..", "logs")
START_CAPITAL = 10_000.0

# Baseline defaults (the locked reference variant).
VIX_THRESHOLD = 40.0
RSI_THRESHOLD = 35.0
RSI_PERIOD = 14
RSI_METHOD = "sma"      # "sma" (simple) or "wilder"
RSI_FREQ = "weekly"     # "weekly" (W-FRI) or "daily"
MA_PERIOD = 100
MIN_HOLD_DAYS = 365     # calendar days
ENTRY_DELAY_DAYS = 9    # trading days between signal and entry
LEVERAGE = 1.0          # daily-rebalanced leverage applied to the traded series
ANNUAL_DRAG = 0.0       # annual fee/decay drag when leverage != 1 (fraction/yr)


def load_yf(path):
    """Load a yfinance-style CSV (3 header rows) -> DataFrame with OHLCV, Date index."""
    df = pd.read_csv(path, skiprows=3, header=None)
    df.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()


def load_index(path):
    """Load a standard-header OHLCV CSV (e.g. long-history ^GSPC), Date index.

    Handles tz-aware Date strings; returns a naive DatetimeIndex.
    """
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None).dt.normalize()
    return df.set_index("Date").sort_index()


def rsi(series, period, method="sma"):
    """RSI. method='sma' uses a simple MA of gains/losses; 'wilder' uses Wilder smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    if method == "wilder":
        avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    else:
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def build_signals(trade, trend, vix=None, *, vix_threshold=VIX_THRESHOLD,
                  rsi_threshold=RSI_THRESHOLD, rsi_period=RSI_PERIOD,
                  rsi_method=RSI_METHOD, rsi_freq=RSI_FREQ, ma_period=MA_PERIOD):
    """Build a daily signal frame.

    Parameters
    ----------
    trade : DataFrame with 'Open'/'Close' for the *traded* instrument.
    trend : DataFrame with 'Close' for the *trend/signal* instrument (RSI + MA).
    vix   : optional DataFrame with 'Close'; if None the VIX leg is disabled.
    """
    close_r = trend["Close"].resample("W-FRI").last() if rsi_freq == "weekly" else trend["Close"]
    trend_rsi = rsi(close_r, rsi_period, rsi_method)

    tr = pd.DataFrame(index=trend.index)
    tr["trend_close"] = trend["Close"]
    tr["ma"] = trend["Close"].rolling(ma_period).mean()
    tr["rsi"] = trend_rsi.reindex(trend.index, method="ffill")

    df = pd.DataFrame(index=trade.index)
    df["trade_open"] = trade["Open"]
    df["trade_close"] = trade["Close"]
    df["vix_close"] = vix["Close"].reindex(trade.index) if vix is not None else np.nan
    df = df.join(tr, how="left")
    df = df.dropna(subset=["trade_open", "trade_close", "trend_close"])

    vix_leg = (df["vix_close"] > vix_threshold) if vix is not None else False
    df["signal"] = vix_leg | (df["rsi"] < rsi_threshold)
    df.attrs["has_vix"] = vix is not None
    return df


def _apply_leverage(close, leverage, annual_drag):
    """Return a daily-rebalanced levered price series from a 1x close series."""
    if leverage == 1.0 and annual_drag == 0.0:
        return close
    ret = close.pct_change()
    lev = (leverage * ret - annual_drag / 252.0).fillna(0.0)
    return close.iloc[0] * (1.0 + lev).cumprod()


def run_backtest(df, *, min_hold_days=MIN_HOLD_DAYS, entry_delay_days=ENTRY_DELAY_DAYS,
                 leverage=LEVERAGE, annual_drag=ANNUAL_DRAG, vix_threshold=VIX_THRESHOLD,
                 rsi_threshold=RSI_THRESHOLD, exit_mode="trend", trail_pct=0.30,
                 scale_levels=(1.0, 2.0), capital_fraction=1.0, entry_offsets=None,
                 catastrophe_ret=None, catastrophe_cooldown_days=0):
    """Event-driven backtest. Returns (trades DataFrame, daily equity Series).

    Entry: signal fires on a daily close; position is bought at the close
    `entry_delay_days` trading days later. Leverage (with `annual_drag`) is
    applied to the traded close series.

    Exit modes (Step 2 — re-engineer the exit):
      "trend"       : baseline. After held >= min_hold_days, exit on the first
                      day the trend instrument closes below its MA.
      "trail"       : pure trailing stop — exit when the traded close falls
                      `trail_pct` below its running peak since entry (no min-hold).
      "trend_trail" : hybrid — exit on the trend rule OR the trailing stop,
                      whichever fires first (trailing stop active immediately).
      "scaleout"    : sell 1/3 of the original position at each return in
                      `scale_levels` (e.g. +100%, +200%); the remainder exits on
                      the trailing stop or the trend rule, whichever fires first.

    Sizing (Step 3 — size for survival):
      capital_fraction : fraction of equity deployed into the traded instrument
                         each trade; the remainder stays in cash (0% reserve).
                         1.0 = full-capital (baseline).
      entry_offsets    : trading-day offsets from the signal at which to buy
                         equal tranches (scale-in). None -> a single lump at
                         `entry_delay_days` (baseline). E.g. (0, 5, 10) buys 1/3
                         on the signal day, 1/3 five days later, 1/3 ten days
                         later. The 1-year hold clock starts at the FIRST fill;
                         entry price is the tranche-weighted average cost.

    Catastrophe rule (Step 4 — tail protection):
      catastrophe_ret : if set, exit immediately (bypassing the min-hold) at the
                        close of any held day whose traded-instrument daily return
                        is <= this value. For a 3x instrument, -0.30 ~ a -10% day
                        in the 1x underlying. None = off (baseline).
      catastrophe_cooldown_days : trading days to stay flat after a catastrophe
                        exit before a new signal may schedule an entry.

    Every trade record includes `MaxDD_From_Buy_%` = worst close-to-entry dip
    while holding (matches src/plot_trades.py), `Peak_Return_%`, and `Exit_Reason`.
    """
    df = df.copy()
    df["trade_close"] = _apply_leverage(df["trade_close"], leverage, annual_drag)
    rets = df["trade_close"].pct_change().to_numpy()  # daily return of traded series
    has_vix = df.attrs.get("has_vix", True)
    offsets = tuple(entry_offsets) if entry_offsets is not None else (entry_delay_days,)
    cooldown_until = -1  # index before which no new entry may be scheduled

    dates = df.index.to_list()
    n = len(dates)
    cash = START_CAPITAL
    shares = 0.0
    in_pos = False
    entry_date = entry_price = entry_trigger = signal_date = None
    invested_total = shares_bought = orig_shares = peak_price = min_price = None
    proceeds = scaled = 0
    pending_fills = {}       # fill index -> cash amount for that tranche
    pending_trigger = None
    pending_signal_date = None
    trades = []
    equity = []

    def record(exit_date, exit_price, held, reason, open_at_end=False):
        entry_px = invested_total / shares_bought
        trades.append({
            "Signal_Date": signal_date,
            "Entry_Date": entry_date,
            "Trigger": entry_trigger,
            "Entry_Price": entry_px,
            "Exit_Date": exit_date,
            "Exit_Price": exit_price,
            "Return_%": (proceeds / invested_total - 1) * 100,
            "Capital_After": cash,
            "Hold_Days": held,
            "Peak_Return_%": (peak_price / entry_px - 1) * 100,
            "MaxDD_From_Buy_%": (min_price / entry_px - 1) * 100,
            "Exit_Reason": reason,
            **({"Open_At_End": True} if open_at_end else {}),
        })

    for i, d in enumerate(dates):
        row = df.loc[d]
        price = row["trade_close"]

        # Schedule a new entry only when flat with nothing pending or open,
        # and not inside a post-catastrophe cooldown.
        if not in_pos and not pending_fills and i >= cooldown_until and row["signal"]:
            fills = [i + off for off in offsets if i + off < n]
            if fills:
                budget = capital_fraction * cash
                amt = budget / len(fills)
                pending_fills = {idx: amt for idx in fills}
                pending_signal_date = d
                reasons = []
                if has_vix and row["vix_close"] > vix_threshold:
                    reasons.append(f"VIX {row['vix_close']:.1f}>{vix_threshold:.0f}")
                if row["rsi"] < rsi_threshold:
                    reasons.append(f"RSI {row['rsi']:.1f}<{rsi_threshold:.0f}")
                pending_trigger = " + ".join(reasons)

        # Fill any tranche scheduled for today.
        if i in pending_fills:
            invest = pending_fills.pop(i)
            bought = invest / price
            shares += bought
            cash -= invest
            if not in_pos:                       # first tranche opens the position
                in_pos = True
                entry_date = d
                signal_date = pending_signal_date
                entry_trigger = pending_trigger
                invested_total = 0.0
                shares_bought = 0.0
                proceeds = 0.0
                scaled = 0
                peak_price = price
                min_price = price
            invested_total += invest
            shares_bought += bought
            orig_shares = shares_bought

        # Manage an open position.
        if in_pos:
            held = (d - entry_date).days
            peak_price = max(peak_price, price)
            min_price = min(min_price, price)
            entry_px = invested_total / shares_bought

            # Catastrophe rule: an extreme single-day drop forces an exit and
            # starts a cooldown, overriding the min-hold and any pending tranche.
            cat_exit = (catastrophe_ret is not None and held >= 1
                        and rets[i] <= catastrophe_ret)

            trend_exit = held >= min_hold_days and row["trend_close"] < row["ma"]
            trail_exit = price <= peak_price * (1.0 - trail_pct)

            # Scale-out: bank a tranche each time a return level is first reached.
            if not cat_exit and exit_mode == "scaleout" and scaled < len(scale_levels):
                if price / entry_px - 1.0 >= scale_levels[scaled]:
                    sell = (orig_shares / 3.0) * price
                    cash += sell
                    proceeds += sell
                    shares -= orig_shares / 3.0
                    scaled += 1

            if exit_mode == "trend":
                do_exit = trend_exit
            elif exit_mode == "trail":
                do_exit = trail_exit
            else:  # "trend_trail" or "scaleout"
                do_exit = trend_exit or trail_exit

            if cat_exit:
                sell = shares * price
                cash += sell
                proceeds += sell
                shares = 0.0
                pending_fills = {}
                record(d, price, held, "catastrophe")
                in_pos = False
                entry_date = None
                cooldown_until = i + catastrophe_cooldown_days
            elif do_exit and not pending_fills:   # don't exit mid scale-in
                sell = shares * price
                cash += sell
                proceeds += sell
                shares = 0.0
                record(d, price, held, "trend" if trend_exit else "trail")
                in_pos = False
                entry_date = None

        equity.append(cash + shares * price)

    # Mark any open position to the final close for reporting.
    if in_pos:
        last_px = df.iloc[-1]["trade_close"]
        sell = shares * last_px
        cash += sell
        proceeds += sell
        shares = 0.0
        record(df.index[-1], last_px, (df.index[-1] - entry_date).days, "eod", open_at_end=True)

    return pd.DataFrame(trades), pd.Series(equity, index=df.index, name="strategy")


def metrics(equity, bench_returns=None):
    """Compute professional performance metrics from a daily equity curve."""
    rets = equity.pct_change().dropna()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    dd = equity / equity.cummax() - 1
    max_dd = dd.min()
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else np.nan

    alpha = beta = np.nan
    if bench_returns is not None:
        aligned = pd.concat([rets, bench_returns], axis=1).dropna()
        aligned.columns = ["p", "b"]
        if len(aligned) > 2 and aligned["b"].var() > 0:
            beta = aligned["p"].cov(aligned["b"]) / aligned["b"].var()
            alpha = (aligned["p"].mean() - beta * aligned["b"].mean()) * 252

    return {
        "Final Equity": equity.iloc[-1],
        "Return %": total_return * 100,
        "CAGR %": cagr * 100,
        "Max DD %": max_dd * 100,
        "Sharpe": sharpe,
        "Alpha": alpha,
        "Beta": beta,
    }


def buy_hold_equity(price):
    """Daily equity for buying & holding `price` with START_CAPITAL."""
    return START_CAPITAL * price / price.iloc[0]


def main():
    # Baseline: signal/trend = S&P 500, traded = real TQQQ (already 3x), VIX enabled.
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))

    df = build_signals(tqqq, spx, vix)
    trades, equity = run_backtest(df)

    tqqq_bh = buy_hold_equity(df["trade_close"])
    tqqq_bh_rets = tqqq_bh.pct_change().dropna()

    strat_m = metrics(equity, tqqq_bh_rets)
    tqqq_m = metrics(tqqq_bh, tqqq_bh_rets)

    summary = pd.DataFrame({
        "VIX40 Strategy (TQQQ)": strat_m,
        "Buy & Hold TQQQ": tqqq_m,
    }).T
    summary = summary.sort_values("Final Equity", ascending=False)

    os.makedirs(RESULTS, exist_ok=True)
    os.makedirs(PLOTS, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    trades.to_csv(os.path.join(RESULTS, "tqqq_vix40_trades.csv"), index=False)
    summary.to_csv(os.path.join(RESULTS, "performance_summary.csv"))

    # Equity curve plot.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(equity.index, equity, label="VIX40 Strategy (TQQQ)", lw=1.8)
    ax.plot(tqqq_bh.index, tqqq_bh, label="Buy & Hold TQQQ", lw=1.0, alpha=0.8)
    ax.set_yscale("log")
    ax.set_title("VIX > 40 Buy-the-Fear vs Buy & Hold (start $10,000)")
    ax.set_ylabel("Equity ($, log scale)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "equity_curve.png"), dpi=120)

    # Console / log output.
    pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
    print("\n=== TRADES ===")
    print(trades.to_string(index=False))
    print("\n=== PERFORMANCE SUMMARY ===")
    print(summary.to_string())
    print(f"\nWindow: {df.index[0].date()} -> {df.index[-1].date()}  ({len(df)} days)")
    print(f"Number of trades: {len(trades)}")
    if len(trades):
        wins = (trades["Return_%"] > 0).sum()
        print(f"Win rate: {wins}/{len(trades)} = {wins/len(trades)*100:.1f}%")

    with open(os.path.join(LOGS, "backtest_run.txt"), "w") as f:
        f.write(trades.to_string(index=False))
        f.write("\n\n")
        f.write(summary.to_string())


if __name__ == "__main__":
    main()
