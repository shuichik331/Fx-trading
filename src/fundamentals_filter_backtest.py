"""Empirically test whether the macro bias filter (real yields + DXY, see
fundamentals.py) actually improves Pattern A (Gold 15m Donchian breakout)
and Pattern B (Gold 5m RSI mean-reversion) - the two patterns selected in
reports/trading_plan.md.

Rule tested: only take a LONG signal when macro_bias >= 0 (not bearish), and
only take a SHORT signal when macro_bias <= 0 (not bullish). Reject signals
that fight the macro backdrop. Bias is computed once per calendar day from
daily real-yield/DXY data and applied to every intraday signal that day.

This is an honest before/after comparison, not a foregone conclusion - if
the filter doesn't help, this script will show that.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from fundamentals import fetch_dxy, fetch_real_yield, macro_bias
from strategies import donchian_breakout, rsi_mean_reversion

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def stats(trades) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": np.nan, "expectancy_r": np.nan}
    r = np.array([t.r_multiple for t in trades])
    return {"n_trades": len(trades), "win_rate": (r > 0).mean(), "expectancy_r": r.mean()}


def apply_macro_filter(signals: pd.Series, bias_by_date: pd.Series) -> pd.Series:
    day_bias = bias_by_date.reindex(signals.index.normalize()).ffill()
    day_bias.index = signals.index
    filtered = signals.copy()
    filtered[(signals == 1) & (day_bias < 0)] = 0   # reject longs against bearish macro
    filtered[(signals == -1) & (day_bias > 0)] = 0  # reject shorts against bullish macro
    return filtered


def main() -> None:
    ry = fetch_real_yield(start="2024-06-01")
    dxy = fetch_dxy(range_="2y")
    bias = macro_bias(ry, dxy, window=20)

    configs = [
        ("Pattern A: Gold 15m Donchian Breakout", "gold_15m.csv", donchian_breakout),
        ("Pattern B: Gold 5m RSI Mean-Reversion", "gold_5m.csv", rsi_mean_reversion),
    ]

    rows = []
    for label, fname, strat_fn in configs:
        df = pd.read_csv(DATA_DIR / fname, index_col=0, parse_dates=True).sort_index()
        df.index = df.index.tz_localize(None)

        raw_signals = strat_fn(df)
        baseline_trades = run_backtest(df, raw_signals)

        filtered_signals = apply_macro_filter(raw_signals, bias)
        filtered_trades = run_backtest(df, filtered_signals)

        b, f = stats(baseline_trades), stats(filtered_trades)
        rows.append(
            {
                "pattern": label,
                "baseline_n": b["n_trades"],
                "baseline_winrate": b["win_rate"],
                "baseline_expectancy_r": b["expectancy_r"],
                "filtered_n": f["n_trades"],
                "filtered_winrate": f["win_rate"],
                "filtered_expectancy_r": f["expectancy_r"],
                "expectancy_delta": (f["expectancy_r"] - b["expectancy_r"]) if f["n_trades"] else np.nan,
            }
        )

    results = pd.DataFrame(rows)
    out = REPORTS_DIR / "fundamentals_filter_results.csv"
    results.to_csv(out, index=False)
    pd.set_option("display.width", 160)
    print(results.round(3).to_string(index=False))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
