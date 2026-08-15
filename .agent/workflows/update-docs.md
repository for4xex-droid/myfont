---
description: ドキュメントを最新のコード状態に同期。README、API仕様、コメントを更新。
---

# /update-docs - ドキュメント更新コマンド

コード変更に合わせてドキュメントを最新化します。

## 更新対象

1. **README.md** - プロジェクト概要、セットアップ手順
2. **API仕様** - エンドポイント、パラメータ、レスポンス
3. **コードコメント** - JSDoc、rustdoc
4. **CHANGELOG.md** - 変更履歴
5. **環境変数** - .env.example

## 実行手順

### ステップ1: 変更の特定
// turbo
```powershell
git diff --name-only HEAD~5
```

### ステップ2: README.mdの更新チェック

確認項目：
- [ ] プロジェクト説明が正確
- [ ] インストール手順が最新
- [ ] 使用例が動作する
- [ ] 依存関係が正しい
- [ ] ライセンス情報が正確

### ステップ3: API仕様の更新

```typescript
/**
 * ユーザーを取得する
 * @param id - ユーザーID
 * @returns ユーザーオブジェクト
 * @throws {NotFoundError} ユーザーが存在しない場合
 * @example
 * const user = await getUser('123');
 * console.log(user.name);
 */
async function getUser(id: string): Promise<User> {
  // ...
}
```

### ステップ4: CHANGELOGの更新

```markdown
# Changelog

## [Unreleased]

### Added
- 新機能の説明

### Changed
- 変更内容の説明

### Fixed
- 修正内容の説明

### Removed
- 削除内容の説明
```

### ステップ5: 環境変数の更新

```bash
# .env.example
# 必須
DATABASE_URL=postgresql://user:pass@localhost:5432/db
API_KEY=your-api-key-here

# オプション
DEBUG=false
LOG_LEVEL=info
```

## ドキュメント品質チェックリスト

### README.md
- [ ] バッジが最新（ビルド状態、カバレッジ等）
- [ ] クイックスタートが3分以内に完了可能
- [ ] スクリーンショットが最新
- [ ] リンクが有効

### API仕様
- [ ] 全エンドポイントが記載
- [ ] リクエスト/レスポンス例が正確
- [ ] エラーコードが説明されている
- [ ] 認証方法が明確

### コードコメント
- [ ] 公開関数にJSDoc/rustdoc
- [ ] 複雑なロジックに説明
- [ ] TODOが追跡されている
- [ ] 廃止予定に@deprecated

## 自動ドキュメント生成

**TypeScript (TypeDoc)**
// turbo
```powershell
npx typedoc --out docs src
```

**Rust**
// turbo
```powershell
cargo doc --no-deps --open
```

## ドキュメントテンプレート

### 関数ドキュメント

```typescript
/**
 * 関数の簡潔な説明（1行）
 *
 * 詳細な説明（必要に応じて複数行）
 *
 * @param paramName - パラメータの説明
 * @returns 戻り値の説明
 * @throws {ErrorType} エラーが発生する条件
 *
 * @example
 * // 使用例
 * const result = functionName('input');
 *
 * @see 関連する関数やドキュメント
 * @since 追加されたバージョン
 * @deprecated 非推奨の場合の代替手段
 */
```

### READMEセクション

```markdown
# プロジェクト名

簡潔な説明（1-2文）

## 機能

- 機能1
- 機能2

## インストール

\`\`\`bash
npm install package-name
\`\`\`

## 使用方法

\`\`\`typescript
import { something } from 'package-name';
\`\`\`

## API

### functionName(param)

説明

## ライセンス

MIT
```

## 関連ワークフロー

- `/code-review` - コードレビュー
- `/plan` - 実装計画
