"""Fetch historical OHLC data for FX/commodity symbols from Yahoo Finance's
public chart API and cache it as CSV under data/.

Yahoo's endpoint occasionally 429s without a browser-like User-Agent, so we
always send one.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# symbol -> (yahoo ticker, friendly name)
SYMBOLS = {
    "usdjpy": "JPY=X",
    "gold": "GC=F",
}


def fetch(symbol_key: str, range_: str, interval: str, retries: int = 3) -> pd.DataFrame:
    ticker = SYMBOLS[symbol_key]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": range_, "interval": interval}

    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            result = data["chart"]["result"][0]
            ts = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            df = pd.DataFrame(
                {
                    "open": quote["open"],
                    "high": quote["high"],
                    "low": quote["low"],
                    "close": quote["close"],
                    "volume": quote.get("volume"),
                },
                index=pd.to_datetime(ts, unit="s", utc=True),
            )
            df.index.name = "datetime"
            df = df.dropna(subset=["open", "high", "low", "close"])
            return df
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {symbol_key} {range_}/{interval}: {last_err}")


def fetch_and_cache(symbol_key: str, range_: str, interval: str) -> pd.DataFrame:
    out = DATA_DIR / f"{symbol_key}_{interval}.csv"
    df = fetch(symbol_key, range_, interval)
    df.to_csv(out)
    print(f"saved {out} ({len(df)} rows, {df.index.min()} -> {df.index.max()})")
    return df


def fetch_and_cache_long_1h(symbol_key: str) -> pd.DataFrame:
    """Yahoo serves up to 730 days of hourly bars - far more regimes than the
    60-day cap on 15m/5m data, so this is the longest intraday history we can
    validate a pattern against. Saved separately from the 60d 1h file.
    """
    out = DATA_DIR / f"{symbol_key}_1h_730d.csv"
    df = fetch(symbol_key, range_="730d", interval="1h")
    df.to_csv(out)
    print(f"saved {out} ({len(df)} rows, {df.index.min()} -> {df.index.max()})")
    return df


if __name__ == "__main__":
    for key in SYMBOLS:
        fetch_and_cache(key, range_="2y", interval="1d")
        fetch_and_cache(key, range_="60d", interval="1h")
        fetch_and_cache(key, range_="60d", interval="15m")
        fetch_and_cache(key, range_="60d", interval="5m")
        fetch_and_cache_long_1h(key)
