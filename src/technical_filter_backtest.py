"""Does requiring 1-hour-timeframe trend alignment (a purely technical,
higher-timeframe confirmation filter) improve Pattern A / Pattern B?

Filter: only take a Pattern A (15m Donchian breakout) or Pattern B (5m RSI
mean-reversion) signal when its direction agrees with the 1h EMA200 trend
(close above EMA200 = uptrend, below = downtrend). This is the standard
"trade with the higher-timeframe trend" idea, tested empirically rather than
assumed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from indicators import ema
from strategies import donchian_breakout, rsi_mean_reversion

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def stats(trades) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": np.nan, "expectancy_r": np.nan}
    r = np.array([t.r_multiple for t in trades])
    return {"n_trades": len(trades), "win_rate": (r > 0).mean(), "expectancy_r": r.mean()}


def htf_trend_at(index: pd.DatetimeIndex, trend_1h: pd.Series) -> pd.Series:
    combined = trend_1h.reindex(index.union(trend_1h.index)).sort_index().ffill()
    return combined.reindex(index)


def main() -> None:
    df_1h = pd.read_csv(DATA_DIR / "gold_1h.csv", index_col=0, parse_dates=True).sort_index()
    df_1h.index = df_1h.index.tz_localize(None)
    trend_1h = np.sign(df_1h["close"] - ema(df_1h["close"], 200))

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

        bias = htf_trend_at(df.index, trend_1h)
        filtered_signals = raw_signals.copy()
        filtered_signals[(raw_signals == 1) & (bias < 0)] = 0
        filtered_signals[(raw_signals == -1) & (bias > 0)] = 0
        filtered_trades = run_backtest(df, filtered_signals)

        b, f = stats(baseline_trades), stats(filtered_trades)
        days = (df.index.max() - df.index.min()).days
        months = days / 30.44
        rows.append(
            {
                "pattern": label,
                "baseline_n": b["n_trades"],
                "baseline_trades_per_month": b["n_trades"] / months,
                "baseline_expectancy_r": b["expectancy_r"],
                "baseline_ev_r_per_month": (b["n_trades"] / months) * b["expectancy_r"],
                "filtered_n": f["n_trades"],
                "filtered_trades_per_month": f["n_trades"] / months if f["n_trades"] else np.nan,
                "filtered_expectancy_r": f["expectancy_r"],
                "filtered_ev_r_per_month": (f["n_trades"] / months) * f["expectancy_r"] if f["n_trades"] else np.nan,
            }
        )

    results = pd.DataFrame(rows)
    out = REPORTS_DIR / "technical_filter_results.csv"
    results.to_csv(out, index=False)
    pd.set_option("display.width", 200)
    print(results.round(3).to_string(index=False))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
