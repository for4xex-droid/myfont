---
description: 開発内容を分析し、関連ドキュメントを自動同期するワークフロー
---

# /docs-sync - ドキュメント自動同期

実装完了後に実行し、コードの変更内容をドキュメント（README, 仕様書, マニュアル等）に反映させます。

## 使用法

```bash
/docs-sync
```

## 実行手順

1. **変更分析 (Diff Analysis)**
   - `git diff` を実行し、インデックスまたは直近のコミットの変更内容を解析します。
   - 変更が「インフラ」「セキュリティ」「API」「UI」のどのカテゴリに属するかを特定します。

2. **影響ドキュメントの特定**
   - 以下のマッピングに基づき、更新が必要な候補を選定します。
     - **新環境変数**: `OPERATIONS_MANUAL.md`, `README.md`, `README_en.md`, `.env.example`
     - **新モジュール**: `docs/architecture/INFRASTRUCTURE_MODULES.md`, `CHANGELOG.md`, `CLOUD_DOCUMENTATION.md`
     - **セキュリティ変更**: `SECURITY_DESIGN.md`, `SECURITY_WHITEPAPER.md`
     - **進化システム変更**: `EVOLUTION_STRATEGY.md`
     - **LLM関連**: `LLM_PROVIDER_ARCHITECTURE.md`
     - **スキル/WASM関連**: `SKILL_FORGE_SPEC.md`, `SKILLS_MANUAL.md`
     - **トレイト/クレート/MCPツール変更**: `docs/architecture/AIOME_NURTURE_SYNERGY.md` (クラス図・シーケンス図・依存マップ)
     - **検証スクリプト追加 (`scripts/verify-*.sh` 等)**: `docs/guides/OPERATIONS_MANUAL.md`（リリース検証スクリプト節）, 関連する `docs/operations/*.md`
       <!-- 出典: 2026-07-06 /docs-sync 実行 (commit b63f753c)。verify-production-postgres.sh / verify-keychain-cli.sh 追加時に OPERATIONS_MANUAL v3.4 と api_key_rotation.md §5 への追記が必要だった -->
     - **タスク完了/新規発生**: `OPEN.md`（未解決タスクの正本）と `docs/roadmaps/release_master_plan.md` のステータス

3. **ドキュメント更新**
   - 抽出された変更内容（例：新しい環境変数の役割）を、各ドキュメントの適切なセクションに追記または修正します。
   - 英語版 (`README_en.md`) も必ず同期対象に含めます。

4. **最終確認**
   - `CHANGELOG.md` の [Unreleased] セクションに全ての変更が集約されているか確認します。
   - 各ドキュメントの「最終更新日」を**実行日の日付**（`date +%Y-%m-%d` で確認）に更新します。ワークフロー内の日付をコピーしてはいけません。

## 注意事項
- 既存の「独自の表現」や「トーン」を壊さないように配慮してください。
- Mermaid図の更新が必要な場合は、構造体やアクターの追加・削除を反映させてください。