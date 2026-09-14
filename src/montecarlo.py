"""How reliably does capital actually grow with the edge we measured?

Expectancy alone doesn't answer "will my account go up?" - variance decides
that over any realistic horizon. This resamples the empirical per-trade R
distribution (bootstrap, 10,000 paths) to produce the numbers that matter for
compounding real money:

  - probability the account is up after 3 / 6 / 12 months
  - median and 5th-percentile outcome
  - probability of hitting a 10% / 20% / 30% drawdown along the way

Position sizing is fixed-fractional (risk the same % of current equity each
trade), which is what the trading plan prescribes.

It also runs a "what if the true edge were stronger" scenario, to show how much
edge per trade is actually needed before growth becomes dependable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import run_backtest
from cost_sensitivity import SPREAD_ESTIMATES
from indicators import atr
from strategies import donchian_breakout

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

N_PATHS = 10_000
RNG = np.random.default_rng(42)


def gold_1h_net_r() -> tuple[np.ndarray, float]:
    """Net-of-spread R multiples for gold 1h Donchian(20), plus trades/month."""
    df = pd.read_csv(DATA_DIR / "gold_1h_730d.csv", index_col=0, parse_dates=True).sort_index()
    cost_r = SPREAD_ESTIMATES["gold"] / (1.5 * atr(df, 14)).dropna().mean()
    trades = run_backtest(df, donchian_breakout(df, 20))
    r = np.array([t.r_multiple for t in trades]) - cost_r
    months = (df.index.max() - df.index.min()).days / 30.44
    return r, len(r) / months


def simulate(r_pool: np.ndarray, trades_per_month: float, risk_pct: float, months: int) -> dict:
    """Bootstrap fixed-fractional equity paths. Returns distribution stats."""
    n_trades = int(round(trades_per_month * months))
    draws = RNG.choice(r_pool, size=(N_PATHS, n_trades), replace=True)

    # fixed fractional: equity *= (1 + risk_pct * R) each trade
    growth = 1.0 + risk_pct * draws
    growth = np.clip(growth, 1e-9, None)  # an account can't go below zero
    equity = np.cumprod(growth, axis=1)

    running_max = np.maximum.accumulate(equity, axis=1)
    max_dd = (1 - equity / running_max).max(axis=1)

    final = equity[:, -1]
    return {
        "risk_pct": risk_pct,
        "months": months,
        "p_profit": (final > 1).mean(),
        "median_return": np.median(final) - 1,
        "p5_return": np.percentile(final, 5) - 1,
        "p95_return": np.percentile(final, 95) - 1,
        "p_dd_over_10pct": (max_dd > 0.10).mean(),
        "p_dd_over_20pct": (max_dd > 0.20).mean(),
        "p_dd_over_30pct": (max_dd > 0.30).mean(),
        "median_max_dd": np.median(max_dd),
    }


def main() -> None:
    r, tpm = gold_1h_net_r()
    print(f"素材データ: ゴールド1時間足ドンチアン20（730日）")
    print(f"  トレード数={len(r)}  月あたり={tpm:.1f}回  実質期待値={r.mean():+.4f}R  標準偏差={r.std(ddof=1):.3f}")
    se = r.std(ddof=1) / np.sqrt(len(r))
    print(f"  95%信頼区間=[{r.mean()-1.96*se:+.4f}, {r.mean()+1.96*se:+.4f}]R  → ゼロを含む=優位性は未証明\n")

    rows = []
    print("=== 実測した期待値(+%.3fR)のまま運用した場合 ===" % r.mean())
    for risk in (0.005, 0.01, 0.02):
        for months in (3, 6, 12):
            rows.append({"scenario": "measured_edge", **simulate(r, tpm, risk, months)})
    measured = pd.DataFrame(rows)
    print(measured.round(3).to_string(index=False))

    # what would it take for growth to be dependable? shift the distribution
    # so its mean equals a stronger hypothetical edge, keeping the shape.
    print("\n=== 仮に1トレードあたりの期待値がもっと高かったら（12ヶ月・リスク1%） ===")
    hypo_rows = []
    for target in (0.05, 0.10, 0.20, 0.30):
        shifted = r - r.mean() + target
        hypo_rows.append({"assumed_expectancy_r": target, **simulate(shifted, tpm, 0.01, 12)})
    hypo = pd.DataFrame(hypo_rows)
    print(hypo.round(3).to_string(index=False))

    out = REPORTS_DIR / "montecarlo_results.csv"
    pd.concat([measured, hypo], ignore_index=True).to_csv(out, index=False)
    print(f"\nsaved -> {out}")

    # breakeven spread: how much round-trip cost wipes out the measured edge
    df = pd.read_csv(DATA_DIR / "gold_1h_730d.csv", index_col=0, parse_dates=True).sort_index()
    avg_risk_usd = (1.5 * atr(df, 14)).dropna().mean()
    gross = r.mean() + SPREAD_ESTIMATES["gold"] / avg_risk_usd
    print(f"\n損益分岐スプレッド: 1トレードあたり往復 ${gross * avg_risk_usd:.2f} を超えると"
          f"実測した優位性は完全に消える（平均損切り幅 ${avg_risk_usd:.1f} 基準）")


if __name__ == "__main__":
    main()
