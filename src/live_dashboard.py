"""
LIVE local dashboard for the VIX>40 "buy the fear" TQQQ strategy.

Monitors the strategy's trigger conditions in near-real time during market hours,
reusing the signal engine in backtest.py. Quotes come from Yahoo (yfinance,
~15-min delayed); everything falls back to the last CSV close when the market is
closed or a fetch fails, so the page never breaks.

Run:
    cd src && PORT=8000 ../.venv/bin/python live_dashboard.py
    # open http://localhost:8000   (avoid 5000 on macOS — AirPlay)

Optional env: ENTRY_OFFSET (default 9) — which entry option the position/exit
panel assumes (+3 / +9 trading days); the entry-timers panel always shows all
three (+3d / +9d / MA5-confirmation).

Shows: market status + countdown · VIX gauge (vs 40) · S&P weekly RSI gauge
(provisional intraday, vs 35) · master ARMED/FIRING signal · open position &
MA50-exit state · -40% catastrophe monitor · entry timers · context chart.
"""

import os
import sys
import json
import time
import socket
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, render_template_string, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
import download_data  # noqa: E402

socket.setdefaulttimeout(8)  # cap any yfinance hang

# --- config ---------------------------------------------------------------
MA_PERIOD = 50                 # adopted exit MA
CATASTROPHE_RET = -0.40        # single-day TQQQ circuit-breaker (~ QQQ -13%)
CATA_QQQ_REF = -13.0           # underlying reference for the -40% 3x move
ENTRY_OFFSET = int(os.environ.get("ENTRY_OFFSET", "9"))
CONFIRM_MA, CONFIRM_CAP = 5, 20
QUOTE_TTL = 45                 # seconds; browser polls at the same cadence
AUTO_UPDATE = os.environ.get("AUTO_UPDATE", "1") != "0"   # daily CSV self-refresh
UPDATE_HOUR = int(os.environ.get("UPDATE_HOUR", "18"))    # 18:00 ET (after close)
EASTERN = ZoneInfo("America/New_York")
TICKERS = ("^VIX", "TQQQ", "^GSPC", "QQQ")
CSV_MAP = {"^VIX": "vix", "TQQQ": "tqqq", "^GSPC": "spx"}   # QQQ has no local CSV

app = Flask(__name__)

_QUOTE_CACHE = {"ts": 0.0, "data": None}
_DERIVED_CACHE = {"key": None, "data": None}


# --- data loading (cached by CSV mtime) -----------------------------------
CSV_FILES = {"tqqq": "tqqq_data.csv", "vix": "vix_data.csv", "spx": "sp500_data.csv"}


def _paths():
    return {k: os.path.join(bt.DATA, fn) for k, fn in CSV_FILES.items()}


def load_frames():
    """Load the three CSV frames; cached and reused (they change ~daily)."""
    frames = {}
    for key, path in _paths().items():
        frames[key] = bt.load_yf(path)
    return frames


def derived(frames):
    """build_signals + run_backtest, cached by CSV mtimes (recomputed on refresh)."""
    key = tuple(os.path.getmtime(p) for p in _paths().values())
    if _DERIVED_CACHE["key"] == key and _DERIVED_CACHE["data"] is not None:
        return _DERIVED_CACHE["data"]
    sig = bt.build_signals(frames["tqqq"], frames["spx"], frames["vix"], ma_period=MA_PERIOD)
    trades, _ = bt.run_backtest(sig, catastrophe_ret=CATASTROPHE_RET,
                                entry_delay_days=ENTRY_OFFSET)
    data = {"sig": sig, "trades": trades}
    _DERIVED_CACHE.update(key=key, data=data)
    return data


# --- live quotes (TTL-cached, 3-tier fallback) ----------------------------
def live_quotes(frames):
    now = time.time()
    if _QUOTE_CACHE["data"] is not None and now - _QUOTE_CACHE["ts"] < QUOTE_TTL:
        return _QUOTE_CACHE["data"]

    quotes, any_live = {}, False
    for t in TICKERS:
        last = prev = None
        src = "csv_fallback"
        try:                                   # tier 1: fast_info
            fi = yf.Ticker(t).fast_info
            last = float(fi.last_price)
            prev = float(fi.previous_close)
            src, any_live = "live", True
        except Exception:
            try:                               # tier 2: 1-minute history
                h = yf.Ticker(t).history(period="2d", interval="1m")
                c = h["Close"].dropna()
                if len(c):
                    last = float(c.iloc[-1])
                    src, any_live = "live_1m", True
            except Exception:
                pass
        fr = frames.get(CSV_MAP.get(t))        # tier 3: last CSV close
        if fr is not None and len(fr):
            if last is None:
                last = float(fr["Close"].iloc[-1])
                src = "csv_fallback"
            if prev is None:
                prev = float(fr["Close"].iloc[-2]) if len(fr) > 1 else last
        quotes[t] = {"last": last, "prev": prev, "source": src}

    data = {"quotes": quotes, "any_live": any_live}
    _QUOTE_CACHE.update(ts=now, data=data)
    return data


# --- provisional intraday weekly RSI --------------------------------------
def provisional_weekly_rsi(spx_close, live_spx, today_date, inject):
    """Weekly RSI(14, SMA) matching build_signals; the in-progress week uses the
    live S&P quote when `inject` (a weekday session). Returns (value, week_ending,
    provisional)."""
    weekly = spx_close.resample("W-FRI").last()
    provisional = False
    if inject and live_spx is not None:
        this_fri = pd.Period(pd.Timestamp(today_date), freq="W-FRI").end_time.normalize()
        weekly.loc[this_fri] = float(live_spx)   # replace partial / append current week
        weekly = weekly.sort_index()
        provisional = True
    r = bt.rsi(weekly, bt.RSI_PERIOD, "sma")
    return float(r.iloc[-1]), weekly.index[-1].strftime("%Y-%m-%d"), provisional


