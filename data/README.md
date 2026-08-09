# 文字セット正本（掟19）

このディレクトリの `glyphset_*.txt` が cmap・欠字検査・スコープ撤退の唯一の正本。
変更は明示コミットとして行う。

| ファイル | 内容 | 出典 |
|---|---|---|
| `glyphset_joyo2136.txt` | 常用漢字 2,136 字（1字1行） | PyPI `kanji-lists` JOYO（spike2 で実カウント検証後に凍結） |
| `glyphset_kyoiku1026.txt` | 教育漢字 1,026 字 | 同上 KYOIKU |
| `glyphset_joyo2136_uninames.txt` | `uniXXXX` 一覧 | 上記から生成 |
| `glyphset_p1_kana_core20.txt` | P1 ひらがな核心20字 | PLAN §3.5 |
| `glyphset_alpha.txt` | α 版公開スコープ（仮名・英数・約物・基準漢字） | `docs/strategy.md` α 定義 |

再生成スクリプト: `scripts/freeze_glyphsets.py`（既存凍結ファイルの再検証＋再出力）。
