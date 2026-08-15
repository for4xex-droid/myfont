---
description: コードのリファクタリングを実行。デッドコード削除、パフォーマンス改善、コード整理。
---

# /refactor - リファクタリングコマンド

コードの品質を改善し、技術的負債を解消します。

## リファクタリング対象の特定

### コードスメルチェック

1. **長すぎる関数** (50行超)
2. **深いネスト** (4レベル超)
3. **重複コード**
4. **マジックナンバー**
5. **神クラス/関数**
6. **長いパラメータリスト** (4つ超)
7. **フィーチャーエンビー**
8. **デッドコード**

### 検出コマンド

// turbo
```powershell
# 長い関数を検出 (Rust)
rg -c "fn " --type rust | Sort-Object

# 未使用インポートを検出 (TypeScript)
npx eslint . --rule "unused-imports/no-unused-imports: error"
```

## リファクタリングパターン

### 1. 関数の抽出

```typescript
// Before ❌
function processOrder(order: Order) {
  // バリデーション
  if (!order.items || order.items.length === 0) {
    throw new Error('Empty order');
  }
  if (!order.customerId) {
    throw new Error('No customer');
  }
  
  // 価格計算
  let total = 0;
  for (const item of order.items) {
    total += item.price * item.quantity;
  }
  
  // 税金追加
  total = total * 1.1;
  
  return total;
}

// After ✅
function validateOrder(order: Order): void {
  if (!order.items?.length) throw new Error('Empty order');
  if (!order.customerId) throw new Error('No customer');
}

function calculateSubtotal(items: OrderItem[]): number {
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}

function addTax(amount: number, rate = 0.1): number {
  return amount * (1 + rate);
}

function processOrder(order: Order): number {
  validateOrder(order);
  const subtotal = calculateSubtotal(order.items);
  return addTax(subtotal);
}
```

### 2. 条件分岐の簡略化

```typescript
// Before ❌
function getDiscount(user: User): number {
  if (user.isPremium) {
    if (user.years > 5) {
      return 0.3;
    } else if (user.years > 2) {
      return 0.2;
    } else {
      return 0.1;
    }
  } else {
    return 0;
  }
}

// After ✅
function getDiscount(user: User): number {
  if (!user.isPremium) return 0;
  if (user.years > 5) return 0.3;
  if (user.years > 2) return 0.2;
  return 0.1;
}
```

### 3. マジックナンバーの定数化

```typescript
// Before ❌
if (user.age >= 18 && user.posts > 100) {
  user.level = 3;
}

// After ✅
const ADULT_AGE = 18;
const POWER_USER_POSTS = 100;
const UserLevel = {
  POWER_USER: 3,
} as const;

if (user.age >= ADULT_AGE && user.posts > POWER_USER_POSTS) {
  user.level = UserLevel.POWER_USER;
}
```

### 4. ガード節の使用

```typescript
// Before ❌
function doSomething(user: User | null) {
  if (user) {
    if (user.isActive) {
      if (user.hasPermission) {
        // 実際の処理
      }
    }
  }
}

// After ✅
function doSomething(user: User | null) {
  if (!user) return;
  if (!user.isActive) return;
  if (!user.hasPermission) return;
  
  // 実際の処理
}
```

## デッドコード削除

### 未使用コードの検出

// turbo
```powershell
# TypeScript/JavaScript
npx ts-prune

# Rust
cargo +nightly udeps
```

### 削除前チェックリスト

- [ ] 本当に未使用か確認
- [ ] 動的インポートを確認
- [ ] テストを実行
- [ ] git diffで変更を確認

## リファクタリング安全チェック

1. **テストが存在する** - リファクタリング前にテストを確認
2. **小さなステップ** - 一度に大きな変更をしない
3. **頻繁にコミット** - 各ステップ後にコミット
4. **テスト実行** - 各変更後にテストを実行

// turbo
```powershell
npm test
```

## 関連ワークフロー

- `/code-review` - コードレビュー
- `/tdd` - テスト駆動開発
- `/test-coverage` - テストカバレッジ分析
