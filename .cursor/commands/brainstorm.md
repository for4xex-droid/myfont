---
description: Tree of Thoughts (ToT) を用いた多角的な解決策の探索
---

# /brainstorm

このコマンドを受け取ったら次をこの順で実行する。

1. `.agent/PROJECT_MAP.md` を読む（cargo / npm / Aiome 固有コマンドは使わない）
2. `.agent/workflows/brainstorm.md` を読む
3. その手順を MyMincho 読み替えで最後まで実行する
4. `GOLDENRULES.md` に反することはしない

ユーザー入力の残り（Issue番号・対象ファイル・要件）をワークフローの引数として使う。
