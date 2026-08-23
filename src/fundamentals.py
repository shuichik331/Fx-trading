"""Macro fundamentals for Gold: real yields, USD strength, and a high-impact
economic-event calendar.

Gold's two dominant macro drivers, empirically and theoretically:
  - US real yields (10Y TIPS yield, FRED series DFII10): rising real yields
    raise the opportunity cost of holding a zero-yield asset like gold ->
    bearish for gold. Falling real yields -> bullish.
  - USD strength (DXY): gold is priced in USD, so a stronger dollar is
    mechanically bearish for gold (all else equal), a weaker dollar bullish.

We use these only as a *bias filter*, not a standalone entry signal -
see fundamentals_filter_backtest.py for the empirical test of whether this
filter actually improves the technical patterns.

No API key required: FRED's CSV export and Yahoo's chart API are both public.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from data_fetch import HEADERS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def fetch_real_yield(start: str = "2024-06-01") -> pd.Series:
    """US 10-Year Treasury Inflation-Indexed (real) yield, daily, from FRED."""
    r = requests.get(
        "https://fred.stlouisfed.org/graph/fredgraph.csv",
        params={"id": "DFII10", "cosd": start},
        timeout=20,
    )
    r.raise_for_status()
    df = pd.read_csv(pd.io.common.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df[df["value"] != "."]
    df["value"] = df["value"].astype(float)
    return df.set_index("date")["value"]


def fetch_dxy(range_: str = "2y") -> pd.Series:
    """USD index (ICE DXY), daily close, from Yahoo Finance."""
    r = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
        params={"range": range_, "interval": "1d"},
        headers=HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    ts = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_localize(None).normalize()
    close = result["indicators"]["quote"][0]["close"]
    return pd.Series(close, index=ts).dropna()


def macro_bias(real_yield: pd.Series, dxy: pd.Series, window: int = 20) -> pd.Series:
    """Daily gold macro bias: +1 bullish, -1 bearish, 0 neutral.

    Bullish when BOTH real yields and DXY are below their own `window`-day
    SMA (both trending down = tailwind for gold). Bearish when BOTH are
    above their SMA. Mixed signals -> neutral (0), since the two drivers
    disagree and we don't want to fabricate false confidence.
    """
    ry_trend = (real_yield < real_yield.rolling(window).mean()).astype(int) - (
        real_yield > real_yield.rolling(window).mean()
    ).astype(int)
    dxy_trend = (dxy < dxy.rolling(window).mean()).astype(int) - (
        dxy > dxy.rolling(window).mean()
    ).astype(int)

    combined = pd.concat([ry_trend, dxy_trend], axis=1, sort=True).ffill()
    bias = pd.Series(0, index=combined.index)
    bias[(combined.iloc[:, 0] > 0) & (combined.iloc[:, 1] > 0)] = 1
    bias[(combined.iloc[:, 0] < 0) & (combined.iloc[:, 1] < 0)] = -1
    return bias


def fetch_calendar_this_week() -> list[dict]:
    """This week's economic calendar (ForexFactory public feed). No key needed."""
    r = requests.get(
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        headers=HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def upcoming_high_impact_usd_events(buffer_hours: float = 48) -> pd.DataFrame:
    """High-impact USD events in the next `buffer_hours`, soonest first."""
    events = fetch_calendar_this_week()
    df = pd.DataFrame(events)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], utc=True)
    now = pd.Timestamp.now(tz="UTC")
    mask = (
        (df["country"] == "USD")
        & (df["impact"] == "High")
        & (df["date"] >= now)
        & (df["date"] <= now + pd.Timedelta(hours=buffer_hours))
    )
    return df.loc[mask, ["date", "title", "forecast", "previous"]].sort_values("date")


def minutes_to_next_high_impact_usd_event() -> tuple[float, str] | None:
    """(minutes_until, title) for the soonest upcoming high-impact USD event, or None."""
    upcoming = upcoming_high_impact_usd_events(buffer_hours=72)
    if upcoming.empty:
        return None
    row = upcoming.iloc[0]
    minutes = (row["date"] - pd.Timestamp.now(tz="UTC")).total_seconds() / 60
    return minutes, row["title"]


def high_impact_usd_events_near_now(before_hours: float = 1.0, after_hours: float = 1.0) -> pd.DataFrame:
    """High-impact USD events within [now-before_hours, now+after_hours].

    Use this as a trading pause window: a 15m/5m ATR-based stop is sized for
    normal volatility and can get blown straight through by the spike a
    release like FOMC/NFP/CPI causes, regardless of whether the technical
    pattern itself was valid. Only covers the current calendar week (the
    public feed doesn't serve arbitrary historical weeks).
    """
    events = fetch_calendar_this_week()
    df = pd.DataFrame(events)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], utc=True)
    now = pd.Timestamp.now(tz="UTC")
    mask = (
        (df["country"] == "USD")
        & (df["impact"] == "High")
        & (df["date"] >= now - pd.Timedelta(hours=before_hours))
        & (df["date"] <= now + pd.Timedelta(hours=after_hours))
    )
    return df.loc[mask, ["date", "title", "forecast", "previous"]].sort_values("date")


if __name__ == "__main__":
    ry = fetch_real_yield()
    dxy = fetch_dxy()
    bias = macro_bias(ry, dxy)
    print("直近の実質金利(10年):\n", ry.tail(5))
    print("\n直近のドル指数(DXY):\n", dxy.tail(5))
    print("\n直近のゴールド・マクロバイアス(+1強気/-1弱気/0中立):\n", bias.tail(10))

    print("\n直近72時間以内の米国ハイインパクト指標:")
    ev = upcoming_high_impact_usd_events(buffer_hours=72)
    print(ev.to_string(index=False) if not ev.empty else "  なし")
