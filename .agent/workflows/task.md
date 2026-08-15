---
description: 複数のワークフローを自動連結・実行する究極のタスク・オーケストレーター（Mission Control）。GitHub Issue等の要件を起点に自律判断します。
---

# /task - ミッション・コントロール・オーケストレーター 👑

このコマンドは、Aiome の全ワークフローを統括する「指揮者」です。
ユーザーは「タスク内容」または「Issue番号」を与えるだけで、AIがタスクの種別（Feature, Fix, Security, Docs）を解析し、必要なワークフローを適切な順番で**自動連鎖**させます。

## コマンド使用法

```bash
/task #123
/task 新しい決済APIを導入したい
```

---

## 🚀 実行フェーズ (The Orchestration Pipeline)

エージェントは、以下のフェーズに沿って自立的にタスクを進行させます。

### Phase 0: コンテキストの取得 & タスク種別の判定
1. ユーザー入力（またはGitHub MCP）から要件を取得します。
2. 以下の4分類から**タスク種別を1つ決定**します。
   - `[FEAT]` 新機能開発・アーキテクチャ変更
   - `[FIX]` バグ修正・リファクタリング
   - `[SEC]` セキュリティ・脆弱性対応
   - `[DOCS]` ドキュメントや設定の更新

### Phase 1: Planning & Verification (計画とメタ検証)
タスク種別に応じて、必要なワークフローを連鎖させます。

- **`[FEAT]`, `[SEC]` の場合**:
  1. まず `/deep-scan` を実行し、アーキテクチャ定義（`ARCHITECTURE.md`）から現行構造の全体像を把握する。
  2. 実装計画を立案する。
  3. 実装計画の初稿が完了したら、必ず `/perfect-plan` を実行し、波及漏れや依存関係の矛盾がないかメタ検証（Gate 1〜5）を行う。
- **`[FIX]`, `[DOCS]` の場合**:
  1. 計画立案後、`/preflight` を実行して `grep_search` および `RIPPLE_MAP.md` から影響範囲を確認する。

### Phase 2: Implementation (実装)
- **`[SEC]` の場合のみ**: 実装前に `/red-team` を実行し、攻撃ベクトルをシミュレーションして防御策を確定させる。
- 全てのコード変更は `/tdd`（テスト駆動開発）の精神に則り、テストを修正/作成してから本体コードを実装する。

### Phase 3: Review & Sync (監査と同期)
コードの変更が完了し、テスト（`cargo test` 等）がPASSしたら、以下の2つを**必ず**実行します。

1. `/code-review` - 品質、セキュリティ、保守性の最終セルフチェック。
2. `/docs-sync` - `CHANGELOG.md`, `RIPPLE_MAP.md`, `ARCHITECTURE.md` 等のドキュメント群をコードの最新状態に合わせて完全同期する。（ADRが必要かもここで判断）

### Phase 4: Git Commit & Finish (完了)
- Conventional Commitsのプレフィックスを用いてコミットします。
  例: `feat: add Tremendous API gift engine (#123)`
  例: `fix: resolve silent panic in biome decryption (#124)`
- GitHub MCPが有効であればPRを作成し、なければ完了をユーザーに報告します。

---

## 🧠 エージェントへの絶対指示 (Directives for AI)

> **Agent Directive:**
> あなたが `/task` コマンドを受け取った場合、ユーザーに「現在どのフェーズ（どの連鎖ワークフロー）を実行中か」を随時報告しながら、上記のパイプラインを**自律的に最後まで完遂**してください。
> 各フェーズの移行ごとに、連鎖するワークフローの名前（例: `> 🔄 Transitioning to /perfect-plan`）を明示し、Aiomeの極限の堅牢性を保証してください。
