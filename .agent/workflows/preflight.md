---
description: コード変更前に影響範囲を確認し、カスケードエラーを防止するプリフライトチェック
---

# /preflight プリフライトチェック

コード変更を行う**前に**、以下の手順を必ず実行する。

## 手順

### 1. 影響範囲の特定 (Architecture & Semantic)
変更対象のシンボルがシステム全体にどれほど波及するかを `grep_search` や `cargo tree` で特定します。
また `ARCHITECTURE.md`（リポジトリルート）と `.context/RIPPLE_MAP.md` を確認し、設計上の依存関係に違反していないか確認します。
### 2. ベースラインテストの実行
// turbo
影響先を含むクレートのテストを**変更前に**実行し、現在の状態が正常であることを確認する。

```bash
cargo test -p soul -p infrastructure -p api-server
```

テストが既に失敗している場合は、まず**その修正を先に行う**こと。

### 3. 変更の実施
コードを変更する。以下のチェックを変更中に行う:

- [ ] 構造体のフィールド追加 → `RIPPLE_MAP.md` の「CAUTION」注記を確認したか？
- [ ] トレイトのシグネチャ変更 → 全ての impl (本体 + テスト用 Dummy) を列挙したか？
- [ ] `AppState` の変更 → `api_integration_tests.rs` を確認したか？
- [ ] 関数シグネチャ変更 → `grep` で全呼び出し元を確認したか？

### 4. ポストフライト検証
// turbo
変更後にワークスペース全体のテストを実行する。

```bash
cargo check --workspace --tests && cargo test --workspace
```

### 5. ドキュメント同期
- [ ] `CHANGELOG.md` — [Unreleased] に変更内容を追記
- [ ] `RIPPLE_MAP.md` — 新規ファイル/構造体がある場合は更新
- [ ] `docs/decisions/` — 重要な設計判断をした場合はADRを追記