# --- market hours ----------------------------------------------------------
def _next_weekday_open(now_et):
    d = now_et
    while True:
        d = (d + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
        if d.weekday() < 5:
            return d


def _daily_updater():
    """Background daemon: refresh the CSVs now if stale, then daily at UPDATE_HOUR ET."""
    def refresh(tag):
        try:
            download_data.main()
            _DERIVED_CACHE.update(key=None, data=None)   # force recompute next request
            print(f"[auto-update] {tag} CSV refresh done {datetime.now(EASTERN):%Y-%m-%d %H:%M ET}")
        except Exception as e:
            print(f"[auto-update] {tag} refresh failed: {e}")

    try:  # catch-up refresh at startup if data is behind
        last = bt.load_yf(_paths()["tqqq"]).index[-1].date()
        if np.busday_count(last, datetime.now(EASTERN).date()) > 0:
            refresh("startup")
    except Exception as e:
        print(f"[auto-update] startup check failed: {e}")

    while True:
        now = datetime.now(EASTERN)
        nxt = now.replace(hour=UPDATE_HOUR, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep((nxt - now).total_seconds())
        refresh("daily")


def market_status(now_et):
    wd = now_et.weekday() < 5
    open_t = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if wd and open_t <= now_et < close_t:
        state, nxt, when = "OPEN", "close", close_t
    elif wd and now_et < open_t:
        state, nxt, when = "PREMARKET", "open", open_t
    elif wd and now_et >= close_t:
        state, nxt, when = "AFTERHOURS", "open", _next_weekday_open(now_et)
    else:
        state, nxt, when = "CLOSED", "open", _next_weekday_open(now_et)
    return {
        "state": state, "is_open": state == "OPEN", "next_event": nxt,
        "next_event_eastern": when.strftime("%Y-%m-%d %H:%M ET"),
        "seconds_to_next": int((when - now_et).total_seconds()),
        "session_today": state in ("OPEN", "AFTERHOURS"),
    }


# --- helpers ---------------------------------------------------------------
def _bday(d, n):
    return pd.bdate_range(start=pd.Timestamp(d), periods=n + 1)[-1].date()


def _signal_run_start(sig):
    """Start date of the trailing contiguous True run in the signal column, else None."""
    s = sig["signal"]
    if not bool(s.iloc[-1]):
        return None
    i = len(s) - 1
    while i > 0 and bool(s.iloc[i - 1]):
        i -= 1
    return s.index[i]


# --- state payload ---------------------------------------------------------
def build_state():
    now_utc = datetime.now(ZoneInfo("UTC"))
    now_et = now_utc.astimezone(EASTERN)
    today = now_et.date()
    mkt = market_status(now_et)

    try:
        frames = load_frames()
    except Exception as e:
        return {"error": f"Could not load data CSVs ({e}). Run: python src/download_data.py",
                "market": mkt, "server_time_utc": now_utc.isoformat()}

    d = derived(frames)
    sig, trades = d["sig"], d["trades"]
    q = live_quotes(frames)
    Q = q["quotes"]

    def qval(t, k="last"):
        v = Q.get(t, {}).get(k)
        return None if v is None else float(v)

    vix_live, vix_prev = qval("^VIX"), qval("^VIX", "prev")
    spx_live = qval("^GSPC")
    tqqq_live, tqqq_prev = qval("TQQQ"), qval("TQQQ", "prev")
    qqq_live, qqq_prev = qval("QQQ"), qval("QQQ", "prev")

    # Inject the live S&P into the current week only when it's a weekday AND the
    # quote is genuinely live (not a stale CSV fallback); otherwise report the
    # last completed weekly RSI (matches build_signals exactly).
    spx_src = Q.get("^GSPC", {}).get("source", "csv_fallback")
    inject = (now_et.weekday() < 5) and (spx_src in ("live", "live_1m"))
    rsi_val, week_ending, provisional = provisional_weekly_rsi(
        frames["spx"]["Close"], spx_live, today, inject)

    vix_hit = vix_live is not None and vix_live > bt.VIX_THRESHOLD
    rsi_hit = rsi_val < bt.RSI_THRESHOLD
    firing = bool(vix_hit or rsi_hit)
    legs = []
    if vix_live is not None:
        legs.append(f"VIX {vix_live:.1f}{'>' if vix_hit else '<'}{bt.VIX_THRESHOLD:.0f}")
    legs.append(f"RSI {rsi_val:.1f}{'<' if rsi_hit else '>'}{bt.RSI_THRESHOLD:.0f}")

    last_csv_date = frames["tqqq"].index[-1].date()
    days_stale = int(np.busday_count(last_csv_date, today))

    # --- position / exit ---
    last = trades.iloc[-1]
    in_pos = bool(last.get("Open_At_End") is True)
    spx_ma50 = float(frames["spx"]["Close"].rolling(MA_PERIOD).mean().iloc[-1])
    position = {"in_position": in_pos, "assumed_entry_offset": ENTRY_OFFSET,
                "spx_live": spx_live, "spx_ma50": round(spx_ma50, 2)}
    if in_pos:
        entry_date = pd.Timestamp(last["Entry_Date"]).date()
        entry_price = float(last["Entry_Price"])
        hold_days = (today - entry_date).days
        exit_armed = hold_days >= bt.MIN_HOLD_DAYS
        below = spx_live is not None and spx_live < spx_ma50
        position.update(
            entry_date=entry_date.strftime("%Y-%m-%d"), entry_price=round(entry_price, 4),
            tqqq_live=tqqq_live,
            unrealized_pct=None if tqqq_live is None else round((tqqq_live / entry_price - 1) * 100, 1),
            hold_days=hold_days, min_hold_days=bt.MIN_HOLD_DAYS,
            hold_progress_pct=round(min(100.0, hold_days / bt.MIN_HOLD_DAYS * 100), 1),
            min_hold_left=max(0, bt.MIN_HOLD_DAYS - hold_days), exit_armed=exit_armed,
            ma50_distance_pct=None if spx_live is None else round((spx_live / spx_ma50 - 1) * 100, 2),
            below_ma50=below, exit_condition_met=bool(exit_armed and below),
            trigger=str(last["Trigger"]))

    # --- catastrophe ---
    def day_pct(last_, prev_):
        return None if (last_ is None or not prev_) else round((last_ / prev_ - 1) * 100, 2)
    tqqq_day = day_pct(tqqq_live, tqqq_prev)
    catastrophe = {
        "tqqq_day_change_pct": tqqq_day, "threshold_pct": CATASTROPHE_RET * 100,
        "qqq_day_change_pct": day_pct(qqq_live, qqq_prev), "qqq_ref_pct": CATA_QQQ_REF,
        "breach": bool(tqqq_day is not None and tqqq_day <= CATASTROPHE_RET * 100),
        "headroom_pct": None if tqqq_day is None else round(tqqq_day - CATASTROPHE_RET * 100, 1)}

    # --- entry timers (only when firing & flat) ---
    timers = {"active": False}
    if firing and not in_pos:
        sd = _signal_run_start(sig) or pd.Timestamp(today)
        sd_date = sd.date() if hasattr(sd, "date") else sd
        tqqq_now = tqqq_live if tqqq_live is not None else float(frames["tqqq"]["Close"].iloc[-1])
        tqqq_ma5 = float(frames["tqqq"]["Close"].rolling(CONFIRM_MA).mean().iloc[-1])
        dsince = int(np.busday_count(sd_date, today))

        def leg(offset):
            tgt = _bday(sd_date, offset)
            return {"target_date": tgt.strftime("%Y-%m-%d"),
                    "trading_days_left": max(0, int(np.busday_count(today, tgt))),
                    "due": today >= tgt}
        timers = {
            "active": True, "signal_date": sd_date.strftime("%Y-%m-%d"),
            "plus3": leg(3), "plus9": leg(9),
            "ma5_confirm": {"tqqq": round(tqqq_now, 4), "tqqq_ma5": round(tqqq_ma5, 4),
                            "confirmed": bool(tqqq_now > tqqq_ma5), "days_since_signal": dsince,
                            "cap": CONFIRM_CAP, "expired": dsince > CONFIRM_CAP}}

    return {
        "server_time_utc": now_utc.isoformat(),
        "as_of_eastern": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
        "market": mkt,
        "quotes_ok": q["any_live"], "quote_source": "live" if q["any_live"] else "csv_fallback",
        "data_freshness": {"last_csv_date": last_csv_date.strftime("%Y-%m-%d"),
                           "days_stale": days_stale, "stale_warning": days_stale > 4},
        "trigger_vix": {"value": None if vix_live is None else round(vix_live, 2),
                        "threshold": bt.VIX_THRESHOLD, "hit": vix_hit,
                        "prev_close": None if vix_prev is None else round(vix_prev, 2),
                        "day_change": None if (vix_live is None or not vix_prev) else round(vix_live - vix_prev, 2)},
        "trigger_rsi": {"value": round(rsi_val, 2), "threshold": bt.RSI_THRESHOLD, "hit": rsi_hit,
                        "provisional": provisional, "week_ending": week_ending,
                        "spx_live": None if spx_live is None else round(spx_live, 2)},
        "master_signal": {"state": "FIRING" if firing else "ARMED", "firing": firing,
                          "legs": {"vix": vix_hit, "rsi": rsi_hit}, "legs_text": " · ".join(legs)},
        "position": position, "catastrophe": catastrophe, "entry_timers": timers,
        "thresholds": {"vix": bt.VIX_THRESHOLD, "rsi": bt.RSI_THRESHOLD,
                       "ma_period": MA_PERIOD, "catastrophe": CATASTROPHE_RET * 100},
    }


# --- history payload (context chart) --------------------------------------
def _series(s):
    return [None if pd.isna(v) else round(float(v), 4) for v in s]


def _entry_candidates(close, ma5, all_dates, sig_date):
    """The three entry options for a signal: +3d, +9d, MA5-confirmation."""
    try:
        si = all_dates.index(pd.Timestamp(sig_date))
    except ValueError:
        return None
    out = {}
    for lbl, off in (("plus3", 3), ("plus9", 9)):
        j = min(si + off, len(all_dates) - 1)
        out[lbl] = {"date": all_dates[j].strftime("%Y-%m-%d"), "price": round(float(close.iloc[j]), 4)}
    j = min(si + CONFIRM_CAP, len(all_dates) - 1)
    for k in range(si + 1, min(si + CONFIRM_CAP + 1, len(all_dates))):
        if close.iloc[k] > ma5.iloc[k]:
            j = k
            break
    out["ma5"] = {"date": all_dates[j].strftime("%Y-%m-%d"), "price": round(float(close.iloc[j]), 4)}
    return out


def build_history(window=360):
    frames = load_frames()
    d = derived(frames)
    sig, trades = d["sig"], d["trades"]
    df = sig.iloc[-window:]
    tqqq = frames["tqqq"].reindex(df.index)
    dates = [x.strftime("%Y-%m-%d") for x in df.index]
    start = df.index[0]
    holidays = [x.strftime("%Y-%m-%d")
                for x in pd.bdate_range(start, df.index[-1]) if x not in set(df.index)]

    close_full = frames["tqqq"]["Close"]
    ma5_full = close_full.rolling(CONFIRM_MA).mean()
    all_dates = frames["tqqq"].index.to_list()
    tl = []
    for _, t in trades.iterrows():
        if pd.Timestamp(t["Exit_Date"]) < start:
            continue
        tl.append({"signal_date": pd.Timestamp(t["Signal_Date"]).strftime("%Y-%m-%d"),
                   "entry_date": pd.Timestamp(t["Entry_Date"]).strftime("%Y-%m-%d"),
                   "entry_price": round(float(t["Entry_Price"]), 4),
                   "exit_date": pd.Timestamp(t["Exit_Date"]).strftime("%Y-%m-%d"),
                   "exit_price": round(float(t["Exit_Price"]), 4),
                   "ret": round(float(t["Return_%"]), 1), "trigger": str(t["Trigger"]),
                   "open": bool(t.get("Open_At_End") is True),
                   "entries": _entry_candidates(close_full, ma5_full, all_dates, t["Signal_Date"])})
    return {"dates": dates, "holidays": holidays,
            "tqqq": _series(df["trade_close"]), "tqqq_open": _series(tqqq["Open"]),
            "tqqq_high": _series(tqqq["High"]), "tqqq_low": _series(tqqq["Low"]),
            "vix": _series(df["vix_close"]), "rsi": _series(df["rsi"]),
            "trades": tl, "thresholds": {"vix": bt.VIX_THRESHOLD, "rsi": bt.RSI_THRESHOLD}}


# --- routes ----------------------------------------------------------------
@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/api/state")
def api_state():
    try:
        return jsonify(build_state())
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"})


@app.route("/api/history")
def api_history():
    try:
        return jsonify(build_history())
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"})


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VIX&gt;40 Buy-the-Fear · Live Monitor</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root{--bg:#0f1419;--card:#1a2029;--ink:#e6edf3;--muted:#9aa7b4;--line:#2d333b;
        --accent:#f0883e;--green:#3fb950;--red:#f85149;--blue:#58a6ff;--amber:#e3b341;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;}
  .wrap{max-width:1180px;margin:0 auto;padding:20px 18px 60px}
  .hdr{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-bottom:6px}
  h1{font-size:21px;margin:0}
  .muted{color:var(--muted);font-size:12.5px}
  .pill{display:inline-block;padding:3px 12px;border-radius:20px;font-size:12.5px;font-weight:700}
  .pill.open{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.45)}
  .pill.closed{background:rgba(154,167,180,.12);color:var(--muted);border:1px solid var(--line)}
  .pill.pre{background:rgba(227,179,65,.14);color:var(--amber);border:1px solid rgba(227,179,65,.4)}
  .banner{border-radius:10px;padding:8px 13px;font-size:12.5px;margin:8px 0}
  .banner.warn{background:rgba(227,179,65,.10);border:1px solid rgba(227,179,65,.4);color:#e8d3a0}
  .banner.err{background:rgba(248,81,73,.10);border:1px solid rgba(248,81,73,.4);color:#f0b3b0}
  .grid{display:grid;gap:12px;margin:12px 0}
  .g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
  .g3{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
  .card h3{margin:0 0 8px;font-size:11px;color:var(--muted);font-weight:600;letter-spacing:.5px;text-transform:uppercase}
  .row{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px solid var(--line);font-size:13px}
  .row:last-child{border-bottom:none}
  .row .k{color:var(--muted)}
  .pos{color:var(--green)} .neg{color:var(--red)} .hot{color:var(--accent)} .amber{color:var(--amber)}
  .big{font-size:30px;font-weight:800;letter-spacing:.5px}
  .signal-firing{color:var(--red);animation:pulse 1.3s ease-in-out infinite}
  .signal-armed{color:var(--muted)}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
  .bar{height:8px;border-radius:6px;background:#0d1117;border:1px solid var(--line);overflow:hidden;margin-top:5px}
  .bar > i{display:block;height:100%;background:var(--accent)}
  .badge{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11.5px;font-weight:700}
  .badge.on{background:rgba(63,185,80,.15);color:var(--green)}
  .badge.off{background:rgba(154,167,180,.12);color:var(--muted)}
  .badge.due{background:rgba(240,136,62,.16);color:var(--accent)}
  #chartcard{background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 12px;margin-top:12px;color:#1a1a1a}
  #charthdr{display:flex;flex-wrap:wrap;align-items:baseline;gap:14px;padding:2px 4px 8px}
  #charthdr .tkr{font-weight:800;font-size:15px;color:#111}
  #charthdr .px{font-weight:700}
  #ohlc{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#555;margin-left:auto}
  #chart{background:#fff;border-radius:8px}
  button{background:#0d1117;color:var(--ink);border:1px solid var(--line);border-radius:8px;
    padding:5px 12px;font-size:12.5px;cursor:pointer}
  button:hover{border-color:var(--accent)}
  .foot{color:var(--muted);font-size:11.5px;text-align:center;margin-top:24px}
  .dim{opacity:.45}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>VIX &gt; 40 「Buy the Fear」 · Live Monitor</h1>
    <span id="mktpill" class="pill closed">—</span>
    <span id="countdown" class="muted"></span>
    <span style="flex:1"></span>
    <span id="asof" class="muted"></span>
    <button onclick="refreshAll()">↻ Refresh</button>
  </div>
  <div id="banners"></div>

  <div class="grid g2">
    <div class="card"><h3>VIX <span class="muted" id="vixsub"></span></h3><div id="vixGauge" style="height:200px"></div></div>
    <div class="card"><h3>S&amp;P Weekly RSI(14) <span class="muted" id="rsisub"></span></h3><div id="rsiGauge" style="height:200px"></div></div>
  </div>

  <div class="card" style="text-align:center">
    <h3>Master Signal — VIX&gt;40 OR weekly RSI&lt;35</h3>
    <div id="sigBig" class="big signal-armed">—</div>
    <div id="sigLegs" class="muted"></div>
  </div>

  <div class="grid g3">
    <div class="card"><h3>Position &amp; Exit</h3><div id="position"></div></div>
    <div class="card"><h3>Catastrophe Monitor</h3><div id="catastrophe"></div></div>
    <div class="card"><h3>Entry Timers</h3><div id="timers"></div></div>
  </div>

  <div id="chartcard">
    <div id="charthdr">
      <span class="tkr">TQQQ · ProShares UltraPro QQQ</span>
      <span id="lastpx" class="px muted">—</span>
      <span id="ohlc"></span>
    </div>
    <div id="chart" style="height:1520px"></div>
  </div>
  <div class="foot">Yahoo Finance quotes (~15-min delayed) · auto-refresh 45s · falls back to last close when the market is closed / offline · not investment advice</div>
</div>

<script>
const TH = {bg:'#1a2029', line:'#2d333b', ink:'#e6edf3', muted:'#9aa7b4',
  accent:'#f0883e', green:'#3fb950', red:'#f85149', blue:'#58a6ff', amber:'#e3b341'};
const money = n => (n==null?'—':'$'+Number(n).toLocaleString('en-US'));
const pct = n => (n==null?'—':(n>=0?'+':'')+Number(n).toFixed(1)+'%');
const cls = n => (n==null?'':(n>=0?'pos':'neg'));

let gaugesInit = false;
function gauge(div, value, min, max, thr, invert, suffix){
  const hot = invert ? (value!=null && value<thr) : (value!=null && value>thr);
  const barColor = hot ? TH.red : TH.green;
  const tr = {type:'indicator', mode:'gauge+number', value:(value==null?0:value),
    number:{font:{color:TH.ink,size:34}, suffix:suffix||''},
    gauge:{axis:{range:[min,max],tickcolor:TH.muted,tickfont:{color:TH.muted,size:10}},
      bar:{color:barColor,thickness:0.28}, bgcolor:'#0d1117', borderwidth:0,
      threshold:{line:{color:TH.accent,width:3}, thickness:0.85, value:thr}}};
  const lay = {paper_bgcolor:TH.bg, margin:{t:14,b:8,l:24,r:24}, height:200,
    font:{color:TH.muted}};
  Plotly.react(div, [tr], lay, {displayModeBar:false, responsive:true});
}

function renderMarket(s){
  const m = s.market||{}; const p = document.getElementById('mktpill');
  const map = {OPEN:['open','● OPEN'], PREMARKET:['pre','PRE-MARKET'],
    AFTERHOURS:['pre','AFTER HOURS'], CLOSED:['closed','● CLOSED']};
  const e = map[m.state]||['closed', m.state||'—'];
  p.className = 'pill '+e[0]; p.textContent = e[1];
  const secs = m.seconds_to_next||0, h=Math.floor(secs/3600), mi=Math.floor((secs%3600)/60);
  document.getElementById('countdown').textContent =
    (m.next_event? (m.next_event==='close'?'closes in ':'opens in ')+h+'h '+mi+'m' : '');
  document.getElementById('asof').textContent = 'as of '+(s.as_of_eastern||'');
}

function renderBanners(s){
  let h='';
  if(s.error){ h += `<div class="banner err">⚠ ${s.error}</div>`; }
  if(s.data_freshness && s.data_freshness.stale_warning)
    h += `<div class="banner warn">Data is ${s.data_freshness.days_stale} business days old (last ${s.data_freshness.last_csv_date}) — run <code>python src/download_data.py</code></div>`;
  if(s.quotes_ok===false)
    h += `<div class="banner warn">Live quotes unavailable — showing last close.</div>`;
  const m=s.market||{};
  if(m.state==='OPEN'||m.state==='AFTERHOURS')
    h += `<div class="banner warn">VIX &amp; weekly RSI are <b>provisional intraday</b> until the 16:00 ET close.</div>`;
  document.getElementById('banners').innerHTML = h;
}

function renderGauges(s){
  const v=s.trigger_vix||{}, r=s.trigger_rsi||{};
  document.getElementById('vixsub').textContent =
    v.day_change==null?'':'Δ '+(v.day_change>=0?'+':'')+v.day_change+' vs prev close';
  document.getElementById('rsisub').textContent = r.provisional?'· provisional (wk '+r.week_ending+')':'· wk '+ (r.week_ending||'');
  gauge('vixGauge', v.value, 10, 60, v.threshold||40, false, '');
  gauge('rsiGauge', r.value, 0, 100, r.threshold||35, true, '');
}

function renderSignal(s){
  const m=s.master_signal||{}; const el=document.getElementById('sigBig');
  if(m.firing){ el.className='big signal-firing'; el.textContent='🔴 FIRING'; }
  else { el.className='big signal-armed'; el.textContent='ARMED'; }
  document.getElementById('sigLegs').textContent = m.legs_text||'';
}

function renderPosition(s){
  const p=s.position||{}; let h='';
  if(p.in_position){
    const exit = p.exit_condition_met ? '<span class="neg">EXIT triggered (S&amp;P&lt;MA50)</span>'
      : (p.exit_armed ? '<span class="pos">unlocked — waiting for S&amp;P&lt;MA50</span>'
      : 'locked · '+p.min_hold_left+'d left');
    h = `<div class="row"><span class="k">Entry (assumed +${p.assumed_entry_offset}d)</span><span>${p.entry_date} · $${p.entry_price}</span></div>
      <div class="row"><span class="k">TQQQ live / P&amp;L</span><span>${money(p.tqqq_live)} · <span class="${cls(p.unrealized_pct)}">${pct(p.unrealized_pct)}</span></span></div>
      <div class="row"><span class="k">Hold ${p.hold_days}/${p.min_hold_days}d</span><span>${exit}</span></div>
      <div class="bar"><i style="width:${p.hold_progress_pct}%"></i></div>
      <div class="row"><span class="k">S&amp;P vs MA50</span><span class="${p.below_ma50?'neg':'pos'}">${p.spx_live==null?'—':p.spx_live} vs ${p.spx_ma50} (${pct(p.ma50_distance_pct)})</span></div>`;
  } else {
    h = `<div class="row"><span class="k">Position</span><span class="muted">flat (no open trade)</span></div>
      <div class="row"><span class="k">S&amp;P vs MA50</span><span>${p.spx_live==null?'—':p.spx_live} vs ${p.spx_ma50}</span></div>`;
  }
  document.getElementById('position').innerHTML = h;
}

function renderCatastrophe(s){
  const c=s.catastrophe||{}; const dp=c.tqqq_day_change_pct;
  const frac = dp==null?0:Math.max(0,Math.min(100,(1 - dp/(c.threshold_pct))*100)); // 100=safe, 0=at breach
  const color = c.breach?TH.red:(dp!=null&&dp<-25?TH.amber:TH.green);
  document.getElementById('catastrophe').innerHTML =
    `<div class="row"><span class="k">TQQQ today</span><span class="${cls(dp)}" style="font-weight:700">${pct(dp)}</span></div>
     <div class="row"><span class="k">Circuit-breaker</span><span>${c.breach?'<span class="neg">BREACH — sell all</span>':'sell if ≤ '+c.threshold_pct+'%'}</span></div>
     <div class="bar"><i style="width:${frac}%;background:${color}"></i></div>
     <div class="row"><span class="k">QQQ today (ref ${c.qqq_ref_pct}%)</span><span class="${cls(c.qqq_day_change_pct)}">${pct(c.qqq_day_change_pct)}</span></div>`;
}

function renderTimers(s){
  const t=s.entry_timers||{}; const box=document.getElementById('timers');
  if(!t.active){ box.parentElement.classList.add('dim');
    box.innerHTML='<div class="row"><span class="muted">no active signal — timers idle</span></div>'; return; }
  box.parentElement.classList.remove('dim');
  const leg=(o,name)=>`<div class="row"><span class="k">${name}</span><span>${o.target_date} · ${o.due?'<span class="badge due">DUE</span>':o.trading_days_left+'d left'}</span></div>`;
  const m=t.ma5_confirm||{};
  box.innerHTML = `<div class="row"><span class="k">signal date</span><span>${t.signal_date}</span></div>`
    + leg(t.plus3,'+3d entry') + leg(t.plus9,'+9d entry')
    + `<div class="row"><span class="k">MA5 confirm (${m.tqqq} vs ${m.tqqq_ma5})</span><span>${m.confirmed?'<span class="badge on">CONFIRMED</span>':(m.expired?'<span class="badge off">expired</span>':'<span class="badge off">waiting</span>')}</span></div>`;
}

async function tick(){
  try{
    const s = await fetch('/api/state').then(r=>r.json());
    renderMarket(s); renderBanners(s); renderGauges(s);
    renderSignal(s); renderPosition(s); renderCatastrophe(s); renderTimers(s);
  }catch(e){ document.getElementById('banners').innerHTML =
    '<div class="banner err">Dashboard fetch failed: '+e+'</div>'; }
}

/* ---- Yahoo-style context chart (once on load) ---- */
const YH = {up:'#16a34a', down:'#e11d48', grid:'#eceef1', ink:'#1a1a1a', mut:'#6b7280',
  sig:'#f0883e', p3:'#2563eb', p9:'#16a34a', ma5:'#8b5cf6', exit:'#ef4444'};
let CHART = null;   // {dates, tqqq, low, high} for auto-y-zoom
let scaling = false;

function markers(D){
  const dates=D.dates, out={sigX:[],sigY:[],sigT:[],p3X:[],p3Y:[],p9X:[],p9Y:[],
    m5X:[],m5Y:[],exX:[],exY:[],exT:[],p3T:[],p9T:[],m5T:[]};
  D.trades.forEach(t=>{
    const si=dates.indexOf(t.signal_date);
    if(si>=0 && D.tqqq[si]!=null){ out.sigX.push(t.signal_date); out.sigY.push(D.tqqq[si]);
      out.sigT.push('Signal '+t.signal_date+'<br>'+t.trigger); }
    if(t.entries){ const e=t.entries;
      out.p3X.push(e.plus3.date); out.p3Y.push(e.plus3.price); out.p3T.push('+3d entry '+e.plus3.date+'<br>$'+e.plus3.price);
      out.p9X.push(e.plus9.date); out.p9Y.push(e.plus9.price); out.p9T.push('+9d entry '+e.plus9.date+'<br>$'+e.plus9.price);
      out.m5X.push(e.ma5.date);  out.m5Y.push(e.ma5.price);  out.m5T.push('MA5 entry '+e.ma5.date+'<br>$'+e.ma5.price); }
    if(!t.open){ out.exX.push(t.exit_date); out.exY.push(t.exit_price);
      out.exT.push('Exit '+t.exit_date+'<br>$'+t.exit_price+' · '+(t.ret>=0?'+':'')+t.ret+'%'); }
  });
  return out;
}
function mk(x,y,txt,name,color,sym,size){
  return {x:x,y:y,type:'scatter',mode:'markers',name:name,xaxis:'x',yaxis:'y',
    marker:{color:color,symbol:sym,size:size,line:{color:'#fff',width:1}},
    text:txt,hovertemplate:'%{text}<extra></extra>'};
}
/* The triggered trade: the open one, else the most recent (as in trade_10.png). */
function triggeredTrade(D){ return D.trades.find(t=>t.open) || D.trades[D.trades.length-1] || null; }
/* Local arrowed text-box callouts for ONE trade: Signal lower-left of the V, the
   three entry options stacked to the lower-right in the empty band below the
   recovery. Positions are in data coords keyed to the trade's own V (a local
   price band around its cluster), so each trade's group sits by its own candles
   and stays put on pan/zoom. */
function localTradeAnnotations(D, t){
  if(!t || !t.entries) return [];
  const e=t.entries, N=D.dates.length;
  const si=D.dates.indexOf(t.signal_date);
  const ei9=D.dates.indexOf(e.plus9.date);
  const anchor = ei9>=0 ? ei9 : (si>=0 ? si+9 : -1);
  if(anchor<0) return [];
  const a=Math.max(0,(si>=0?si:anchor-9)-3), b=Math.min(N, anchor+48);   // V + early recovery
  let lo=Infinity,hi=-Infinity;
  for(let i=a;i<b;i++){ const v=D.tqqq[i]; if(v!=null){ if(v<lo)lo=v; if(v>hi)hi=v; } }
  if(!isFinite(lo)) return [];
  const span=(hi-lo)||1, at=i=>D.dates[Math.max(0,Math.min(N-1,i))];
  const box=(x,y,bx,by,anchorX,text,color)=>({x:x,y:y,xref:'x',yref:'y',
    ax:bx,ay:by,axref:'x',ayref:'y',xanchor:anchorX,yanchor:'middle',
    showarrow:true,arrowhead:2,arrowsize:1,arrowwidth:1.5,arrowcolor:color,
    bordercolor:color,borderwidth:1.5,borderpad:5,bgcolor:'rgba(255,255,255,0.94)',
    font:{color:color,size:10},align:'left',text:text});
  const A=[], sigBase=si>=0?si:anchor-9, rx=at(anchor+40);   // entries hang under the recovery
  if(si>=0 && D.tqqq[si]!=null)
    A.push(box(t.signal_date,D.tqqq[si], at(sigBase-8), lo+span*0.04,'left',
      '<b>Signal</b> '+t.signal_date+'<br>'+t.trigger, YH.sig));
  A.push(box(e.plus3.date,e.plus3.price, rx, lo+span*0.40,'left',
    '<b>+3d entry</b><br>'+e.plus3.date+'<br>$'+e.plus3.price, YH.p3));
  A.push(box(e.plus9.date,e.plus9.price, rx, lo+span*0.24,'left',
    '<b>+9d entry ✓</b> (adopted)<br>'+e.plus9.date+'<br>$'+e.plus9.price, YH.p9));
  A.push(box(e.ma5.date, e.ma5.price, rx, lo+span*0.08,'left',
    '<b>MA5 entry</b><br>'+e.ma5.date+'<br>$'+e.ma5.price, YH.ma5));
  return A;
}
/* Annotations for a visible window: the live price tag plus a callout group for
   every trade whose cluster is in view — only when zoomed in enough (≤ ~1.4y) so
   wide views (5Y/Max) stay uncluttered and show just markers. */
function buildAnnotations(D, priceTag, x0, x1){
  const A = priceTag ? [priceTag] : [];
  const x0ms=new Date(x0).getTime(), x1ms=new Date(x1).getTime();
  if((x1ms-x0ms)/86400000 <= 520)
    D.trades.forEach(t=>{
      const s=new Date(t.signal_date).getTime();
      const e9=t.entries? new Date(t.entries.plus9.date).getTime():s;
      if((s>=x0ms&&s<=x1ms)||(e9>=x0ms&&e9<=x1ms)) A.push(...localTradeAnnotations(D,t));
    });
  return A;
}

function drawChart(D){
  if(!D || D.error) return;
  const dates=D.dates;
  const M=markers(D);
  const price={x:dates,open:D.tqqq_open,high:D.tqqq_high,low:D.tqqq_low,close:D.tqqq,
    type:'candlestick',name:'TQQQ',xaxis:'x',yaxis:'y',showlegend:false,
    increasing:{line:{color:YH.up},fillcolor:YH.up},
    decreasing:{line:{color:YH.down},fillcolor:YH.down}};
  const traces=[price,
    mk(M.sigX,M.sigY,M.sigT,'Signal',YH.sig,'circle',9),
    mk(M.p3X,M.p3Y,M.p3T,'+3d',YH.p3,'triangle-up',10),
    mk(M.p9X,M.p9Y,M.p9T,'+9d ✓',YH.p9,'triangle-up',13),
    mk(M.m5X,M.m5Y,M.m5T,'MA5',YH.ma5,'diamond',10),
    mk(M.exX,M.exY,M.exT,'Exit',YH.exit,'triangle-down',12),
    {x:dates,y:D.vix,mode:'lines',name:'VIX',line:{color:'#c2410c',width:1.1},xaxis:'x',yaxis:'y2',
      hovertemplate:'VIX %{y:.1f}<extra></extra>',showlegend:false},
    {x:dates,y:D.rsi,mode:'lines',name:'S&P RSI(14)',line:{color:'#111',width:1.1},xaxis:'x',yaxis:'y3',
      hovertemplate:'RSI %{y:.1f}<extra></extra>',showlegend:false}];

  const lastDate=dates[dates.length-1];
  let lastClose=null; for(let i=D.tqqq.length-1;i>=0;i--){ if(D.tqqq[i]!=null){lastClose=D.tqqq[i];break;} }
  const d3=new Date(lastDate); d3.setMonth(d3.getMonth()-3);
  let rangeStart=d3.toISOString().slice(0,10);   // default 3M, but widen to show the triggered trade
  const trig=triggeredTrade(D);
  if(trig){ const s=new Date(trig.signal_date); s.setDate(s.getDate()-14);
    const ss=s.toISOString().slice(0,10); if(ss<rangeStart) rangeStart=ss; }
  const priceTag = lastClose==null ? null : {xref:'paper',x:1,y:lastClose,yref:'y',xanchor:'left',
    yanchor:'middle',text:' '+Number(lastClose).toFixed(2)+' ',showarrow:false,bgcolor:YH.down,
    font:{color:'#fff',size:11},borderpad:2};
  const layout={paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{color:YH.mut,size:11.5},
    showlegend:true,legend:{orientation:'h',y:1.02,x:0,yanchor:'bottom',font:{color:YH.ink,size:11}},
    margin:{l:8,r:58,t:34,b:24},hovermode:'x',dragmode:'pan',
    xaxis:{domain:[0,1],anchor:'y3',gridcolor:YH.grid,range:[rangeStart,lastDate],rangeslider:{visible:false},
      showspikes:true,spikemode:'across',spikesnap:'cursor',spikethickness:1,spikedash:'dot',spikecolor:'#9aa0a6',
      rangebreaks:[{bounds:['sat','mon']},{values:D.holidays}],
      rangeselector:{bgcolor:'#f3f4f6',activecolor:'#2563eb',bordercolor:'#d1d5db',borderwidth:1,
        font:{color:'#111'},x:0,y:1.05,yanchor:'bottom',buttons:[
        {count:7,label:'5D',step:'day',stepmode:'backward'},
        {count:3,label:'3M',step:'month',stepmode:'backward'},
        {count:6,label:'6M',step:'month',stepmode:'backward'},
        {count:1,label:'1Y',step:'year',stepmode:'backward'},
        {count:5,label:'5Y',step:'year',stepmode:'backward'},
        {step:'all',label:'Max'}]}},
    yaxis:{domain:[0.40,1],side:'right',gridcolor:YH.grid,showspikes:true,spikemode:'across',
      spikethickness:1,spikedash:'dot',spikecolor:'#9aa0a6',tickfont:{color:'#333'}},
    yaxis2:{domain:[0.21,0.37],side:'right',gridcolor:YH.grid,title:{text:'VIX',font:{size:10}},tickfont:{color:'#333'}},
    yaxis3:{domain:[0.02,0.18],side:'right',gridcolor:YH.grid,title:{text:'S&P RSI(14)',font:{size:10}},range:[10,95],tickfont:{color:'#333'}},
    shapes:[
      {type:'line',xref:'paper',x0:0,x1:1,yref:'y2',y0:D.thresholds.vix,y1:D.thresholds.vix,line:{color:YH.down,width:1,dash:'dash'}},
      {type:'rect',xref:'paper',x0:0,x1:1,yref:'y2',y0:D.thresholds.vix,y1:100,fillcolor:'rgba(225,29,72,0.06)',line:{width:0}},
      {type:'line',xref:'paper',x0:0,x1:1,yref:'y3',y0:D.thresholds.rsi,y1:D.thresholds.rsi,line:{color:YH.down,width:1,dash:'dash'}},
      {type:'rect',xref:'paper',x0:0,x1:1,yref:'y3',y0:0,y1:D.thresholds.rsi,fillcolor:'rgba(225,29,72,0.08)',line:{width:0}},
      {type:'rect',xref:'paper',x0:0,x1:1,yref:'y3',y0:70,y1:95,fillcolor:'rgba(0,0,0,0.05)',line:{width:0}}],
    annotations: buildAnnotations(D, priceTag, rangeStart, lastDate)};
  if(lastClose!=null) layout.shapes.push({type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:lastClose,y1:lastClose,
    line:{color:YH.down,width:1,dash:'dash'}});

  const gd=document.getElementById('chart');
  Plotly.react(gd,traces,layout,{scrollZoom:true,responsive:true,displaylogo:false,
    modeBarButtonsToRemove:['lasso2d','select2d']}).then(()=>{
    CHART={dates:dates,tqqq:D.tqqq,low:D.tqqq_low,high:D.tqqq_high,vix:D.vix,rsi:D.rsi,gd:gd,D:D,priceTag:priceTag};
    autoscaleY(false);
    document.getElementById('lastpx').textContent = lastClose==null?'':('$'+Number(lastClose).toFixed(2));
    gd.removeAllListeners && gd.removeAllListeners('plotly_relayout');
    gd.on('plotly_relayout',ev=>{ if(scaling) return;
      if('xaxis.autorange' in ev) autoscaleY(true);
      else if(('xaxis.range[0]' in ev)||('xaxis.range' in ev)) autoscaleY(false); });
    gd.on('plotly_hover',ev=>{ const p=(ev.points||[]).find(pt=>pt.data.type==='candlestick'); if(!p)return;
      const i=p.pointNumber, f=v=>v==null?'—':Number(v).toFixed(2);
      document.getElementById('ohlc').textContent =
        `O ${f(D.tqqq_open[i])}  H ${f(D.tqqq_high[i])}  L ${f(D.tqqq_low[i])}  C ${f(D.tqqq[i])}`; });
  });
}
function autoscaleY(full){
  const C=CHART; if(!C) return;
  let x0=-Infinity,x1=Infinity;
  if(!full){ const xr=C.gd.layout.xaxis&&C.gd.layout.xaxis.range;
    if(xr){ x0=new Date(xr[0]).getTime(); x1=new Date(xr[1]).getTime(); } }
  let pl=Infinity,ph=-Infinity,vl=Infinity,vh=-Infinity;
  for(let i=0;i<C.dates.length;i++){ const tm=new Date(C.dates[i]).getTime();
    if(tm<x0||tm>x1) continue;
    const lo=C.low[i],hi=C.high[i]; if(lo!=null&&lo<pl)pl=lo; if(hi!=null&&hi>ph)ph=hi;
    const v=C.vix[i]; if(v!=null){if(v<vl)vl=v;if(v>vh)vh=v;} }
  if(!isFinite(pl)||!isFinite(ph)) return;
  const upd={'yaxis.range':[pl*0.96,ph*1.04]};
  if(isFinite(vl)){ const lo=Math.min(vl,40),hi=Math.max(vh,40),p=Math.max(1,(hi-lo)*0.1);
    upd['yaxis2.range']=[Math.max(0,lo-p),hi+p]; }
  const xr=C.gd.layout.xaxis&&C.gd.layout.xaxis.range;   // rebuild callouts for the visible trade(s)
  if(xr) upd['annotations']=buildAnnotations(C.D, C.priceTag, xr[0], xr[1]);
  scaling=true; Plotly.relayout(C.gd,upd).then(()=>{scaling=false;});
}
function loadChart(){ fetch('/api/history').then(r=>r.json()).then(drawChart).catch(()=>{}); }
function refreshAll(){ tick(); loadChart(); }

tick(); loadChart();
setInterval(tick, 45000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    if AUTO_UPDATE:
        threading.Thread(target=_daily_updater, daemon=True).start()  # daily CSV self-refresh
        print(f"Auto-update: CSVs refresh daily at {UPDATE_HOUR:02d}:00 ET (AUTO_UPDATE=0 to disable)")
    print(f"Live dashboard -> http://localhost:{port}  (Ctrl-C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)
