# MyMincho `.agent` ワークフロー

tango-apps の `.agent/workflows` をこのリポジトリへ移植し、Cursor のスラッシュコマンドから使えるようにした。

## 使い方

チャットで次のように呼ぶ（例）:

```
/plan 8c「の」のテールを足す
/tdd cubic_fit の穴輪郭ゲート
/task あ の骨格を追加
/code-review
/ship
```

エージェントは:

1. `.agent/PROJECT_MAP.md` でコマンドと正本を MyMincho 向けに読み替える
2. `.agent/workflows/<name>.md` の手順を実行する
3. `GOLDENRULES.md` に反する指示は実行しない

索引とサイクルは `workflows/VIBE_WORKFLOW.md`。日常の3ループ（計測・エンジン・字形）は従来どおり `WORKFLOW.md`。

## 配置

| パス | 役割 |
|---|---|
| `.agent/workflows/` | ワークフロー正本（Antigravity `/command` 互換） |
| `.agent/PROJECT_MAP.md` | cargo/npm/Aiome → pytest/仮名/黄金 の読み替え |
| `.cursor/commands/` | Cursor スラッシュコマンド（正本を読む薄いラッパ） |
| `.cursor/rules/agent-workflows.mdc` | `/plan` 等を見たらワークフローを読む指示 |
