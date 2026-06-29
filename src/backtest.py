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
"""

import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
PLOTS = os.path.join(os.path.dirname(__file__), "..", "plots")
LOGS = os.path.join(os.path.dirname(__file__), "..", "logs")
START_CAPITAL = 10_000.0
VIX_THRESHOLD = 40.0
RSI_THRESHOLD = 35.0
RSI_PERIOD = 14
MA_PERIOD = 100
MIN_HOLD_DAYS = 365  # calendar days
ENTRY_DELAY_DAYS = 9  # trading days between signal and entry


def load_yf(path):
    """Load a yfinance-style CSV (3 header rows) -> DataFrame with OHLCV, Date index."""
    df = pd.read_csv(path, skiprows=3, header=None)
    df.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()


def rsi(series, period):
    """RSI using a simple moving average of gains and losses (not Wilder's)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def build_signals():
    """Return a daily DataFrame with all indicators and the entry signal."""
    tqqq = load_yf(os.path.join(DATA, "tqqq_data.csv"))
    vix = load_yf(os.path.join(DATA, "vix_data.csv"))
    spx = load_yf(os.path.join(DATA, "sp500_data.csv"))

    # S&P weekly RSI(14), forward-filled onto daily dates.
    weekly_close = spx["Close"].resample("W-FRI").last()
    weekly_rsi = rsi(weekly_close, RSI_PERIOD)
    spx_daily = pd.DataFrame(index=spx.index)
    spx_daily["spx_close"] = spx["Close"]
    spx_daily["ma100"] = spx["Close"].rolling(MA_PERIOD).mean()
    spx_daily["weekly_rsi"] = weekly_rsi.reindex(spx.index, method="ffill")

    df = pd.DataFrame(index=tqqq.index)
    df["tqqq_open"] = tqqq["Open"]
    df["tqqq_close"] = tqqq["Close"]
    df["vix_close"] = vix["Close"].reindex(tqqq.index)
    df = df.join(spx_daily, how="left")
    df = df.dropna(subset=["tqqq_open", "tqqq_close", "vix_close", "spx_close"])

    df["signal"] = (df["vix_close"] > VIX_THRESHOLD) | (df["weekly_rsi"] < RSI_THRESHOLD)
    return df


def run_backtest(df):
    """Event-driven backtest. Returns (trades DataFrame, daily equity Series).

    Entry: the signal fires on a daily close; the position is bought at the
    close ENTRY_DELAY_DAYS trading days later.
    Exit:  after holding >= MIN_HOLD_DAYS, sell at the close of the first day
    S&P 500 closes below its MA100.
    """
    dates = df.index.to_list()
    n = len(dates)
    cash = START_CAPITAL
    shares = 0.0
    in_pos = False
    entry_date = entry_price = entry_trigger = signal_date = None
    entry_target_idx = None  # index at which a scheduled entry fills
    pending_trigger = None
    pending_signal_date = None
    trades = []
    equity = []

    for i, d in enumerate(dates):
        row = df.loc[d]

        # Fill a scheduled entry at today's close (9 trading days after signal).
        if not in_pos and entry_target_idx == i:
            shares = cash / row["tqqq_close"]
            cash = 0.0
            in_pos = True
            entry_date = d
            entry_price = row["tqqq_close"]
            entry_trigger = pending_trigger
            signal_date = pending_signal_date
            entry_target_idx = None

        # Schedule a new entry only when flat with nothing already pending.
        if not in_pos and entry_target_idx is None and row["signal"]:
            target = i + ENTRY_DELAY_DAYS
            if target < n:
                entry_target_idx = target
                pending_signal_date = d
                reasons = []
                if row["vix_close"] > VIX_THRESHOLD:
                    reasons.append(f"VIX {row['vix_close']:.1f}>40")
                if row["weekly_rsi"] < RSI_THRESHOLD:
                    reasons.append(f"RSI {row['weekly_rsi']:.1f}<35")
                pending_trigger = " + ".join(reasons)

        # Exit at today's close once past the minimum hold and S&P < MA100.
        if in_pos:
            held = (d - entry_date).days
            if held >= MIN_HOLD_DAYS and row["spx_close"] < row["ma100"]:
                cash = shares * row["tqqq_close"]
                trades.append({
                    "Signal_Date": signal_date,
                    "Entry_Date": entry_date,
                    "Trigger": entry_trigger,
                    "Entry_Price": entry_price,
                    "Exit_Date": d,
                    "Exit_Price": row["tqqq_close"],
                    "Return_%": (row["tqqq_close"] / entry_price - 1) * 100,
                    "Capital_After": cash,
                    "Hold_Days": held,
                })
                shares = 0.0
                in_pos = False
                entry_date = None

        equity.append(cash + shares * row["tqqq_close"])

    # Close any open position at the final close for mark-to-market reporting.
    if in_pos:
        last = df.iloc[-1]
        cash = shares * last["tqqq_close"]
        trades.append({
            "Signal_Date": signal_date,
            "Entry_Date": entry_date,
            "Trigger": entry_trigger,
            "Entry_Price": entry_price,
            "Exit_Date": df.index[-1],
            "Exit_Price": last["tqqq_close"],
            "Return_%": (last["tqqq_close"] / entry_price - 1) * 100,
            "Capital_After": cash,
            "Hold_Days": (df.index[-1] - entry_date).days,
            "Open_At_End": True,
        })

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
    df = build_signals()
    trades, equity = run_backtest(df)

    tqqq_bh = buy_hold_equity(df["tqqq_close"])
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
