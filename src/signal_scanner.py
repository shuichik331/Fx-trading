"""Check whether one of the two selected, cost-validated Gold patterns just
fired on the latest closed bar:

  Pattern A - Gold 15m Donchian Breakout   (net expectancy +0.135R, ~86 trades/month)
  Pattern B - Gold 5m RSI Mean-Reversion   (net expectancy +0.335R, ~16.5 trades/month,
                                             smaller sample -> trade smaller size / extra caution)

Both are the only 15m/5m patterns from the backtest (see reports/analysis_report.md
and reports/cost_adjusted_results.csv) that stayed net-positive after estimated
spread costs. USD/JPY and Gold's plain 15m/5m Donchian-on-5m did NOT survive
costs and are intentionally excluded here.

This does not place trades. It only tells you whether the rule-based entry
condition is true right now, with the corresponding entry/stop/target so you
can execute manually (or feed it into your own execution layer).

Run: python3 signal_scanner.py
"""
from __future__ import annotations

import sys

import pandas as pd

from data_fetch import fetch
from fundamentals import (
    fetch_dxy,
    fetch_real_yield,
    high_impact_usd_events_near_now,
    macro_bias,
)
from indicators import atr, ema, rsi
from strategies import donchian_breakout, rsi_mean_reversion

STOP_ATR = 1.5
REWARD_ATR = 3.0
NEWS_BUFFER_HOURS = 1.0  # avoid new entries within this many hours of high-impact USD releases


def check_pattern_a(df_15m: pd.DataFrame) -> dict | None:
    """Gold 15m Donchian breakout: signal on the last *closed* bar."""
    sig = donchian_breakout(df_15m, window=20)
    last_sig = sig.iloc[-1]
    if last_sig == 0:
        return None
    a = atr(df_15m, 14).iloc[-1]
    ref_close = df_15m["close"].iloc[-1]
    direction = "BUY" if last_sig == 1 else "SELL"
    stop = ref_close - STOP_ATR * a if last_sig == 1 else ref_close + STOP_ATR * a
    target = ref_close + REWARD_ATR * a if last_sig == 1 else ref_close - REWARD_ATR * a
    return {
        "pattern": "A: Gold 15m Donchian Breakout",
        "direction": direction,
        "signal_bar_close_time": df_15m.index[-1],
        "reference_close": ref_close,
        "suggested_entry": "次の15分足の始値",
        "stop": stop,
        "target": target,
        "atr": a,
    }


def check_pattern_b(df_5m: pd.DataFrame) -> dict | None:
    """Gold 5m RSI mean-reversion: signal on the last *closed* bar."""
    sig = rsi_mean_reversion(df_5m, rsi_window=14)
    last_sig = sig.iloc[-1]
    if last_sig == 0:
        return None
    a = atr(df_5m, 14).iloc[-1]
    ref_close = df_5m["close"].iloc[-1]
    r = rsi(df_5m["close"], 14).iloc[-1]
    direction = "BUY" if last_sig == 1 else "SELL"
    stop = ref_close - STOP_ATR * a if last_sig == 1 else ref_close + STOP_ATR * a
    target = ref_close + REWARD_ATR * a if last_sig == 1 else ref_close - REWARD_ATR * a
    return {
        "pattern": "B: Gold 5m RSI Mean-Reversion",
        "direction": direction,
        "signal_bar_close_time": df_5m.index[-1],
        "reference_close": ref_close,
        "rsi": r,
        "suggested_entry": "次の5分足の始値",
        "stop": stop,
        "target": target,
        "atr": a,
    }


def print_fundamentals_context() -> bool:
    """Print macro bias (informational) and news-blackout warnings.

    Returns True if a new entry should be avoided right now (high-impact
    USD release within NEWS_BUFFER_HOURS either side).
    """
    print("\n--- ファンダメンタルズ・コンテキスト ---")
    try:
        ry = fetch_real_yield(start="2026-06-01")
        dxy = fetch_dxy(range_="3mo")
        bias = macro_bias(ry, dxy, window=20)
        latest_bias = int(bias.dropna().iloc[-1]) if not bias.dropna().empty else 0
        label = {1: "強気(ゴールド追い風)", -1: "弱気(ゴールド逆風)", 0: "中立"}[latest_bias]
        print(f"  マクロバイアス: {label}")
        print("  ※ 検証の結果、このバイアスを方向フィルターとして使っても勝率・期待値は改善しなかった"
              "（reports/fundamentals_filter_results.csv）。あくまで参考情報として見ること。")
    except Exception as e:  # noqa: BLE001
        print(f"  マクロデータ取得失敗: {e}")

    avoid = False
    try:
        near = high_impact_usd_events_near_now(before_hours=NEWS_BUFFER_HOURS, after_hours=NEWS_BUFFER_HOURS)
        if near is not None and not near.empty:
            avoid = True
            print(f"  ⚠ 米国ハイインパクト指標が前後{NEWS_BUFFER_HOURS}時間以内にあり。新規エントリーは見送り推奨:")
            for _, row in near.iterrows():
                print(f"      {row['date']}  {row['title']}  (予想:{row['forecast']} 前回:{row['previous']})")
        else:
            print("  直近の米国ハイインパクト指標: なし（新規エントリーの妨げなし）")
    except Exception as e:  # noqa: BLE001
        print(f"  経済指標カレンダー取得失敗: {e}")

    return avoid


def main() -> None:
    print("最新データを取得中...")
    df_15m = fetch("gold", range_="1mo", interval="15m")
    df_5m = fetch("gold", range_="5d", interval="5m")

    hits = []
    a_hit = check_pattern_a(df_15m)
    b_hit = check_pattern_b(df_5m)
    if a_hit:
        hits.append(a_hit)
    if b_hit:
        hits.append(b_hit)

    avoid_new_entries = print_fundamentals_context()

    if not hits:
        print("\n現在、パターンA・Bとも条件成立なし。待機。")
        print(f"  直近15分足終値: {df_15m['close'].iloc[-1]:.2f} ({df_15m.index[-1]})")
        print(f"  直近5分足終値:  {df_5m['close'].iloc[-1]:.2f} ({df_5m.index[-1]})")
        return

    for h in hits:
        print(f"\n★ シグナル成立: {h['pattern']}")
        for k, v in h.items():
            if k == "pattern":
                continue
            print(f"    {k}: {v}")
        if avoid_new_entries:
            print("    ⚠ 上記の指標発表が近いため、条件成立していても今回は見送り推奨")
        print("    ※ 必ずリスク管理ルール(1トレード1〜2%)に従ってロットサイズを決めること")


if __name__ == "__main__":
    sys.exit(main())
