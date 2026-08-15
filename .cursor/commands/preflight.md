---
description: コード変更前に影響範囲を確認し、カスケードエラーを防止するプリフライトチェック
---

# /preflight

このコマンドを受け取ったら次をこの順で実行する。

1. `.agent/PROJECT_MAP.md` を読む（cargo / npm / Aiome 固有コマンドは使わない）
2. `.agent/workflows/preflight.md` を読む
3. その手順を MyMincho 読み替えで最後まで実行する
4. `GOLDENRULES.md` に反することはしない

ユーザー入力の残り（Issue番号・対象ファイル・要件）をワークフローの引数として使う。
