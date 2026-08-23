# Fx-trading

ゴールド(XAU/USD)とドル円(USD/JPY)を対象に、実際の価格データを使って「勝てるパターン」を
感覚ではなく数値で検証するためのバックテストツールキット。

**結論(詳細は `reports/analysis_report.md`)**: 検証した4つの機械的パターンのうち、統計的に
意味のある取引数(15件以上)かつプラス期待値だったのは **ゴールド日足のドンチアン・ブレイクアウト
(勝率55.6%, 期待値+0.667R)** のみ。ドル円はこの4パターンでは優位性を確認できなかった。
「月100万円」を狙うために必要な資金規模の試算も含む。

## セットアップ

```bash
pip install -r requirements.txt
```

## 使い方

```bash
cd src

# 1. データ取得（Yahoo Financeから日足2年 + 1時間足60日をdata/にCSVキャッシュ）
python3 data_fetch.py

# 2. 全戦略×全銘柄×全時間足のバックテストを実行し、reports/backtest_results.csv に保存
python3 run_analysis.py

# 3. 見つかった優位性を使い、月100万円を狙うために必要な口座資金・リスク量を試算
python3 position_sizing.py --trades-per-month 22.5 --expectancy-r 0.306
```

## 構成

```
src/
  data_fetch.py      # Yahoo Financeからのデータ取得・CSVキャッシュ
  indicators.py       # EMA/ATR/RSI/ボリンジャー/ドンチアンの実装
  strategies.py        # 4つの売買パターン(トレンド押し目/ブレイクアウト/RSI逆張り/BB逆張り)
  backtest.py           # ATRベースSL/TPの単純バックテストエンジン
  run_analysis.py         # 全組み合わせを実行し結果を集計
  position_sizing.py        # 期待値から必要資金・リスク量を逆算
data/                        # 取得したOHLCVデータのCSVキャッシュ
reports/
  analysis_report.md          # 検証結果と月100万円に向けたトレード計画
  backtest_results.csv         # 全16パターンの生の指標
```

## 免責事項

本リポジトリは教育・分析目的であり、投資助言ではありません。バックテストはスプレッド・
手数料・スワップコストを含んでおらず、サンプル数も限定的です。過去の成績は将来の成績を
保証しません。実資金での取引は自己責任で行ってください。
