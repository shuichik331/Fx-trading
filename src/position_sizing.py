"""Translate a strategy's backtested edge (win rate / expectancy in R) into
the account size and risk-per-trade needed to reach a monthly profit target.

This is plain arithmetic on the expectancy found in run_analysis.py — it is
NOT a guarantee. Expectancy is an average over many trades; individual
months will be far more volatile than the average, including losing months.
"""
from __future__ import annotations

import argparse


def required_account(
    monthly_target_jpy: float,
    trades_per_month: float,
    expectancy_r: float,
    risk_pct: float,
) -> dict:
    ev_r_per_month = trades_per_month * expectancy_r  # expected R gained per month
    if ev_r_per_month <= 0:
        return {"error": "expectancy is not positive; no account size makes this work"}
    risk_per_trade_jpy = monthly_target_jpy / ev_r_per_month
    account_size_jpy = risk_per_trade_jpy / risk_pct
    return {
        "ev_r_per_month": ev_r_per_month,
        "risk_per_trade_jpy": risk_per_trade_jpy,
        "account_size_jpy": account_size_jpy,
    }


def monthly_ev(account_jpy: float, risk_pct: float, trades_per_month: float, expectancy_r: float) -> float:
    risk_per_trade = account_jpy * risk_pct
    return risk_per_trade * trades_per_month * expectancy_r


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", type=float, default=1_000_000)
    p.add_argument("--trades-per-month", type=float, default=6.9)
    p.add_argument("--expectancy-r", type=float, default=0.306)
    args = p.parse_args()

    print(f"target monthly profit: {args.target:,.0f} JPY")
    print(f"assumed trades/month: {args.trades_per_month}, expectancy: {args.expectancy_r} R\n")
    for risk_pct in (0.005, 0.01, 0.02, 0.03):
        r = required_account(args.target, args.trades_per_month, args.expectancy_r, risk_pct)
        print(
            f"risk/trade={risk_pct*100:>4.1f}%  ->  risk/trade={r['risk_per_trade_jpy']:>12,.0f} JPY"
            f"   required account={r['account_size_jpy']:>14,.0f} JPY"
        )
