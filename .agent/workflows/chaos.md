---
description: 制御された障害実験を自動生成・実行し、システムの回復力を検証するカオスエンジニアリングワークフロー
---

# /chaos — カオスエンジニアリング 🔥

## 思想
「壊れないシステム」は存在しない。
「壊れ方を知っているシステム」だけが、本番で生き残る。

## 前提知識
- カオスインジェクション基盤: `libs/infrastructure/tests/common/chaos.rs`
- テストスイート: `libs/infrastructure/tests/chaos_experiments.rs`
- 障害モード enum: `ChaosMode` (EmptyResponse, Timeout, MalformedJson, GiantOutput, AlwaysFail, NetworkPartition, HighLatency)

---

## 実行プロセス

### Phase 1: 定常状態の定義 (Steady State) 📊
対象コンポーネントの「正常な振る舞い」を仮説として明文化する。

**チェック項目:**
- [ ] 対象コンポーネントは何か？ (例: SoTEngine, SamsaraEngine, CircuitBreaker)
- [ ] 正常時の入力と期待される出力は何か？
- [ ] エラーハンドリングの期待動作は？ (fail-open vs fail-safe)

### Phase 2: 障害モードの選択 (Fault Selection) 🎯
`ChaosMode` enum から、対象に最も効果的な障害を選ぶ。

| 障害モード | 対象コンポーネント | 検証内容 |
|---|---|---|
| `EmptyResponse` | SoT, CortexCompiler | 空レスポンスでの Graceful Degradation |
| `Timeout` | SoT, Oracle | タイムアウト時の Error 伝搬 |
| `MalformedJson` | SoT, CortexCompiler | 不正 JSON でのフォールバック動作 |
| `GiantOutput` | ConstraintChecker | 巨大出力の検出・制限 |
| `AlwaysFail` | SamsaraEngine | LLM 全障害時のフォールバック継承 |
| `NetworkPartition` | FederationOps | ネットワーク断絶時の同期エラーハンドリング |
| `HighLatency` | FederationOps | 高レイテンシ時のタイムアウト動作 |

### Phase 3: 実験の実行 (Experiment) 🧪
// turbo
```bash
cargo test --test chaos_experiments
```

**合格基準:** 全テストが GREEN であること。

### Phase 4: 学習の抽出 (Learning) 📝
実験結果を分析し、以下を文書化する：

- 仮説が正しかったか？
- 予想外の副作用はあったか？（例: `generation` のデフォルト値が 0 ではなく 1 だった等）
- `SECURITY_DESIGN.md` に新しい脅威モデルを追加すべきか？
- 新しい `ChaosMode` バリアントを追加すべきか？

### Phase 5: テスト拡張 (Expansion) 🌱
発見された脆弱性や新しい仮説に基づき、`chaos_experiments.rs` に新しいテストを追加する。
追加後は再度 Phase 3 を実行して GREEN を確認する。

---

## 新しいカオス実験の追加方法

```rust
/// 仮説: [対象コンポーネント] が [障害モード] の状態でも、
///       [期待される安全動作] を維持する
#[tokio::test]
async fn chaos_[component]_[failure_mode]() {
    // 1. Steady State: 正常動作の確認
    // 2. Fault Injection: ChaosMode を注入
    // 3. Verification: panic しないこと + 期待動作の検証
    // 4. Learning: コメントで発見事項を記録
}
```

## 🛑 共通の言い訳 (Anti-rationalization)

| エージェントのよくある言い訳 | 現実 |
|---|---|
| 「テスト環境でのみ発生する障害です」 | 本番では予測不能な障害が発生する。テストで発見できた方が幸運。 |
| 「このコンポーネントは安定しているので不要です」 | 安定しているように見えるだけ。非決定的 LLM 出力に依存するならなおさら。 |
| 「カオステストの保守コストが高い」 | 6テストで0.11秒。保守コストは限りなくゼロ。 |

## 関連ワークフロー
- `/tdd` — テスト駆動開発
- `/red-team` — セキュリティ攻撃シミュレーション
- `/god-mode` — 究極のコンボワークフロー（Chaos 統合済み）（非推奨、/task 推奨）
