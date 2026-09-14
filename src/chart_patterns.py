"""Classic chart-pattern detectors (double top/bottom, head & shoulders) so
the textbook patterns can be tested with the same rigour as everything else.

Detection is deliberately mechanical. A human eye can rationalise almost any
squiggle into a "head and shoulders"; that flexibility is exactly what makes
visual pattern trading impossible to verify. Here every leg has an explicit,
ATR-scaled tolerance, so the same chart always yields the same answer.

No look-ahead: a swing point at bar i is only recognised at bar i+k (you need
k bars to its right to know it was a local extreme), and a pattern can only
fire on a bar whose swing legs are all already confirmed.

Not implemented, and why: triangles/wedges/flags/pennants need fitted
trendlines through swing points, where slope tolerance, minimum touch count
and convergence thresholds add many more free parameters - more knobs than
730 days of data can honestly support. Saucers have no objective definition
at all. Rectangles/boxes are already covered by donchian_breakout.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import atr

# defaults
SWING_K = 5          # bars either side required to confirm a swing point
TOL_ATR = 0.5        # how close two shoulders / two tops must be, in ATR
MIN_DEPTH_ATR = 1.0  # minimum pullback depth from the tops down to the neckline
MIN_SEP = 5          # minimum bars between the two tops / shoulders
MAX_SEP = 60         # maximum bars between them
MAX_WAIT = 30        # neckline must break within this many bars of the last swing


def _swing_points(df: pd.DataFrame, k: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Local extremes. Returns (swing_highs, swing_lows) as (position, price)."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    sh: list[tuple[int, float]] = []
    sl: list[tuple[int, float]] = []
    for i in range(k, n - k):
        window_h = highs[i - k : i + k + 1]
        window_l = lows[i - k : i + k + 1]
        if highs[i] == window_h.max():
            sh.append((i, highs[i]))
        if lows[i] == window_l.min():
            sl.append((i, lows[i]))
    return sh, sl


def _confirmed_upto(swings: list[tuple[int, float]], t: int, k: int) -> list[tuple[int, float]]:
    """Swings whose confirmation bar (i+k) has already happened by bar t."""
    return [s for s in swings if s[0] + k <= t]


def _extreme_between(values: np.ndarray, i1: int, i2: int, mode: str) -> float | None:
    if i2 <= i1 + 1:
        return None
    seg = values[i1 + 1 : i2]
    if len(seg) == 0:
        return None
    return float(seg.min() if mode == "min" else seg.max())


def double_top_bottom(
    df: pd.DataFrame,
    k: int = SWING_K,
    tol_atr: float = TOL_ATR,
    min_depth_atr: float = MIN_DEPTH_ATR,
    min_sep: int = MIN_SEP,
    max_sep: int = MAX_SEP,
    max_wait: int = MAX_WAIT,
) -> pd.Series:
    """Double top -> short on neckline break; double bottom -> long.

    Double top: two swing highs at a similar level, a trough between them deep
    enough to matter, and a close below that trough (the neckline).
    """
    a = atr(df, 14).to_numpy()
    close = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    sh, sl = _swing_points(df, k)
    sig = np.zeros(len(df), dtype=int)

    for t in range(k + 1, len(df)):
        if np.isnan(a[t]):
            continue
        tol = tol_atr * a[t]
        depth = min_depth_atr * a[t]

        # --- double top (bearish) ---
        ch = _confirmed_upto(sh, t, k)
        if len(ch) >= 2:
            (i1, p1), (i2, p2) = ch[-2], ch[-1]
            neckline = _extreme_between(lows, i1, i2, "min")
            if (
                neckline is not None
                and abs(p1 - p2) <= tol
                and min_sep <= (i2 - i1) <= max_sep
                and (min(p1, p2) - neckline) >= depth
                and (t - i2) <= max_wait
                and close[t] < neckline <= close[t - 1]
            ):
                sig[t] = -1
                continue

        # --- double bottom (bullish) ---
        cl = _confirmed_upto(sl, t, k)
        if len(cl) >= 2:
            (i1, p1), (i2, p2) = cl[-2], cl[-1]
            neckline = _extreme_between(highs, i1, i2, "max")
            if (
                neckline is not None
                and abs(p1 - p2) <= tol
                and min_sep <= (i2 - i1) <= max_sep
                and (neckline - max(p1, p2)) >= depth
                and (t - i2) <= max_wait
                and close[t] > neckline >= close[t - 1]
            ):
                sig[t] = 1

    return pd.Series(sig, index=df.index)


def head_and_shoulders(
    df: pd.DataFrame,
    k: int = SWING_K,
    tol_atr: float = TOL_ATR,
    min_depth_atr: float = MIN_DEPTH_ATR,
    min_sep: int = MIN_SEP,
    max_sep: int = MAX_SEP,
    max_wait: int = MAX_WAIT,
) -> pd.Series:
    """H&S top -> short on neckline break; inverse H&S -> long.

    Top: three swing highs where the middle (head) is the highest and the two
    shoulders sit at a similar level, with the neckline taken as the lower of
    the two intervening troughs.
    """
    a = atr(df, 14).to_numpy()
    close = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    sh, sl = _swing_points(df, k)
    sig = np.zeros(len(df), dtype=int)

    for t in range(k + 1, len(df)):
        if np.isnan(a[t]):
            continue
        tol = tol_atr * a[t]
        depth = min_depth_atr * a[t]

        # --- head and shoulders top (bearish) ---
        ch = _confirmed_upto(sh, t, k)
        if len(ch) >= 3:
            (i1, p1), (i2, p2), (i3, p3) = ch[-3], ch[-2], ch[-1]
            t1 = _extreme_between(lows, i1, i2, "min")
            t2 = _extreme_between(lows, i2, i3, "min")
            if t1 is not None and t2 is not None:
                neckline = min(t1, t2)
                if (
                    p2 > p1 + tol
                    and p2 > p3 + tol
                    and abs(p1 - p3) <= tol
                    and min_sep <= (i2 - i1) <= max_sep
                    and min_sep <= (i3 - i2) <= max_sep
                    and (p2 - neckline) >= depth
                    and (t - i3) <= max_wait
                    and close[t] < neckline <= close[t - 1]
                ):
                    sig[t] = -1
                    continue

        # --- inverse head and shoulders (bullish) ---
        cl = _confirmed_upto(sl, t, k)
        if len(cl) >= 3:
            (i1, p1), (i2, p2), (i3, p3) = cl[-3], cl[-2], cl[-1]
            t1 = _extreme_between(highs, i1, i2, "max")
            t2 = _extreme_between(highs, i2, i3, "max")
            if t1 is not None and t2 is not None:
                neckline = max(t1, t2)
                if (
                    p2 < p1 - tol
                    and p2 < p3 - tol
                    and abs(p1 - p3) <= tol
                    and min_sep <= (i2 - i1) <= max_sep
                    and min_sep <= (i3 - i2) <= max_sep
                    and (neckline - p2) >= depth
                    and (t - i3) <= max_wait
                    and close[t] > neckline >= close[t - 1]
                ):
                    sig[t] = 1

    return pd.Series(sig, index=df.index)


CHART_PATTERNS = {
    "double_top_bottom": double_top_bottom,
    "head_and_shoulders": head_and_shoulders,
}
