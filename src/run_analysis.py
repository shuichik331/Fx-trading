"""Run every strategy against USD/JPY and Gold on daily + hourly bars,
print a results table, and dump it to reports/backtest_results.csv.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtest import run_backtest, summarize
from strategies import STRATEGIES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

DATASETS = {
    ("usdjpy", "1d"): "usdjpy_1d.csv",
    ("usdjpy", "1h"): "usdjpy_1h.csv",
    ("gold", "1d"): "gold_1d.csv",
    ("gold", "1h"): "gold_1h.csv",
}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / path, index_col=0, parse_dates=True)
    return df.sort_index()


def main() -> None:
    rows = []
    for (symbol, timeframe), fname in DATASETS.items():
        df = load(fname)
        for strat_name, strat_fn in STRATEGIES.items():
            signals = strat_fn(df)
            trades = run_backtest(df, signals)
            stats = summarize(trades)
            rows.append({"symbol": symbol, "timeframe": timeframe, "strategy": strat_name, **stats})

    results = pd.DataFrame(rows)
    results = results.sort_values(["symbol", "timeframe", "expectancy_r"], ascending=[True, True, False])
    out = REPORTS_DIR / "backtest_results.csv"
    results.to_csv(out, index=False)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    print(results.round(3).to_string(index=False))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
