"""Out-of-sample (forward) test of Pattern A and Pattern B.

The two patterns in reports/trading_plan.md were selected using data up to
2026-08-21 (archived in data/insample_20260821/). Any data after that date
did not exist when the patterns were chosen, so it is a genuine out-of-sample
test: it cannot be contaminated by the selection process.

Method: indicators and signals are computed on the FULL fresh dataframe so
warmup is correct, then only trades whose ENTRY falls after the cutoff are
counted. Spread cost is subtracted the same way as cost_sensitivity.py so
in-sample and out-of-sample numbers are comparable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from cost_sensitivity import SPREAD_ESTIMATES
from indicators import atr
from strategies import donchian_breakout, rsi_mean_reversion

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

# last bar of the sample the patterns were selected on
CUTOFF = pd.Timestamp("2026-08-21 21:00:00", tz="UTC")

# in-sample figures as published in reports/trading_plan.md (gross, before spread)
IN_SAMPLE = {
    "Pattern A: Gold 15m Donchian Breakout": {"n": 198, "win_rate": 0.414, "expectancy_r": 0.160},
    "Pattern B: Gold 5m RSI Mean-Reversion": {"n": 38, "win_rate": 0.526, "expectancy_r": 0.379},
}

CONFIGS = [
    ("Pattern A: Gold 15m Donchian Breakout", "gold", "gold_15m.csv", donchian_breakout),
    ("Pattern B: Gold 5m RSI Mean-Reversion", "gold", "gold_5m.csv", rsi_mean_reversion),
]


def main() -> None:
    rows = []
    for label, symbol, fname, strat_fn in CONFIGS:
        df = pd.read_csv(DATA_DIR / fname, index_col=0, parse_dates=True).sort_index()

        trades = run_backtest(df, strat_fn(df))
        oos = [t for t in trades if t.entry_time > CUTOFF]

        spread_cost_r = SPREAD_ESTIMATES[symbol] / (1.5 * atr(df, 14)).dropna().mean()

        if oos:
            r = np.array([t.r_multiple for t in oos])
            days = (df.index.max() - CUTOFF).days
            months = max(days / 30.44, 1e-9)
            oos_stats = {
                "oos_n": len(r),
                "oos_trades_per_month": len(r) / months,
                "oos_win_rate": (r > 0).mean(),
                "oos_expectancy_r": r.mean(),
                "oos_net_expectancy_r": r.mean() - spread_cost_r,
                "oos_total_r": r.sum(),
                "oos_net_total_r": r.sum() - spread_cost_r * len(r),
            }
        else:
            oos_stats = {k: np.nan for k in (
                "oos_n", "oos_trades_per_month", "oos_win_rate",
                "oos_expectancy_r", "oos_net_expectancy_r", "oos_total_r", "oos_net_total_r")}

        ins = IN_SAMPLE[label]
        rows.append({
            "pattern": label,
            "period": f"{CUTOFF.date()} -> {df.index.max().date()}",
            "in_sample_n": ins["n"],
            "in_sample_win_rate": ins["win_rate"],
            "in_sample_expectancy_r": ins["expectancy_r"],
            **oos_stats,
            "expectancy_change": oos_stats["oos_expectancy_r"] - ins["expectancy_r"],
        })

        if oos:
            print(f"\n{label} - out-of-sample trades ({len(oos)}):")
            for t in oos:
                print(f"  {t.entry_time:%Y-%m-%d %H:%M}  {'LONG ' if t.direction == 1 else 'SHORT'}"
                      f"  R={t.r_multiple:+.2f}")

    results = pd.DataFrame(rows)
    out = REPORTS_DIR / "out_of_sample_results.csv"
    results.to_csv(out, index=False)

    pd.set_option("display.width", 200)
    print("\n=== In-sample vs out-of-sample ===")
    print(results.drop(columns=["period"]).round(3).to_string(index=False))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
