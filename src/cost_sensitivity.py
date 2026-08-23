"""Estimate how much of each strategy's backtested edge survives realistic
spread costs.

The core backtest (backtest.py) ignores spread/commission/slippage entirely.
That's fine for finding a raw edge, but it overstates results the shorter the
timeframe gets, because the stop distance (1.5x ATR) shrinks toward the fixed
spread. This script re-runs every strategy/symbol/timeframe combo and
subtracts an estimated spread cost (expressed in R) from every trade.

Spread assumptions are rough retail averages, not a specific broker's feed:
  - Gold (XAU/USD): $0.35 per round trip
  - USD/JPY:        0.6 pip (0.006) per round trip
Adjust SPREAD_JPY / SPREAD_ESTIMATES below if your broker quotes differently.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from indicators import atr
from strategies import STRATEGIES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

SPREAD_ESTIMATES = {"gold": 0.35, "usdjpy": 0.006}

DATASETS = {
    ("usdjpy", "1d"): "usdjpy_1d.csv",
    ("usdjpy", "1h"): "usdjpy_1h.csv",
    ("usdjpy", "15m"): "usdjpy_15m.csv",
    ("usdjpy", "5m"): "usdjpy_5m.csv",
    ("gold", "1d"): "gold_1d.csv",
    ("gold", "1h"): "gold_1h.csv",
    ("gold", "15m"): "gold_15m.csv",
    ("gold", "5m"): "gold_5m.csv",
}


def main() -> None:
    rows = []
    for (symbol, timeframe), fname in DATASETS.items():
        df = pd.read_csv(DATA_DIR / fname, index_col=0, parse_dates=True).sort_index()
        a = atr(df, 14)
        avg_risk = (1.5 * a).dropna().mean()
        spread = SPREAD_ESTIMATES[symbol]
        # round-trip cost expressed as a fraction of the average 1.5xATR stop
        cost_r = spread / avg_risk

        days = (df.index.max() - df.index.min()).days
        months = max(days / 30.44, 1e-9)

        for strat_name, strat_fn in STRATEGIES.items():
            trades = run_backtest(df, strat_fn(df))
            if len(trades) < 15:
                continue  # too few trades to say anything meaningful
            r = np.array([t.r_multiple for t in trades])
            gross_r = r.mean()
            net_r = gross_r - cost_r
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy": strat_name,
                    "n_trades": len(trades),
                    "trades_per_month": len(trades) / months,
                    "gross_expectancy_r": gross_r,
                    "spread_cost_r": cost_r,
                    "net_expectancy_r": net_r,
                    "survives_costs": net_r > 0,
                }
            )

    results = pd.DataFrame(rows).sort_values("net_expectancy_r", ascending=False)
    out = REPORTS_DIR / "cost_adjusted_results.csv"
    results.to_csv(out, index=False)

    pd.set_option("display.width", 160)
    print(results.round(3).to_string(index=False))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
