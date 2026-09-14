"""Validate the patterns against the longest intraday history available
(730 days of hourly bars), with the three tests that actually separate a real
edge from a curve-fit:

1. Statistical significance - a 95% confidence interval on expectancy. An edge
   whose CI contains zero has not been demonstrated, however good the average
   looks.
2. Parameter robustness - sweep the lookback window. A real edge degrades
   gracefully as you nudge the parameter; a curve-fit collapses.
3. Period-by-period consistency - split the history into quarters. An edge you
   can compound needs most periods positive, not one lucky quarter carrying
   everything.

Why hourly and not 15m/5m: Yahoo caps 15m/5m history at 60 days, which is far
too short to clear any of these three bars (as out_of_sample_test.py showed).
Hourly gives ~2.4 years and multiple regimes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from cost_sensitivity import SPREAD_ESTIMATES
from indicators import atr
from strategies import (
    bollinger_reversion,
    donchian_breakout,
    rsi_mean_reversion,
    trend_pullback,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

DATASETS = {"gold": "gold_1h_730d.csv", "usdjpy": "usdjpy_1h_730d.csv"}


def load(symbol: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / DATASETS[symbol], index_col=0, parse_dates=True).sort_index()


def spread_cost_r(df: pd.DataFrame, symbol: str) -> float:
    return SPREAD_ESTIMATES[symbol] / (1.5 * atr(df, 14)).dropna().mean()


def evaluate(df: pd.DataFrame, signals: pd.Series, cost_r: float) -> dict:
    trades = run_backtest(df, signals)
    if len(trades) < 2:
        return {"n_trades": len(trades)}
    r = np.array([t.r_multiple for t in trades]) - cost_r  # net of spread
    se = r.std(ddof=1) / np.sqrt(len(r))
    equity = np.cumsum(r)
    dd = np.maximum.accumulate(equity) - equity
    return {
        "n_trades": len(r),
        "win_rate": (r > 0).mean(),
        "net_expectancy_r": r.mean(),
        "ci_low": r.mean() - 1.96 * se,
        "ci_high": r.mean() + 1.96 * se,
        "t_stat": r.mean() / se,
        "significant": (r.mean() - 1.96 * se) > 0,
        "total_net_r": r.sum(),
        "max_dd_r": dd.max(),
    }


def quarterly_breakdown(df: pd.DataFrame, signals: pd.Series, cost_r: float) -> pd.DataFrame:
    trades = run_backtest(df, signals)
    if not trades:
        return pd.DataFrame()
    rec = pd.DataFrame(
        {
            "quarter": [pd.Timestamp(t.entry_time).to_period("Q") for t in trades],
            "r": [t.r_multiple - cost_r for t in trades],
        }
    )
    g = rec.groupby("quarter")["r"]
    return pd.DataFrame({"n": g.size(), "win_rate": g.apply(lambda s: (s > 0).mean()),
                         "net_expectancy_r": g.mean(), "total_net_r": g.sum()})


def main() -> None:
    strategies = {
        "donchian_breakout": donchian_breakout,
        "trend_pullback": trend_pullback,
        "rsi_mean_reversion": rsi_mean_reversion,
        "bollinger_reversion": bollinger_reversion,
    }

    rows = []
    for symbol in DATASETS:
        df = load(symbol)
        cost_r = spread_cost_r(df, symbol)
        span = f"{df.index.min():%Y-%m-%d} -> {df.index.max():%Y-%m-%d}"
        for name, fn in strategies.items():
            res = evaluate(df, fn(df), cost_r)
            rows.append({"symbol": symbol, "span": span, "strategy": name, **res})

    results = pd.DataFrame(rows).sort_values("net_expectancy_r", ascending=False)
    pd.set_option("display.width", 220)
    print("=== 1時間足 730日 全戦略（スプレッドコスト差引後・95%信頼区間つき） ===")
    print(results.drop(columns=["span"]).round(3).to_string(index=False))
    results.to_csv(REPORTS_DIR / "long_history_results.csv", index=False)

    # --- parameter robustness on the Donchian breakout ---
    print("\n=== パラメータ頑健性: ドンチアン期間を変えても優位性が残るか ===")
    sweep_rows = []
    for symbol in DATASETS:
        df = load(symbol)
        cost_r = spread_cost_r(df, symbol)
        for window in (10, 15, 20, 30, 40, 50):
            res = evaluate(df, donchian_breakout(df, window=window), cost_r)
            sweep_rows.append({"symbol": symbol, "window": window, **res})
    sweep = pd.DataFrame(sweep_rows)
    print(sweep.round(3).to_string(index=False))
    sweep.to_csv(REPORTS_DIR / "parameter_robustness.csv", index=False)

    # --- quarter-by-quarter consistency for gold donchian(20) ---
    print("\n=== 四半期ごとの一貫性: ゴールド 1時間足 ドンチアン20 ===")
    df = load("gold")
    q = quarterly_breakdown(df, donchian_breakout(df, 20), spread_cost_r(df, "gold"))
    print(q.round(3).to_string())
    if not q.empty:
        print(f"\nプラスだった四半期: {(q['total_net_r'] > 0).sum()} / {len(q)}")
    q.to_csv(REPORTS_DIR / "quarterly_consistency.csv")


if __name__ == "__main__":
    main()
