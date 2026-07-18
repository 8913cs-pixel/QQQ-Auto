#!/usr/bin/env python3
"""
QQQ Options Chain Snapshot Collector (GitHub Actions edition)
---------------------------------------------------------------
Pulls the full QQQ options chain from Yahoo Finance via yfinance and writes
one dated JSON snapshot into snapshots/, overwriting today's file each time
it's run (so if this runs every 30 minutes, today's file just gets fresher
until market close -- you still get one file per calendar day for the
backtester, same as before). It also regenerates snapshots/index.json, a
plain list of available dates, so the website knows what's new.

Designed to be run by .github/workflows/collect-snapshot.yml on a schedule,
but you can still run it manually:

    pip install yfinance --break-system-packages
    python3 collect_qqq_snapshot.py

Output:
    snapshots/qqq_YYYY-MM-DD.json
    snapshots/index.json
"""

import json
import os
import sys
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency. Run: pip install yfinance --break-system-packages")
    sys.exit(1)

TICKER = "QQQ"
OUT_DIR = "snapshots"
# QQQ has very frequent expirations (Mon/Wed/Fri). Set this comfortably
# higher than your longest planned back-leg DTE.
MAX_EXPIRATIONS = 20


def fetch_snapshot():
    tk = yf.Ticker(TICKER)

    hist = tk.history(period="1d")
    if hist.empty:
        raise RuntimeError("Could not fetch QQQ spot price")
    spot = float(hist["Close"].iloc[-1])

    expirations = tk.options[:MAX_EXPIRATIONS]
    if not expirations:
        raise RuntimeError("No options expirations returned for QQQ")

    chain_rows = []
    for exp in expirations:
        opt = tk.option_chain(exp)
        for df, opt_type in ((opt.calls, "call"), (opt.puts, "put")):
            for _, row in df.iterrows():
                chain_rows.append({
                    "expiration": exp,
                    "type": opt_type,
                    "strike": float(row.get("strike", 0) or 0),
                    "bid": float(row.get("bid", 0) or 0),
                    "ask": float(row.get("ask", 0) or 0),
                    "last": float(row.get("lastPrice", 0) or 0),
                    "iv": float(row.get("impliedVolatility", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "openInterest": int(row.get("openInterest", 0) or 0),
                })

    return {
        "ticker": TICKER,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "spot": spot,
        "chain": chain_rows,
    }


def rebuild_index():
    """List every qqq_YYYY-MM-DD.json file in OUT_DIR, sorted, as index.json."""
    dates = []
    for fname in os.listdir(OUT_DIR):
        if fname.startswith("qqq_") and fname.endswith(".json") and fname != "index.json":
            dates.append(fname[len("qqq_"):-len(".json")])
    dates.sort()
    with open(os.path.join(OUT_DIR, "index.json"), "w") as f:
        json.dump(dates, f, indent=2)
    return dates


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    snapshot = fetch_snapshot()
    filename = os.path.join(OUT_DIR, f"qqq_{snapshot['date']}.json")
    with open(filename, "w") as f:
        json.dump(snapshot, f, indent=2)
    dates = rebuild_index()
    print(f"Saved {filename}  (spot={snapshot['spot']:.2f}, "
          f"{len(snapshot['chain'])} contracts across "
          f"{len(set(r['expiration'] for r in snapshot['chain']))} expirations)")
    print(f"Index now lists {len(dates)} date(s): {dates}")


if __name__ == "__main__":
    main()
