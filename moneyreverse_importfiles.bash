#!/bin/bash
# MoneyRebirth - CSVファイル一括取り込みスクリプト
# csv/ ディレクトリのCSVファイルを全て取り込む

for f in ./csv/*.csv; do
    python3 moneyreverse_importer.py "$f"
done

echo "✅ 取り込み完了"
