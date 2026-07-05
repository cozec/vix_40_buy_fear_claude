"""
Download latest TQQQ / VIX / S&P 500 data from Yahoo Finance.

Saves CSVs in the existing on-disk format that backtest.load_yf expects
(3 header rows: Price / Ticker / Date, columns Close,High,Low,Open,Volume),
so the backtest runs unchanged. Split/dividend-adjusted (auto_adjust=True).
"""

import os
import yfinance as yf

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
COLS = ["Close", "High", "Low", "Open", "Volume"]
START = "2010-02-01"

TICKERS = {
    "^VIX": "vix_data.csv",
    "TQQQ": "tqqq_data.csv",
    "^GSPC": "sp500_data.csv",
}


def main():
    for ticker, fname in TICKERS.items():
        df = yf.download(ticker, start=START, auto_adjust=True, progress=False)
        # Never overwrite a good CSV with an empty/failed download — Yahoo can
        # rate-limit or block datacenter IPs and return nothing.
        if df is None or df.empty:
            print(f"{ticker:6s} -> empty download; keeping existing {fname}")
            continue
        # yfinance returns MultiIndex columns (Price, Ticker); keep our column order.
        df = df[COLS]
        path = os.path.join(DATA, fname)
        df.to_csv(path)
        print(f"{ticker:6s} -> {fname}: {len(df)} rows, "
              f"{df.index[0].date()} -> {df.index[-1].date()}")


if __name__ == "__main__":
    main()
