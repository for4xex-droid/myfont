---
description: リポジトリ全体を俯瞰し、Git履歴と静的解析を組み合わせて技術的負債を体系的に監査するワークフロー
---

# /tech-debt-audit - 統合技術的負債監査

このワークフローは、局所的なコードレビューでは見えない「アーキテクチャの腐敗」「一貫性の崩壊」「不要な複雑さ」を、変更履歴と静的解析ツールを用いてリポジトリ全体から抽出・可視化します。

## 🎯 いつ使うか
- 定期的な健康診断として（例: スプリントの終わり）
- 大規模なリファクタリングを計画する前の「どこから手をつけるべきか」の特定
- 新しいメンバーがプロジェクトの現状（暗黙の負債）を把握するため

## 🔄 実行手順

### Step 1: 俯瞰とコンテキストのロード (Orient)

Aiome のコードベースは 100k LOC を超えるため、全体を一度に読み込むことはできません。まず、変更頻度の高い「ホットスポット」を特定します。

// turbo-all
```bash
# 過去3ヶ月で最も変更頻度（コミット数）が高かったファイルトップ20を特定
git log --name-only --format="" --since="3 months ago" apps/ libs/ scripts/ | grep -v "^$" | sort | uniq -c | sort -nr | head -20
```

次に、システムの全体像を把握します。
- `view_file` ツールで `docs/architecture/SYSTEM_PANORAMA.md` を読み込む。

### Step 2: 静的解析ツールの実行 (Audit)

以下のコマンドを実行し、セキュリティとコード品質のベースラインを確認します。

// turbo-all
```bash
# Rust: 脆弱性監査
cargo audit 2>&1 | grep -E "error:|warning:|Crate:|Title:|ID:"

# Rust: Zero-Panic Policy 違反の検出 (enforce_unwrap_deny.py)
python3 scripts/enforce_unwrap_deny.py libs apps 2>&1 | tail -20

# クロスカッティング・ディープスキャン
bash scripts/deep-scan.sh --ci 2>&1 | grep -E "Errors:|Warnings:|🔴|⚠️"
```

> [!NOTE]
> `cargo udeps` や `cargo machete` の実行も推奨されますが、インストールされていない場合はスキップして構いません。

### Step 3: サブエージェントによる分割監査 (Subagent Dispatch)

Aiome のコードベースは巨大なため、`scripts/deep-scan.sh` の `CRATES` レジストリを参考に、主要なクレートやディレクトリ（例: `libs/infrastructure`, `apps/api-server`, `apps/management-console`）ごとに監査を分割して実行します。各モジュールについて、以下の **12次元** で負債を特定してください。

#### 監査の12次元 (The 12 Dimensions)
1. **Architectural decay**: SYSTEM_PANORAMA.md や ADR と実際のコードの乖離。
2. **Consistency rot**: 同じことを複数の異なる方法で実装している箇所（エラーハンドリング、設定管理など）。
3. **Type & contract debt**: `any` や過剰な `unwrap()`, 緩いトレイトバウンダリ。
4. **Test debt**: モックの過剰使用、flakey なテスト、重要な分岐のテスト漏れ。
5. **Dependency & config debt**: 未使用の依存関係、`.env.example` の乖離。
6. **Performance & resource hygiene**: メモリリークの可能性、N+1クエリ、過剰なクローン。
7. **Error handling & observability**: エラーが握り潰されている箇所、ログ不足。
8. **Security hygiene**: 権限の過剰付与、サニタイズ漏れ。
9. **Documentation drift**: README や関数ドキュメントが実態と合っていない。
10. **Zero-Panic Policy 形骸化 (Aiome固有)**: `// allow-anti-pattern` の過剰・不適切な使用。
11. **Tauri IPC 型安全性 (Aiome固有)**: バックエンドとフロントエンドの型定義の乖離。
12. **tokens.css 遵守度 (Aiome固有)**: UI における HEX/RGBA のハードコード（U-002 違反）。

> [!IMPORTANT]
> **引用の絶対ルール**:
> すべての指摘には必ず `path/to/file:LINE_NUMBER` 形式で具体的なファイルパスと行数を明記してください。一般論やファジーな指摘は禁止です。

### Step 4: アーティファクトの生成 (Deliverable)

監査結果をまとめ、リポジトリのルートに `TECH_DEBT_AUDIT.md` という Markdown アーティファクト（または既存のファイルの更新）を出力してください。

#### `TECH_DEBT_AUDIT.md` の必須構成要素:

1. **Executive Summary**: 経営陣・テックリード向けの現状の要約。
2. **Top 5 Priorities**: 最優先で解消すべき5つの負債。
3. **Quick Wins**: 1時間以内で修正でき、効果が高いもの。
4. **Findings Table**: 12次元ごとの詳細な指摘リスト（ファイル名、行数、深刻度、見積もり工数を含む）。
5. **Things that look bad but are actually fine**: 一見すると負債に見えるが、実は意図的な設計であるもの（これを含めることで浅い分析を防ぎます）。
6. **Open Questions**: コードを読んだだけでは意図が分からず、人間に確認すべき事項。

> [!TIP]
> 2回目以降の実行時は、既存の `TECH_DEBT_AUDIT.md` を読み込み、解決済みの項目には `[RESOLVED]` タグを、新規項目には `[NEW]` タグを付与して差分更新を行ってください。

## 🛑 共通の言い訳 (Anti-rationalization)

| エージェント(AI)のよくある言い訳 | 現実 (Reality) |
|----------------------|----------------|
| 「全体的に綺麗なので指摘事項はありません」 | 130k LOC のプロジェクトに負債がないことはあり得ません。Git のホットスポットを深く掘り下げてください。 |
| 「エラーハンドリングが不十分な箇所があります」 | どこですか？必ず `file:line` で特定してください。 |
| 「サブエージェントを使わずに一度に分析します」 | コンテキストウィンドウを超過し、精度が落ちます。必ずディレクトリやクレート単位で分割してください。 |
