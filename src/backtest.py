"""Simple, conservative single-position backtester.

Rules:
- Enter at the *next* bar's open after a signal closes (no look-ahead).
- Stop-loss = entry -/+ stop_atr * ATR(14) at signal time.
- Take-profit = entry +/- reward_atr * ATR(14) at signal time (default 2R).
- If both stop and target fall inside the same bar's range, the stop is
  assumed to hit first (worst case, avoids overstating results).
- If neither is hit within max_hold bars, exit at that bar's close.
- Only one position open at a time; signals while a position is open are
  ignored (no pyramiding).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from indicators import atr as atr_fn


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int  # 1 long, -1 short
    entry: float
    exit: float
    stop: float
    target: float
    r_multiple: float
    bars_held: int


def run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    stop_atr: float = 1.5,
    reward_atr: float = 3.0,
    max_hold: int = 20,
) -> list[Trade]:
    a = atr_fn(df, 14)
    trades: list[Trade] = []

    n = len(df)
    idx = df.index
    i = 0
    while i < n - 1:
        sig = signals.iloc[i]
        if sig == 0 or np.isnan(a.iloc[i]):
            i += 1
            continue

        entry_i = i + 1
        entry_price = df["open"].iloc[entry_i]
        risk = stop_atr * a.iloc[i]
        reward = reward_atr * a.iloc[i]
        if sig == 1:
            stop = entry_price - risk
            target = entry_price + reward
        else:
            stop = entry_price + risk
            target = entry_price - reward

        exit_price = None
        exit_i = entry_i
        for j in range(entry_i, min(entry_i + max_hold, n)):
            hi, lo = df["high"].iloc[j], df["low"].iloc[j]
            if sig == 1:
                hit_stop = lo <= stop
                hit_target = hi >= target
            else:
                hit_stop = hi >= stop
                hit_target = lo <= target

            if hit_stop and hit_target:
                exit_price, exit_i = stop, j  # worst case: stop first
                break
            if hit_stop:
                exit_price, exit_i = stop, j
                break
            if hit_target:
                exit_price, exit_i = target, j
                break
            exit_i = j

        if exit_price is None:
            exit_price = df["close"].iloc[exit_i]

        r_multiple = ((exit_price - entry_price) / risk) if sig == 1 else (
            (entry_price - exit_price) / risk
        )

        trades.append(
            Trade(
                entry_time=idx[entry_i],
                exit_time=idx[exit_i],
                direction=int(sig),
                entry=entry_price,
                exit=exit_price,
                stop=stop,
                target=target,
                r_multiple=r_multiple,
                bars_held=exit_i - entry_i,
            )
        )
        i = exit_i + 1  # no overlapping positions

    return trades


def summarize(trades: list[Trade]) -> dict:
    if not trades:
        return {
            "n_trades": 0, "win_rate": np.nan, "avg_r": np.nan,
            "expectancy_r": np.nan, "profit_factor": np.nan, "max_dd_r": np.nan,
        }
    r = np.array([t.r_multiple for t in trades])
    wins = r[r > 0]
    losses = r[r <= 0]
    equity = np.cumsum(r)
    running_max = np.maximum.accumulate(equity)
    dd = running_max - equity
    return {
        "n_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_r": r.mean(),
        "expectancy_r": r.mean(),
        "profit_factor": (wins.sum() / -losses.sum()) if losses.sum() != 0 else np.inf,
        "max_dd_r": dd.max() if len(dd) else 0.0,
        "total_r": r.sum(),
    }
