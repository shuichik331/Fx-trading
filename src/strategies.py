"""Signal generators for the four classic price-action / trend patterns we
test on Gold (XAU) and USD/JPY.

Every function takes an OHLC DataFrame (columns: open, high, low, close) and
returns a Series of {1: long entry, -1: short entry, 0: no signal} aligned to
the bar on which the signal *closed* (the backtester enters on the *next*
bar's open, so there is no look-ahead).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr, bollinger, donchian, ema, rsi


def trend_pullback(df: pd.DataFrame) -> pd.Series:
    """Long-term trend (EMA200) + pullback re-entry (EMA20/EMA50 cross).

    Uptrend (close > EMA200): buy when EMA20 crosses back above EMA50.
    Downtrend (close < EMA200): sell when EMA20 crosses back below EMA50.
    """
    close = df["close"]
    ema20, ema50, ema200 = ema(close, 20), ema(close, 50), ema(close, 200)
    cross_up = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))
    cross_down = (ema20 < ema50) & (ema20.shift(1) >= ema50.shift(1))

    sig = pd.Series(0, index=df.index)
    sig[cross_up & (close > ema200)] = 1
    sig[cross_down & (close < ema200)] = -1
    return sig


def donchian_breakout(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Turtle-style breakout: close beyond the prior N-bar high/low."""
    upper, lower = donchian(df, window)
    prev_upper, prev_lower = upper.shift(1), lower.shift(1)
    close = df["close"]

    sig = pd.Series(0, index=df.index)
    sig[close > prev_upper] = 1
    sig[close < prev_lower] = -1
    return sig


def rsi_mean_reversion(df: pd.DataFrame, rsi_window: int = 14) -> pd.Series:
    """Buy oversold dips in an uptrend, sell overbought rallies in a downtrend."""
    close = df["close"]
    ema200 = ema(close, 200)
    r = rsi(close, rsi_window)
    cross_up_30 = (r > 30) & (r.shift(1) <= 30)
    cross_down_70 = (r < 70) & (r.shift(1) >= 70)

    sig = pd.Series(0, index=df.index)
    sig[cross_up_30 & (close > ema200)] = 1
    sig[cross_down_70 & (close < ema200)] = -1
    return sig


def bollinger_reversion(df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.Series:
    """Fade closes outside the bands back toward the mid-band."""
    close = df["close"]
    upper, mid, lower = bollinger(close, window, num_std)

    touch_lower = (close.shift(1) < lower.shift(1)) & (close > lower)
    touch_upper = (close.shift(1) > upper.shift(1)) & (close < upper)

    sig = pd.Series(0, index=df.index)
    sig[touch_lower] = 1
    sig[touch_upper] = -1
    return sig


def ema_touch_continuation(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """"Buy the pullback to the EMA" - the rule from the viral X post:

    1. Price confirms a cross of EMA(window) (close flips from below to above,
       or above to below) -> establishes a trend "regime".
    2. While in that regime, the first subsequent bar whose range touches the
       EMA (low <= EMA <= high) but still *closes* on the trend side ->
       entry in the trend direction (a pullback-and-hold, not a reversal).

    Only fires on the first bar of each touch (not every bar while price
    hovers on the average), otherwise a slow chop along the EMA would spam
    signals. No look-ahead: regime and touch both use only bars up to t.
    """
    close, low, high = df["close"], df["low"], df["high"]
    e = ema(close, window)

    above = close > e
    cross_up = above & ~above.shift(1).fillna(False)
    cross_down = (~above) & above.shift(1).fillna(False)

    regime = pd.Series(np.nan, index=df.index)
    regime[cross_up] = 1
    regime[cross_down] = -1
    regime = regime.ffill().fillna(0)

    touches = (low <= e) & (high >= e)
    touch_long = touches & (regime == 1) & (close > e)
    touch_short = touches & (regime == -1) & (close < e)
    new_touch_long = touch_long & ~touch_long.shift(1).fillna(False)
    new_touch_short = touch_short & ~touch_short.shift(1).fillna(False)

    sig = pd.Series(0, index=df.index)
    sig[new_touch_long] = 1
    sig[new_touch_short] = -1
    return sig


STRATEGIES = {
    "trend_pullback": trend_pullback,
    "donchian_breakout": donchian_breakout,
    "rsi_mean_reversion": rsi_mean_reversion,
    "bollinger_reversion": bollinger_reversion,
    "ema_touch_continuation": ema_touch_continuation,
}
