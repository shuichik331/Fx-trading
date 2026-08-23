# Fx-trading

ゴールド(XAU/USD)とドル円(USD/JPY)を対象に、実際の価格データを使って「勝てるパターン」を
感覚ではなく数値で検証するためのバックテストツールキット。

**結論(詳細は `reports/analysis_report.md`)**: 日足・1時間足・15分足・5分足でバックテストした結果、
**ゴールドのドンチアン・ブレイクアウトが唯一、全時間足で一貫してスプレッドコスト差引後もプラスの
実質期待値**を示した。ドル円はこの4パターン・4時間足いずれでも優位性を確認できなかった。少額運用
からの現実的な資金計画・ロットサイズの決め方も含む。

**15分足・5分足のみで取引する場合**は `reports/trading_plan.md` を参照。ゴールドの2パターン
（15分足ドンチアン・ブレイクアウト／5分足RSI逆張り）に絞り込み、月10万円目標に必要な資金と
運用ルールをまとめてある。`src/signal_scanner.py` で「今この瞬間、条件に当てはまっているか」を
チェックできる。

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

# 1. データ取得（Yahoo Financeから日足2年 + 1時間足/15分足/5分足60〜70日をdata/にCSVキャッシュ）
python3 data_fetch.py

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
  signal_scanner.py                  # 採用中の2パターン成立有無＋ファンダメンタルズ状況をチェック
data/                                # 取得したOHLCVデータのCSVキャッシュ
reports/
  analysis_report.md                  # 検証結果と少額運用〜月100万円に向けたトレード計画
  backtest_results.csv                 # 全32パターンの生の指標
  cost_adjusted_results.csv             # スプレッドコスト差引後の実質期待値
  trading_plan.md                        # 15分足・5分足限定・月10万円目標の実践プラン
  fundamentals_filter_results.csv         # マクロバイアスフィルター適用前後の比較
  technical_filter_results.csv             # 1時間足トレンドフィルター適用前後の比較
```

## 免責事項

本リポジトリは教育・分析目的であり、投資助言ではありません。バックテストはスプレッド・
手数料・スワップコストを含んでおらず、サンプル数も限定的です。過去の成績は将来の成績を
保証しません。実資金での取引は自己責任で行ってください。
