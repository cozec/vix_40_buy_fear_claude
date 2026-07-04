"""Build a synthetic TQQQ history before its 2010-02-11 inception from QQQ.

TQQQ seeks 3x the *daily* return of the Nasdaq-100. QQQ (1x) is used as the
proxy. For each pre-inception day we set:

    tqqq_daily_return = 3 * qqq_daily_return - daily_drag

using DIVIDEND-ADJUSTED QQQ returns and an annual drag of 2.0%/yr (TQQQ's 0.95%
expense ratio plus a ~1% financing/borrow proxy for the 2x levered exposure).
These assumptions match an externally supplied synthetic series. The result is
chained *backward* from the real TQQQ close on 2010-02-11 so the synthetic tail
joins the real data with no discontinuity. Open/High/Low are approximated by
applying 3x QQQ's intraday move relative to the prior close.

Synthetic-day Volume is set to 0 as a flag.
"""

import pandas as pd

INCEPTION = "2010-02-11"
LEVERAGE = 3.0
ANNUAL_DRAG = 0.020            # 0.95% expense ratio + ~1% financing/borrow proxy
DAILY_DRAG = ANNUAL_DRAG / 252

# --- Load dividend-ADJUSTED QQQ (auto_adjust=True) for return calculation ---
qqq = pd.read_csv("data/qqq_adj_data.csv", index_col="Date", parse_dates=True).sort_index()

# --- Load real TQQQ (yfinance auto_adjust multi-row header) and get anchor ---
tqqq = pd.read_csv("data/tqqq_data.csv", skiprows=[1, 2])
tqqq = tqqq.rename(columns={"Price": "Date"})
tqqq["Date"] = pd.to_datetime(tqqq["Date"])
tqqq = tqqq.set_index("Date").sort_index()[["Open", "High", "Low", "Close", "Volume"]]

anchor_close = tqqq.loc[INCEPTION, "Close"]  # real TQQQ close on inception day

# --- QQQ history strictly before inception, chronological ---
qqq_pre = qqq.loc[qqq.index < INCEPTION].copy()

# QQQ close-to-close return; first row has no prior close -> drop it (can't lever)
qqq_pre["ret"] = qqq_pre["Close"].pct_change()
qqq_pre = qqq_pre.dropna(subset=["ret"])

tqqq_ret = LEVERAGE * qqq_pre["ret"] - DAILY_DRAG

# Chain synthetic close backward from the anchor.
# synth_close[last] should equal anchor / (1 + tqqq_ret[inception_day]); but the
# inception-day return belongs to the real series. So the last synthetic close is
# the value that, compounded one real step, lands on the anchor is not needed —
# we simply chain forward and rescale so the final synthetic close * (1+r_incep)
# matches. Simplest robust method: build a cumulative growth factor then scale so
# the LAST synthetic day sits one QQQ-step below the anchor.
growth = (1.0 + tqqq_ret).cumprod()

# Return that carried real TQQQ from the last synthetic day into inception:
# use QQQ's return on the inception day itself.
incep_qqq_ret = qqq.loc[INCEPTION, "Close"] / qqq.loc[qqq.index < INCEPTION, "Close"].iloc[-1] - 1
incep_tqqq_ret = LEVERAGE * incep_qqq_ret - DAILY_DRAG
last_synth_close = anchor_close / (1.0 + incep_tqqq_ret)

# Scale cumulative growth so its final value == last_synth_close.
synth_close = growth / growth.iloc[-1] * last_synth_close

# --- Approximate O/H/L via 3x QQQ intraday move vs prior QQQ close ---
prior_qqq_close = qqq_pre["Close"].shift(1)
# For the first retained row, shift(1) is NaN; use QQQ Open as its own prior ref.
prior_qqq_close = prior_qqq_close.fillna(qqq_pre["Open"])
prev_synth_close = synth_close.shift(1).fillna(last_synth_close)  # placeholder, fixed below

# Rebuild O/H/L off the previous *synthetic* close, scaling QQQ's intraday ratios.
prev_close_series = synth_close.shift(1)
# first synthetic day's prior close: infer from its own return
prev_close_series.iloc[0] = synth_close.iloc[0] / (1.0 + tqqq_ret.iloc[0])

def scaled(col):
    ratio = qqq_pre[col] / prior_qqq_close - 1.0
    return prev_close_series * (1.0 + LEVERAGE * ratio)

synth = pd.DataFrame({
    "Open": scaled("Open"),
    "High": scaled("High"),
    "Low": scaled("Low"),
    "Close": synth_close,
    "Volume": 0,
}, index=qqq_pre.index)

# Enforce High/Low envelope so OHLC is internally consistent.
synth["High"] = synth[["Open", "High", "Low", "Close"]].max(axis=1)
synth["Low"] = synth[["Open", "High", "Low", "Close"]].min(axis=1)
synth.index.name = "Date"

# --- Combine synthetic (pre) + real (inception onward), clean format ---
combined = pd.concat([synth, tqqq[["Open", "High", "Low", "Close", "Volume"]]])
combined = combined[~combined.index.duplicated(keep="last")].sort_index()

synth.to_csv("data/tqqq_synthetic_pre2010.csv")
combined.to_csv("data/tqqq_synthetic_full.csv")

print(f"Synthetic rows (pre-{INCEPTION}): {len(synth)}")
print(f"  range: {synth.index.min().date()} -> {synth.index.max().date()}")
print(f"  last synthetic close: {synth['Close'].iloc[-1]:.6f}")
print(f"  real inception close: {anchor_close:.6f}  (implied step {incep_tqqq_ret:+.4%})")
print(f"Combined rows: {len(combined)}  ({combined.index.min().date()} -> {combined.index.max().date()})")
print(combined.loc["2010-02-09":"2010-02-12"].round(6))
