# Fx-trading

ゴールド(XAU/USD)とドル円(USD/JPY)を対象に、実際の価格データを使って「勝てるパターン」を
感覚ではなく数値で検証するためのバックテストツールキット。

## 最新の結論（2026-09-14 改訂）

**統計的に優位性が証明できた手法はひとつも無い。** 詳細は `reports/validation_report.md`。

- 旧版で主力にしていた15分足・5分足の2パターンは、**選定後の新データ（8/22〜9/14）で両方とも損失**
  （1%リスクなら3週間で口座−10%相当）。15分足・5分足はデータが60日しか取得できず、優位性の判定に
  必要な約670件に構造的に届かないため、**採用を取り下げた**。
- 2.4年分（614件）の1時間足で再検証したゴールドのブレイクアウトは、実質期待値+0.054R・95%信頼区間
  [−0.052, +0.160]で**未証明**。ただしパラメータ6通り全てでプラス、四半期10期中6期プラスで
  「最も証拠がある候補」。サンプルが増えるほど期待値が下がっており（日足27件+0.663R → 15分足198件
  +0.160R → 1時間足614件+0.054R）、少数サンプルが優位性を過大に見せる典型例。
- モンテカルロ（10,000パス）の結果、**リスクを上げても資金が増える確率は上がらない**
  （0.5%→71.7%、1%→70.7%、2%→66.4%）。増えるのは資金減少幅だけ。
- ゴールドの往復スプレッドが**$1.58を超えると測定した優位性は完全に消滅**する。
- 教科書的チャートパターン（ヘッド&ショルダー、ダブルトップ/ボトム）も機械化して検証したが、
  **有意なものはゼロ**。ネックラインブレイクは構造的にブレイクアウト取引そのもので、期待値も
  既存のドンチアン・ブレイクアウトとほぼ同水準（＝新しい優位性ではなく同じ傾向の測り直し）。
  三角保ち合い・フラッグ・ペナント・ウェッジは、自由に動かせるパラメータが多すぎて730日分の
  データでは正直に検証できないため実装していない（理由は `src/chart_patterns.py` 冒頭に記載）。
- SNSでよく見る「EMA20タッチで順張り」手法も検証したが、**投稿の推奨時間足(ゴールド15分足)ではマイナス
  (−0.066R)**、最も条件の良い1時間足でも現行の最有力候補に見劣りし、パラメータ頑健性も低い
  （EMA期間6通り中プラスは2通りのみ）。採用しない。

実運用プラン（1手法のみ・リスク0.5%・実弾投入前の合否ゲート）は `reports/trading_plan.md`。
この手法をそのまま自動売買化したMT5 EA(ロット自動計算・サーキットブレーカー・ニュースフィルター・
CSVログ出力つき)は `ea/GoldDonchianBreakout.mq5`（使い方は `ea/README.md`）。
`reports/analysis_report.md` は改訂前の初期検証の記録として残してある。

**ファンダメンタルズも並行して見る**場合は `src/fundamentals.py`（実質金利・DXYからのマクロ
バイアス、米国ハイインパクト指標カレンダー）を参照。ただしマクロバイアスを方向フィルターとして
使う効果は`src/fundamentals_filter_backtest.py`で実際に検証済みで、**今回の検証期間では効果なし
（むしろ悪化）**という結果だった。詳細は `reports/trading_plan.md` の「ファンダメンタルズの
組み込み方」章、および `reports/fundamentals_filter_results.csv` を参照。

## セットアップ

```bash
pip install -r requirements.txt
```

## 使い方

