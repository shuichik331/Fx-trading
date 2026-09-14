"""Test the textbook chart patterns (double top/bottom, head & shoulders) the
same way as every other strategy in this repo: net of spread, with a 95%
confidence interval, and a parameter sweep to see whether the result survives
when the detection thresholds are nudged.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from chart_patterns import CHART_PATTERNS, double_top_bottom, head_and_shoulders
from cost_sensitivity import SPREAD_ESTIMATES
from indicators import atr

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

DATASETS = {
    ("gold", "1h_730d"): "gold_1h_730d.csv",
    ("usdjpy", "1h_730d"): "usdjpy_1h_730d.csv",
    ("gold", "15m"): "gold_15m.csv",
    ("gold", "1d"): "gold_1d.csv",
}


def evaluate(df: pd.DataFrame, signals: pd.Series, cost_r: float) -> dict:
    trades = run_backtest(df, signals)
    if len(trades) < 2:
        return {"n_trades": len(trades), "win_rate": np.nan, "net_expectancy_r": np.nan,
                "ci_low": np.nan, "ci_high": np.nan, "significant": False, "total_net_r": np.nan}
    r = np.array([t.r_multiple for t in trades]) - cost_r
    se = r.std(ddof=1) / np.sqrt(len(r))
    return {
        "n_trades": len(r),
        "win_rate": (r > 0).mean(),
        "net_expectancy_r": r.mean(),
        "ci_low": r.mean() - 1.96 * se,
        "ci_high": r.mean() + 1.96 * se,
        "significant": (r.mean() - 1.96 * se) > 0,
        "total_net_r": r.sum(),
    }


def main() -> None:
    rows = []
    for (symbol, tf), fname in DATASETS.items():
        df = pd.read_csv(DATA_DIR / fname, index_col=0, parse_dates=True).sort_index()
        cost_r = SPREAD_ESTIMATES[symbol] / (1.5 * atr(df, 14)).dropna().mean()
        for name, fn in CHART_PATTERNS.items():
            rows.append({"symbol": symbol, "timeframe": tf, "pattern": name,
                         **evaluate(df, fn(df), cost_r)})

    results = pd.DataFrame(rows).sort_values("net_expectancy_r", ascending=False)
    pd.set_option("display.width", 200)
    print("=== 教科書的チャートパターンの検証（スプレッド差引後・95%信頼区間つき） ===")
    print(results.round(3).to_string(index=False))
    results.to_csv(REPORTS_DIR / "chart_pattern_results.csv", index=False)

    # --- does the result survive nudging the detection thresholds? ---
    print("\n=== パラメータ頑健性（ゴールド1時間足730日） ===")
    df = pd.read_csv(DATA_DIR / "gold_1h_730d.csv", index_col=0, parse_dates=True).sort_index()
    cost_r = SPREAD_ESTIMATES["gold"] / (1.5 * atr(df, 14)).dropna().mean()
    sweep = []
    for k in (3, 5, 8):
        for tol in (0.3, 0.5, 0.8):
            for label, fn in (("double_top_bottom", double_top_bottom),
                              ("head_and_shoulders", head_and_shoulders)):
                res = evaluate(df, fn(df, k=k, tol_atr=tol), cost_r)
                sweep.append({"pattern": label, "swing_k": k, "tol_atr": tol, **res})
    sweep_df = pd.DataFrame(sweep)
    print(sweep_df.round(3).to_string(index=False))
    sweep_df.to_csv(REPORTS_DIR / "chart_pattern_robustness.csv", index=False)

    for label in ("double_top_bottom", "head_and_shoulders"):
        sub = sweep_df[sweep_df["pattern"] == label]
        print(f"\n{label}: プラス {int((sub['net_expectancy_r'] > 0).sum())}/{len(sub)} 通り、"
              f"統計的に有意 {int(sub['significant'].sum())}/{len(sub)} 通り")


if __name__ == "__main__":
    main()
