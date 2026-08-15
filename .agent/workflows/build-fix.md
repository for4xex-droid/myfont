---
description: ビルドエラーを分析し、体系的に修正。エラーの根本原因を特定して解決。
---

# /build-fix - ビルドエラー修正コマンド

ビルドエラーを体系的に分析し、根本原因から修正します。

## 実行手順

### ステップ1: ビルド実行
// turbo
```powershell
npm run build 2>&1 | Tee-Object -FilePath build-errors.log
```

### ステップ2: エラー分析

エラーを以下のカテゴリに分類：

| カテゴリ | 例 | 優先度 |
|----------|-----|--------|
| 型エラー | `Type 'X' is not assignable to type 'Y'` | 高 |
| インポート | `Cannot find module 'X'` | 高 |
| 構文エラー | `Unexpected token` | 高 |
| 未使用変数 | `'X' is declared but never used` | 中 |
| 依存関係 | `Module not found` | 高 |

### ステップ3: 依存関係の確認
// turbo
```powershell
npm ls --depth=0
```

### ステップ4: 型チェック
// turbo
```powershell
npx tsc --noEmit
```

### ステップ5: 修正の実行

**修正順序**：
1. 依存関係の問題（npm install）
2. 構文エラー
3. インポートエラー
4. 型エラー
5. 未使用変数/警告

### ステップ6: 再ビルド確認
// turbo
```powershell
npm run build
```

## よくあるエラーと解決策

### 型エラー

```typescript
// エラー: Type 'string' is not assignable to type 'number'
const age: number = "25"; // ❌

// 解決策
const age: number = parseInt("25", 10); // ✅
// または
const age: number = 25; // ✅
```

### インポートエラー

```typescript
// エラー: Cannot find module './components/Button'
import { Button } from './components/Button'; // ❌

// 解決策1: パスを確認
import { Button } from './components/button'; // 大文字/小文字

// 解決策2: 拡張子を追加
import { Button } from './components/Button.js';

// 解決策3: index.tsを確認
import { Button } from './components'; // index.tsからエクスポート
```

### 依存関係エラー

```powershell
# エラー: Module not found: 'lodash'

# 解決策
npm install lodash
npm install @types/lodash -D  # TypeScriptの場合
```

### 環境変数エラー

```typescript
// エラー: process.env.API_KEY is undefined
const apiKey = process.env.API_KEY; // ❌

// 解決策1: 型アサーション
const apiKey = process.env.API_KEY as string;

// 解決策2: デフォルト値
const apiKey = process.env.API_KEY ?? 'default-key';

// 解決策3: 起動時チェック
if (!process.env.API_KEY) {
  throw new Error('API_KEY is required');
}
```

## エラー修正チェックリスト

- [ ] すべてのエラーを特定
- [ ] 依存関係を確認・インストール
- [ ] 型エラーを修正
- [ ] インポートパスを確認
- [ ] ビルド成功を確認
- [ ] テストが通ることを確認

## 関連ワークフロー

- `/tdd` - テスト駆動開発
- `/code-review` - コードレビュー
- `/refactor` - リファクタリング
