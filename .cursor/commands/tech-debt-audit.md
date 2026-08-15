---
description: リポジトリ全体を俯瞰し、Git履歴と静的解析を組み合わせて技術的負債を体系的に監査するワークフロー
---

# /tech-debt-audit

このコマンドを受け取ったら次をこの順で実行する。

1. `.agent/PROJECT_MAP.md` を読む（cargo / npm / Aiome 固有コマンドは使わない）
2. `.agent/workflows/tech-debt-audit.md` を読む
3. その手順を MyMincho 読み替えで最後まで実行する
4. `GOLDENRULES.md` に反することはしない

ユーザー入力の残り（Issue番号・対象ファイル・要件）をワークフローの引数として使う。
