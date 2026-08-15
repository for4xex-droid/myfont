---
description: テストカバレッジを分析し、カバレッジ不足の箇所を特定・改善。
---

# /test-coverage - テストカバレッジ分析コマンド

テストカバレッジを分析し、改善が必要な箇所を特定します。

## 目標カバレッジ

| 種類 | 目標 | 最低限 |
|------|------|--------|
| ステートメント | 80% | 70% |
| ブランチ | 80% | 70% |
| 関数 | 90% | 80% |
| 行 | 80% | 70% |

## 実行手順

### ステップ1: カバレッジレポート生成

**JavaScript/TypeScript (Jest)**
// turbo
```powershell
npm test -- --coverage --coverageReporters=text --coverageReporters=html
```

**Rust**
// turbo
```powershell
cargo tarpaulin --out Html --output-dir coverage
```

### ステップ2: レポート確認
// turbo
```powershell
# HTMLレポートを開く
start coverage/index.html
```

### ステップ3: カバレッジ不足の分析

低カバレッジファイルを特定：
```
File                 | % Stmts | % Branch | % Funcs | % Lines |
---------------------|---------|----------|---------|---------|
src/utils/parser.ts  |   45.2  |    32.1  |   50.0  |   45.2  | ← 要改善
src/api/users.ts     |   92.3  |    88.5  |  100.0  |   92.3  | ✅
```

### ステップ4: 不足テストの作成

カバレッジが低い箇所のテストを追加：

```typescript
// 未テストのブランチを特定
function calculatePrice(quantity: number, isPremium: boolean): number {
  if (quantity <= 0) return 0;           // ← 未テスト
  
  const basePrice = quantity * 100;
  if (isPremium) {                       // ← 未テスト
    return basePrice * 0.8;
  }
  return basePrice;
}

// 追加すべきテスト
describe('calculatePrice', () => {
  it('should return 0 for zero quantity', () => {
    expect(calculatePrice(0, false)).toBe(0);
  });
  
  it('should return 0 for negative quantity', () => {
    expect(calculatePrice(-1, false)).toBe(0);
  });
  
  it('should apply premium discount', () => {
    expect(calculatePrice(10, true)).toBe(800);
  });
});
```

## カバレッジ改善戦略

### 1. エッジケースのテスト

```typescript
describe('edge cases', () => {
  it('handles null input', () => {});
  it('handles empty array', () => {});
  it('handles maximum values', () => {});
  it('handles special characters', () => {});
});
```

### 2. エラーパスのテスト

```typescript
describe('error handling', () => {
  it('throws on invalid input', () => {
    expect(() => fn(null)).toThrow('Invalid input');
  });
  
  it('handles network errors', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await expect(fetchData()).rejects.toThrow();
  });
});
```

### 3. ブランチカバレッジ

```typescript
// 全ブランチをカバー
describe('branch coverage', () => {
  it('condition true', () => {});
  it('condition false', () => {});
  it('early return', () => {});
});
```

## カバレッジ除外設定

テスト不要なコードを除外：

```javascript
// jest.config.js
module.exports = {
  coveragePathIgnorePatterns: [
    '/node_modules/',
    '/__tests__/',
    '/types/',
    '.d.ts$'
  ],
  coverageThreshold: {
    global: {
      branches: 70,
      functions: 80,
      lines: 70,
      statements: 70
    }
  }
};
```

## カバレッジレポート例

```markdown
# テストカバレッジレポート

## サマリー
- 全体カバレッジ: 78%
- 目標達成: ❌ (目標: 80%)
- 改善必要ファイル数: 5

## 要改善ファイル
| ファイル | カバレッジ | 不足箇所 |
|----------|-----------|----------|
| parser.ts | 45% | L23-45, L67-89 |
| validator.ts | 52% | L12-34 |
| api.ts | 68% | L100-120 |

## 推奨アクション
1. parser.tsにエッジケーステスト追加
2. validator.tsにエラーハンドリングテスト追加
3. api.tsにモックテスト追加
```

## 関連ワークフロー

- `/tdd` - テスト駆動開発
- `/code-review` - コードレビュー