```bash
cd src

# 1. データ取得（日足2年 + 1時間足/15分足/5分足60日 + 1時間足730日 をdata/にCSVキャッシュ）
python3 data_fetch.py

# 1b. 【重要】最も検証量の多い1時間足730日で、信頼区間・パラメータ頑健性・四半期一貫性を検証
python3 long_history_validation.py

# 1c. 選定後の新データだけでパターンが機能したかを検証（アウトオブサンプル検証）
python3 out_of_sample_test.py

# 1d. モンテカルロ10,000回で、リスク%別の「増える確率」と最大ドローダウンを算出
python3 montecarlo.py

# 2. 全戦略×全銘柄×全時間足のバックテストを実行し、reports/backtest_results.csv に保存
python3 run_analysis.py

# 3. スプレッドコストを差し引いた実質期待値を算出し、reports/cost_adjusted_results.csv に保存
python3 cost_sensitivity.py

# 4. 見つかった優位性を使い、目標月間利益を狙うために必要な口座資金・リスク量を試算
python3 position_sizing.py --target 100000 --trades-per-month 86.1 --expectancy-r 0.135

# 5. マクロバイアス(実質金利/DXY)フィルターが実際に効果あるか検証し、reports/fundamentals_filter_results.csv に保存
python3 fundamentals_filter_backtest.py

# 5b. 1時間足トレンドフィルター(純粋にテクニカル)が効果あるか検証し、reports/technical_filter_results.csv に保存
python3 technical_filter_backtest.py

# 6. 今この瞬間、採用中の2パターン(ゴールド15分足/5分足)の条件に当てはまっているか
#    ＋マクロバイアス・米国指標発表の有無をあわせてチェック
python3 signal_scanner.py
```

## 構成

```
src/
  data_fetch.py      # Yahoo Financeからのデータ取得・CSVキャッシュ
  indicators.py       # EMA/ATR/RSI/ボリンジャー/ドンチアンの実装
  strategies.py        # 4つの売買パターン(トレンド押し目/ブレイクアウト/RSI逆張り/BB逆張り)
  backtest.py           # ATRベースSL/TPの単純バックテストエンジン
  run_analysis.py         # 全組み合わせを実行し結果を集計
  cost_sensitivity.py       # スプレッドコスト差引後の実質期待値を算出
  position_sizing.py          # 期待値から必要資金・リスク量を逆算
  fundamentals.py                # 実質金利/DXYマクロバイアス・米国指標カレンダー取得
  fundamentals_filter_backtest.py  # マクロバイアスをフィルターとして使った場合の効果を検証
  technical_filter_backtest.py       # 1時間足トレンドフィルターの効果を検証
  long_history_validation.py           # 1時間足730日で信頼区間・パラメータ頑健性・四半期一貫性を検証
  out_of_sample_test.py                  # 選定後の新データだけで機能したかを検証
  montecarlo.py                            # リスク%別の増加確率・最大DD・必要な優位性を試算
  chart_patterns.py                          # H&S・ダブルトップ/ボトムの機械的検出（先読みなし）
  chart_pattern_validation.py                  # 上記パターンを信頼区間・頑健性つきで検証
  ema_touch_validation.py                        # SNSの「EMA20タッチ」手法を同基準で検証
  signal_scanner.py                  # 旧15分/5分パターンの成立有無＋ファンダメンタルズ状況をチェック
data/
  insample_20260821/                 # 旧パターン選定時点のデータスナップショット（検証の再現用）
reports/
  trading_plan.md                      # 【最新】1手法のみ・リスク0.5%・実弾投入前の合否ゲート
  validation_report.md                  # 【最新】アウトオブサンプル失敗・長期検証・モンテカルロの記録
  out_of_sample_results.csv              # 選定後データでの成績（旧パターンの失敗を記録）
  long_history_results.csv                # 1時間足730日・全戦略・95%信頼区間つき
  parameter_robustness.csv                 # ドンチアン期間を変えた場合の結果
  quarterly_consistency.csv                 # 四半期ごとの一貫性
  montecarlo_results.csv                     # リスク%別の増加確率・DD確率
  chart_pattern_results.csv                   # 教科書的チャートパターンの検証結果
  chart_pattern_robustness.csv                 # 検出閾値を変えた場合の結果
  ema_touch_results.csv                         # EMA20タッチ手法の検証結果
  ema_touch_robustness.csv                       # EMA期間を変えた場合の結果
  analysis_report.md                          # 改訂前の初期検証の記録（結論は上記に置き換え済み）
  backtest_results.csv                         # 全32パターンの生の指標
  cost_adjusted_results.csv                     # スプレッドコスト差引後の実質期待値
  fundamentals_filter_results.csv                # マクロバイアスフィルター適用前後の比較
  technical_filter_results.csv                    # 1時間足トレンドフィルター適用前後の比較
```

## 免責事項

本リポジトリは教育・分析目的であり、投資助言ではありません。バックテストはスプレッド・
手数料・スワップコストを含んでおらず、サンプル数も限定的です。過去の成績は将来の成績を
保証しません。実資金での取引は自己責任で行ってください。
