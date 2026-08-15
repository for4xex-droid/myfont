---
description: 複雑なトピックを第一原理（根本的な真実）まで分解し、既存の前提を削ぎ落として再構築する「First Principles Breakdown」を実行する。
---

# /first-principles - 第一原理思考ワークフロー 🧠

このワークフローは、複雑な技術的問題、アーキテクチャ設計、または一般的なトピックを、イーロン・マスクが用いるような「第一原理思考（First Principles Thinking）」によって最小要素まで分解し、本質的な真実のみから再構築するために使用します。

## 実行コマンド

ユーザーが指定したトピック（例: 「AIエージェントの記憶フレームワーク」「分散システムの認証」など）に対して、以下のプロンプトをそのままLLMに投下し、深いレベルでの分析と再構築を実行してください。

```text
[topic] を [対象とするトピックや問題] に置き換えて、以下のプロンプトを実行してください。

"Break [topic] down using first principles thinking. Start by identifying every assumption people commonly make about this topic. Then strip each assumption away and ask: what is fundamentally, provably true here? Rebuild the concept from only what remains. Show me what changes when you remove inherited thinking."
```

## 出力の期待値
1. **前提の洗い出し**: 人々（または既存のシステム）が当たり前としている暗黙の前提（Inherited thinking）のリスト。
2. **前提の削ぎ落とし**: それらの前提を全て捨てた後に残る「絶対に証明可能な真実（Bedrock）」の特定。
3. **概念の再構築**: その真実だけをブロックとして使い、トピックをゼロから組み上げた全く新しい理解やアプローチの提示。
