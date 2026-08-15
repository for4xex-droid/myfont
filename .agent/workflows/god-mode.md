---
description: Brainstorm, TDD, Reflexion, Chaos, Red-Team を連鎖させ、最高品質の成果物を生み出す究極のコンボワークフロー
---

> [!NOTE] このワークフローは `/task` オーケストレーターに統合予定です。新規利用は `/task` を推奨します。

# /god-mode - 神の一手

重要かつ難解なタスクに対し、全知全能（Brainstorm x TDD x Reflexion x Red-Team）のアプローチで完遂します。
時間とトークンを大量に消費しますが、**人間を超える品質のコード**を生み出します。

## 実行プロセス

### Phase 1: 衆愚を排す (Brainstorm) 🧠
まず、飛びつき実装を防ぎます。
ワークフロー `/brainstorm` を実行し、3つのアプローチから最良の設計を選択してください。

### Phase 2: 創造 (Implementation) 🔨
選択された設計に基づき、コードを実装します。
`security-guardrails` スキルを参照し、ベースからセキュアであることを心がけてください。

### Phase 3: 研鑽 (Reflexion) ✨
ワークフロー `/reflexion` を実行し、自己批判ループを回してコード品質を95点以上に引き上げてください。
Golden Ruleへの準拠を徹底させます。

### Phase 4: 混沌 (Chaos) 🔥
ワークフロー `/chaos` を実行し、障害注入テストを回してレジリエンスを検証してください。
LLM 空レスポンス、LLM タイムアウト、Circuit Breaker 強制 Open の3つは最低限実行すること。

### Phase 5: 試練 (Red-Team) 🛡️
ワークフロー `/red-team` を実行し、AST構造マップ → Taint Analysis → `gitleaks` + `cargo audit` セキュリティスキャンと攻撃シミュレーションを行ってください。
いかなる脆弱性も許してはいけません。

## 完了条件
Phase 5まで全てのチェックをクリアし、`gitleaks` + `cargo audit` がオールグリーンであること。
