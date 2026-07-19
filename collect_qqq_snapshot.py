#!/usr/bin/env python3
"""
QQQ Options Chain Snapshot Collector (GitHub Actions edition)
---------------------------------------------------------------
Pulls the full QQQ options chain from Yahoo Finance via yfinance and writes
a new JSON snapshot into snapshots/ on every run -- nothing gets overwritten,
so running this every 30 minutes builds up a full intraday history. It also
regenerates snapshots/index.json, a plain list of available snapshot IDs, so
the website knows what's new.

Designed to be run by .github/workflows/collect-snapshot.yml on a schedule,
but you can still run it manually:

    pip install yfinance --break-system-packages
    python3 collect_qqq_snapshot.py

Output:
    snapshots/qqq_YYYY-MM-DDTHH-MM.json   (one per run)
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


def safe_float(v, default=0.0):
    """Convert to float, treating NaN/None/unparseable values as `default`.
    `x or 0` does NOT catch NaN (NaN is truthy in Python), which is what
    caused int(NaN) crashes on illiquid contracts with missing volume/OI."""
    try:
        f = float(v)
        if f != f:  # NaN check (NaN is the only value that isn't equal to itself)
            return default
        return f
    except (TypeError, ValueError):
        return default


def safe_int(v, default=0):
    return int(safe_float(v, default))


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
                    "strike": safe_float(row.get("strike")),
                    "bid": safe_float(row.get("bid")),
                    "ask": safe_float(row.get("ask")),
                    "last": safe_float(row.get("lastPrice")),
                    "iv": safe_float(row.get("impliedVolatility")),
                    "volume": safe_int(row.get("volume")),
                    "openInterest": safe_int(row.get("openInterest")),
                })

    now = datetime.now()
    return {
        "ticker": TICKER,
        "date": now.strftime("%Y-%m-%dT%H:%M"),   # unique per run -- e.g. 2026-07-18T14:30
        "timestamp": now.isoformat(),
        "spot": spot,
        "chain": chain_rows,
    }


def rebuild_index():
    """List every qqq_*.json file in OUT_DIR, sorted, as index.json."""
    stems = []
    for fname in os.listdir(OUT_DIR):
        if fname.startswith("qqq_") and fname.endswith(".json") and fname != "index.json":
            stems.append(fname[len("qqq_"):-len(".json")])
    stems.sort()
    with open(os.path.join(OUT_DIR, "index.json"), "w") as f:
        json.dump(stems, f, indent=2)
    return stems


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    snapshot = fetch_snapshot()
    # filesystem-safe stem: colons aren't allowed in filenames on some systems
    stem = snapshot["date"].replace(":", "-")
    filename = os.path.join(OUT_DIR, f"qqq_{stem}.json")
    with open(filename, "w") as f:
        json.dump(snapshot, f, indent=2)
    stems = rebuild_index()
    print(f"Saved {filename}  (spot={snapshot['spot']:.2f}, "
          f"{len(snapshot['chain'])} contracts across "
          f"{len(set(r['expiration'] for r in snapshot['chain']))} expirations)")
    print(f"Index now lists {len(stems)} snapshot(s)")


if __name__ == "__main__":
    main()
