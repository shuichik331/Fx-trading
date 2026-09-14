"""Validate the "buy the EMA20 touch" pattern from the viral X post
(@HAGEDESU000, 2026-09-14: EMA20 x 15m, claims "beginner-achievable 3M
JPY/year pace") with the same rigor as everything else in this repo:
net of spread, 95% CI, and an EMA-window sweep for parameter robustness.

The post's own chart is a textbook selection artifact: it draws arrows only
at the touches that worked and shows one ~2-day window of a strong uptrend.
That tells us nothing about the many touches that would have failed, or how
it performs outside a trending run - which is exactly what this script
checks.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from cost_sensitivity import SPREAD_ESTIMATES
from indicators import atr
from strategies import ema_touch_continuation

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

DATASETS = {
    ("gold", "15m"): "gold_15m.csv",       # the post's own timeframe (60d only)
    ("gold", "1h_730d"): "gold_1h_730d.csv",
    ("gold", "1d"): "gold_1d.csv",
    ("usdjpy", "1h_730d"): "usdjpy_1h_730d.csv",
}


def evaluate(df: pd.DataFrame, signals: pd.Series, cost_r: float) -> dict:
    trades = run_backtest(df, signals)
    if len(trades) < 2:
        return {"n_trades": len(trades), "win_rate": np.nan, "net_expectancy_r": np.nan,
                "ci_low": np.nan, "ci_high": np.nan, "significant": False, "total_net_r": np.nan}
    r = np.array([t.r_multiple for t in trades]) - cost_r
    se = r.std(ddof=1) / np.sqrt(len(r))
    days = (df.index.max() - df.index.min()).days
    months = max(days / 30.44, 1e-9)
    return {
        "n_trades": len(r),
        "trades_per_month": len(r) / months,
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
        rows.append({"symbol": symbol, "timeframe": tf,
                     **evaluate(df, ema_touch_continuation(df, window=20), cost_r)})

    results = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("=== EMA20タッチ継続手法（Xの投稿の手法）検証結果 ===")
    print(results.round(3).to_string(index=False))
    results.to_csv(REPORTS_DIR / "ema_touch_results.csv", index=False)

    print("\n=== パラメータ頑健性: EMA期間を変えても優位性が残るか（ゴールド1時間足730日）===")
    df = pd.read_csv(DATA_DIR / "gold_1h_730d.csv", index_col=0, parse_dates=True).sort_index()
    cost_r = SPREAD_ESTIMATES["gold"] / (1.5 * atr(df, 14)).dropna().mean()
    sweep = []
    for window in (10, 15, 20, 25, 30, 50):
        sweep.append({"window": window, **evaluate(df, ema_touch_continuation(df, window), cost_r)})
    sweep_df = pd.DataFrame(sweep)
    print(sweep_df.round(3).to_string(index=False))
    sweep_df.to_csv(REPORTS_DIR / "ema_touch_robustness.csv", index=False)
    print(f"\nプラスだった期間: {(sweep_df['net_expectancy_r'] > 0).sum()}/{len(sweep_df)}  "
          f"統計的に有意: {sweep_df['significant'].sum()}/{len(sweep_df)}")

    # what the post's own screenshot period looked like, for context
    print("\n=== 参考: 投稿のスクリーンショット期間(2026-08-19〜21頃)のゴールドの状況 ===")
    d = pd.read_csv(DATA_DIR / "gold_1d.csv", index_col=0, parse_dates=True).sort_index()
    window = d[(d.index >= pd.Timestamp("2026-08-17", tz="UTC")) & (d.index <= pd.Timestamp("2026-08-21", tz="UTC"))]
    if not window.empty:
        chg = 100 * (window["close"].iloc[-1] / window["open"].iloc[0] - 1)
        print(f"  {window.index.min().date()} -> {window.index.max().date()}: {chg:+.2f}%（強いトレンド期間）")


if __name__ == "__main__":
    main()
