---
description: 攻撃者視点（Red Team）による容赦ないセキュリティ・堅牢性レビュー。AST構造マップとTaint Analysis駆動。
---

# /red-team - 悪魔の弁護人

あなたのコードに対する「攻撃者」となり、脆弱性やロジックの穴を徹底的に洗い出します。
通常のレビューでは見逃されがちな、エッジケースや悪意ある操作に対する耐性を高めます。

## 実行プロセス

**Sequential Thinking** を使用して、攻撃と防御のシミュレーションを行ってください。

### Phase 0: 構造マップ注入 (Architecture Deep Structure Map) 📡
// turbo
コードを「読む」前に、まず自動生成されたアーキテクチャ定義を読み込み、攻撃対象の「地図」を手に入れる。
```bash
# ツール (view_file) で ARCHITECTURE.md（リポジトリルート）を読み込む
```

`ARCHITECTURE.md` と `grep_search` の走査結果から以下を把握する：
- 全APIエンドポイント（Source = 外部入力の侵入口）の一覧
- 全構造体・トレイトの依存関係（Propagator = データの伝播経路）

### Phase 1: Taint Analysis (Source → Sink 追跡) 🎯
// turbo
自動化されたアンチパターン検出を実行し、潜在的な汚染経路や脆弱なコードパターンを特定する。
```bash
bash scripts/pattern-enforcer.sh
```
実行後、その標準出力を確認して Unsanitized Routes を特定する。

上記で特定された Source と Sink のペアについて、データが**サニタイズ（バリデーション）なしに到達可能か**を論理的に検証する。以下の「汚染方程式」を適用：
- Source（入力）が変数に入る → その変数がサニタイズなしに関数間を移動 → Sink（危険関数）に到達 = **脆弱性**
- サニタイズ関数の例: `.parse::<T>()`, `.validate()`, `.clamp()`, `is_verified()`, Rust型制約

### Phase 2: 攻撃シミュレーション (Attack) 😈
Phase 1 で特定された Taint ルートに対し、具体的な攻撃シナリオを立案する。

**Tool実行: Security Scan**
// turbo
自動セキュリティスキャナを実行し、既知の脆弱性とSecret漏洩がないか確認する。
```bash
echo "=== Secret Scan ===" && gitleaks detect -v 2>&1 | tail -5 && echo "=== Dependency Audit ===" && cargo audit 2>&1 | tail -10
```
※ 出力されたALERTやWarningは必ず修正対象に含めてください。

次に、論理的な攻撃シミュレーションを行います。
- **Fuzzing思考**: 極端に大きな値、空文字、制御文字、不正なUTF-8を送ったらどうなる？
- **Race Condition**: 並行処理でタイミングをずらしたら整合性が壊れないか？
- **Resource Exhaustion**: 無限ループやメモリリークを引き起こせるか？
- **Security Check**: SQLインジェクション、XSS、権限昇格の隙はないか？
- **Taint Route Exploitation**: Phase 1で特定した未サニタイズルートに悪意ある入力を流したら？

### Phase 3: 防御壁の確認 (Defense Check) 🛡️
攻撃に対して、現在のコードが耐えられるか検証します。

- `unwrap()`, `expect()`, `panic!()` でクラッシュしないか？
- `Result` は適切にハンドリングされているか？
- 型システムで不正状態（Illegal State）をコンパイル時に弾けているか？
- 全 Source → Sink ルートにサニタイズ層が挟まれているか？

### Phase 4: 改善提案 (Patch) 🩹
発見された脆弱性を塞ぐための具体的な修正コードを提示します。
「ただ動くコード」ではなく「壊れないコード」に修正してください。