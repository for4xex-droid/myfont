# ⚡ Antigravity Vibe Workflow

MyMincho 移植版。コマンド対応は `.agent/PROJECT_MAP.md`。鉄の掟は `GOLDENRULES.md`。

Everything Antigravity + Golden Rule + GitHub MCP を統合した、究極のバイブコーディングフロー。

## 🎯 哲学

- **記憶の外出し**: タスクと進捗はすべてGitHub Issueに記録する。LLMのコンテキスト飽和を解決。
- **品質の自動化**: コードの作法はGolden Rule / Skillsが担保する。
- **完全同期**: 作業再開時はIssueからコンテキストを復元する。

## 🔄 The Cycle

### 1. START: タスク作成
思考をGitHubに実体化させる。

```bash
/task <やりたいこと>
# 例: /task ログイン画面にGoogle認証ボタンを追加
```
→ AIがIssueを作成し、番号を取得する。

### 2. PLAN: 計画と同期
Golden Ruleに基づいた設計を行い、GitHubに残す。

```bash
/plan #<Issue番号>
```
→ AIが計画を立案し、Issueのコメントとして投稿する（記憶の永続化）。

### 3. IMPLEMENT: 実装
思考をコードに変換。

**オプション: 迷ったら会議**
```bash
/brainstorm <お題>
```
→ AIが3つのプラン(堅実/革新/別解)を出して比較検討する。

**オプション: 神の一手 (究極コンボ)**
```bash
/god-mode <お題>
```
→ 「会議→実装→自己修正→セキュリティ監査」を全自動で行う。

```bash
/tdd <具体的な実装内容>
```
→ AIが言語ごとのGolden Rule (Rustならunwrap禁止など) を守って実装する。

### 4. REFINE: 自己研鑽 (Optional)
実装されたコードの品質を極限まで高める。

**品質向上ループ**
```bash
/reflexion <ファイルパス>
```
→ AIが「批評→修正」のループを最大3回回し、Golden Rule遵守率と堅牢性を95点以上にする。

**悪魔の証明 (高セキュリティ向け)**
```bash
/red-team <ファイルパス>
```
→ 攻撃者視点で脆弱性を突き、堅牢性をテストする。

### 5. REVIEW & LAND: 着地
品質確認とPR作成。

```bash
完了したらPR作って
```
→ AIが `/code-review` を実行後、GitHub上にPRを作成し、Issueと紐付ける。

### 6. SYNC: 同期
ローカルの変更をアップロード。

```bash
git push
```

## 🧠 コンテキスト復帰（Resume）

作業を中断した後や、翌日に再開する場合：

```bash
/task #<続きのIssue番号>
```
→ AIがGitHub上の履歴（計画、コメント、現状）を読み込み、即座に「前回の続き」から開始する。

**これにより、LLMのコンテキストウィンドウ制限を超えた「永続的な記憶」を実現。**

## 🔑 キーコマンド

| コマンド | 用途 | MCPの動き |
|---------|------|-----------|
| `/task` | タスク管理 | Issue作成・読込 |
| `/plan` | 設計 | Issueコメント投稿 |
| `/brainstorm`| 会議 | ToT (3案比較) |
| `/tdd` | 実装 | (ローカル作業) |
| `/god-mode` | 全自動 | 究極コンボ (会議→実装→修正→監査) |
| `/reflexion` | 自己修正 | Sequential Thinking (ループ) |
| `/red-team` | セキュリティ| 攻撃シミュレーション |
| `PR作成` | 提出 | PR作成・リンク |

## ⚠️ MCP未設定の場合

GitHub MCPが未設定の場合でも、ワークフローは動作します：

- `/task` → Issue操作はスキップ、通常の計画立案を実行
- `/plan` → GitHub投稿なしで計画を画面表示

**推奨**: フル機能を使うには `mcp_config.json` にGitHub設定を追加してください。
詳細は `mcp-configs/README.md` を参照。

## 📊 ワークフロー比較

| シナリオ | 従来 | Vibe Workflow |
|----------|------|---------------|
| 中断後の再開 | ファイルを漁る、README読む | `/task #123` で即復帰 |
| 進捗共有 | 手動でドキュメント更新 | Issueに自動記録 |
| 再実装防止 | 記憶頼り（忘れる） | Issue検索で重複検出 |
