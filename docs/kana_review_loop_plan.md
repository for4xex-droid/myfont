# 仮名レビューループ計画（P1-B 支援）v2.1

2026-08-12 策定・実コード監査反映（v2.1: 方位角定義の具体化・ゲートのライブラリ化・OTF非コミット前提を追記）。目的: 「し・い・と」で起きた迷走（突き抜け・浮遊・左右反転を目視で見落とし、直したつもりで終わる）を仕組みで再発防止し、核心20字の反復を高速化する。

**位置づけ**: P1-B（`docs/kana_parametric_plan.md`）の**内部品質装置**。盲検（S4）・出荷ゲート（S1）の置き換えではない。合否の最終権は数値ゲート（幾何）と人間（受け入れ）のみ。

## 0. 原則（役割の非重複）

| 層 | 担当 | 判定権 |
|---|---|---|
| 幾何・トポロジー | **数値ゲート B（コード）** | **合否を決める（必須レーン）** |
| ゲシュタルト観察 | Gemini Flash（API・C） | なし。観察JSONのみ（任意レーン） |
| 修正 | Grok／実装エージェント（D） | YAML差分の提案・適用のみ |
| 最終受け入れ | 人間 | 字ごとの accept と黄金凍結 |

固定ルール:
1. Gemini 出力に「OK/NG」を含めさせない（含んでも無視）。数値で測れるものは Gemini に聞かない
2. **C 未実行 ≠ 品質合格**。人間 accept の前提は **B green**。C は参考。キー無しで C を skip しても B の合否には影響しない（計画 v1 の「ゲートを通さない」は誤りだった）
3. **座標空間と方位角の定義（実装契約）**: 骨格 YAML・ゲート計測は現行 `COORDINATE_SPACE=svg_y_down_legacy`（Y下）。方位角は **`bearing = atan2(-dy, dx)`**（dy は legacy の Y下差分。符号反転により**画面の上が正**）で計算し、0°＝右・90°＝上・±180°＝左・−90°＝下 とする。これで `[15°, 75°]`＝「右上」が見た目どおりになる。ゲート報告に `coordinate_space` と `bearing_convention: "atan2(-dy,dx)"` を必ず載せる（生 atan2(dy,dx) で書くと左右反転ゲート自体が上下反転バグを起こす）
4. ゲートは「失敗検出」のみ。美醜・「字に見えるか」は C と人間（過剰工学禁止）

## 0.1 監査で確定した現状ギャップ（2026-08-12）

| 項目 | 現状コード |
|---|---|
| `kana_gate.py` | 輪郭数＋再現ハッシュのみ。接合・突き抜け・bbox・方位・ギャップ・自己交差・`gate_report.json` **なし** |
| YAML | `shi`/`i`/`to` に `motif`・`elements` あり。**`gate:` / `joins:` なし**。`elements[].id` は load 時に捨てられる |
| `kana_render.py` / vision | **不在**（チャット内アドホック freetype のみ） |
| 旧失敗回帰 | **なし**（`test_kana_curve.py` は主に `shi`） |
| `.env` / `proofs/review/` | **gitignore 未登録**（計画 v1 の「済み」は誤記） |
| 黄金比較 | `make_proofs --compare-golden` は **SHA256 厳密一致**（AE ではない） |
| 帯の正本 | `fontdb/config/kana_targets.yaml`・`kana_r1` **未作成**（G2 は parametric 側） |

## 1. 構成要素（MECE）

### 0′. 前提タスク（A/B より先）

実装不能なままゲート設計しても空転するため、**タスク0**を必須とする。

| 項目 | 内容 |
|---|---|
| gitignore | `.env`, `.env.*`, `proofs/review/` を追加 |
| loader | `load.py` が `elements[].id` を `SkeletonStroke`（または並行メタ）に保持。`joins:` / `gate:` をパースし、**必須キー欠落は load 失敗**（未知キー黙殺禁止） |
| データ構造 | `joins: [{from, to, mode}]` と `gate:` のスキーマを YAML コメント＋pytest で固定 |

### A. レンダリング正本化 — `engine/scripts/kana_render.py`（新規）

- 入力: OTF＋文字列（単字・3連・混植）
- 出力: `proofs/out/kana/{glyph_id}/{tag}.png`（サイズ・pad・baseline 固定）＋ `meta.json`（フォントSHA・骨格YAML SHA・レンダ設定・`coordinate_space`）
- 兼務禁止: S4 `scripts/make_proofs.py`（UI/HUD・盲検）は触らない。任意でラスタ核心だけ共通関数化可
- CLI: `regen.py --glyphs X` の後に本スクリプト、または `regen.py --render-kana` のどちらか一方に固定（DoDで決める）
- **OTF は非コミット前提**（`.gitignore` が `*.otf` を全域 ignore・掟10）。再現の正本は「骨格YAML SHA＋params SHA→OTF SHA」の連鎖であり、`meta.json` に **OTF SHA256 を必ず記録**する（黄金PNGだけ commit されても由来が追えるように）
- 黄金比較（初回）: **SHA256**（`make_proofs` 同型）。AE は後段で閾値ファイル＋version 付きにする（掟8）
- DoD: 同一入力SHA → 同一PNG。`proofs/out/` は既に gitignore 済み

### B. 数値ゲート v2 — コアは `engine/src/engine/kana/gate.py`（新規モジュール）＋ CLI `engine/scripts/kana_gate.py`

期待値は骨格YAMLの `gate:`（ハードコード禁止）。CLI `--expect-contours` は移行期のみ残し、最終は YAML 正本。

**二重実装の禁止**: 現状 `kana_gate.py`（CLI）と `tests/test_kana_curve.py` が輪郭数・再現ハッシュのロジックを複製している。v2 では判定コアを **importable なライブラリ関数**（`engine.kana.gate.run_gate(glyph_id, params) -> GateReport`）に置き、CLI と pytest の両方がそれを呼ぶ（ロジックのドリフト防止）。輪郭抽出は `engine.bridge.extract_contours_xy` を使う（join_solver には無い点に注意）。

| チェック | 実装メモ | 検出する失敗 |
|---|---|---|
| 輪郭数一致 | 既存。最終は `gate.expect_contours` | 点画浮遊による分裂 |
| 再現ハッシュ | 既存 | 非決定生成 |
| **接合** | **union 前**の要素ポリゴン交差/近接（`build_polys`）。`after_cleanup` 単独禁止（微小除去で偽グリーン） | 「と」空中浮遊 |
| **突き抜け** | 要素終点が相手輪郭の反対側縁から `max_overshoot_upm` 超 | 「と」の t 化 |
| **bbox帯** | 字面 x/y・アスペクト（粗い失敗検出。G2 参照帯の代替ではない） | 「）」化・横開き |
| **端点方位** | spine 端点＋接線。legacy Y下でセクター定義 | 左右反転 |
| **要素間ギャップ** | 非接合ペア最短距離 ∈ `[min,max]`（`bbox_distance` 等） | 「い」詰まり／離れ |
| 曲率 | **再実装しない**。`build_kana_curve` の `ValueError` を捕捉して report 化 | ホース／自己交差前 |
| 自己交差 | `SolveResult.self_intersect_suspect` を **FAIL に接続**（join20 と同型） | 肉付け破綻 |

- 出力: 人間可読行＋ `gate_report.json`（`coordinate_space` 必須フィールド）
- OTF 不要で大半が走る（`solve_glyph`）。render 依存は PNG 必須チェックのみ
- DoD:
  1. 旧失敗骨格3種（浮遊・貫通・反転）が pytest と CLI の両方で FAIL
  2. 現行 `shi`/`i`/`to` が green（各YAMLに `gate:` 宣言済み）
  3. `to` 接合宣言ありで、分離骨格→FAIL・現行→PASS

### C. 視覚観察 — `scripts/kana_vision_review.py`（新規・Gemini API）

- 入力: A のPNG（単字＋3連）＋対象文字
- プロンプト: `scripts/prompts/kana_review_v1.txt`（観察語彙固定。合否語禁止）
- 出力: `proofs/review/{glyph_id}/{iter}.json`（gitignore 必須）
- 制御: `GEMINI_API_KEY` は env のみ。画像SHAキャッシュ。1字1イテレーション1コール上限
- モデル: Gemini Flash 系（観察専用・安価）。リポジトリに既存クライアントなし → 新規薄ラッパ
- DoD: キー無し → `status=skipped`（exit≠0 でも B には影響しない）。CI は C を走らせない。人間 accept チェックリストで「C 実施 or 明示スキップ理由」

### D. 修正適用 — 運用手順（当面コードなし）

入力: B の `gate_report.json`（必須）＋ C 観察JSON（参考）。様式は §3。
変更可: 当該YAMLの `spine` / `width` / `gate` / `joins`。エンジン・ゲート閾値の緩和・他字YAMLは禁止。

### E. ループ制御・記録

```
regen → [A render] → B gate
  → FAIL: D 修正（≤5回）→ 戻る
  → green: [C 観察・任意] → D 審美微修正（≤3回）→ 人間判定
```

- 超過 → 手動エスカレーション（parametric §6 撤退ラインと整合）
- 記録: `proofs/review/`（git外）。凍結のみ `proofs/golden/kana_{glyph}/`

### F. 人間判定・黄金凍結

- accept 後: PNG 凍結＋骨格YAML SHA をコミットメッセージへ（掟18）
- 初回比較は **SHA**。AE は parametric の G3 と揃える段階で別ファイル化

### G. 運用

- `.env` / `.env.*` を gitignore（実装前に追加）
- コスト: Flash・キャッシュ・コール上限。月額アラートは任意
- CI: B 相当を **pytest 必須**（CLI は手元用）。C はCI外
- 仮名のみ regen の juu fill skip を「品質合格」と誤認しない（レポートで `skipped` 明示済み）

### 2.0 ランブック（E の具体コマンド列。1字あたり）

```bash
cd engine
# 1) 生成＋ゲート（B green まで繰り返し。修正は骨格YAMLのみ）
.venv/bin/python scripts/regen.py --params product_r1 --glyphs <gid>
.venv/bin/python scripts/kana_gate.py <gid>          # → gate_report.json
# 2) レンダ（人間確認・C 入力用）
.venv/bin/python scripts/kana_render.py --glyph <gid>
# 3) 任意: Gemini 観察
cd .. && python scripts/kana_vision_review.py --glyph <gid>
# 4) 人間 accept → 黄金凍結
#    proofs/golden/kana_<gid>/ にPNGコピー＋コミット（YAML SHA をメッセージに記載）
```

## 2. 作業順序と見積（監査反映）

| # | タスク | 依存 | 見積 |
|---|---|---|---|
| **0** | gitignore（`.env*`・`proofs/review/`）＋ loader（id/joins/gate） | なし | 2–3h |
| 1 | B コア: `engine/kana/gate.py` ライブラリ化＋接合・突き抜け・自己交差接続・`gate_report.json` | 0 | 3–5h |
| 2 | B: bbox・方位・ギャップ＋YAML `gate:` スキーマ | 1 | 2–3h |
| 3 | 旧失敗骨格3種の回帰テスト＋現行 shi/i/to green | 1,2 | 2–3h |
| 4 | A: kana_render.py（決定的レンダ＋meta＋SHA黄金） | なし（Bと並走可） | 2–3h |
| 5 | C: vision_review＋プロンプトv1＋キャッシュ | 4 | 2–3h |
| 6 | 「つ」でループ1周（手順穴修正） | 3,4,5 | 1周 |
| 7 | F: し・い・と黄金凍結＋PLAN/weekly/parametric 相互リンク | 3 | 0.5–1h |

合計 ≈ **14–21h**。**再発防止の完成点はタスク3**（C 無しでもループが閉じる）。着手順: **0→1→2→3**（必須）→4→5→6→7。

## 3. 修正プロンプト様式（D 固定文）

```
対象: engine/src/engine/kana/skeletons/{glyph}.yaml
入力: gate_report.json（必須）、vision観察JSON（参考）
制約:
- 変更可: 当該YAMLの spine / width / gate / joins の数値・宣言のみ
- 変更不可: エンジンコード、ゲート閾値の緩和、他の字のYAML、座標空間の切替
- 変更スカラー数 ≤ 12
- 各変更に1行の理由（どの FAIL/観察に対応するか）
出力: YAML差分＋理由リスト
検証: 変更後に kana_gate 相当が green であること（エージェントが実行）
```

## 4. YAML `gate:` / `joins:` 最小スキーマ（実装契約）

```yaml
# 例: to.yaml（概念。実装時にスキーマテストで固定）
joins:
  - {from: ten, to: main, mode: abut}   # abut=接して1輪郭 / separate=非接合
gate:
  expect_contours: 1
  max_overshoot_upm: 8                  # ten 終点の main 反対側への許容
  bbox:
    width: [280, 620]
    height: [520, 900]
    aspect_w_over_h: [0.35, 0.85]       # 「）」横開き検出
  tips:
    - {element: main, end: exit, bearing_deg: [15, 75]}  # 右上抜き（§0-3 の atan2(-dy,dx) 規約）
  gaps:
    - {a: left, b: right, min_upm: 40, max_upm: 220}     # い用
```

未知の必須キー欠落 → load 失敗。使わないキーは省略可（スキーマで optional 明示）。

## 5. 非目標（スコープ外）

- Gemini による合否・スコアリング
- 画素類似度での参照書体接近（掟9）
- 盲検 S4 / ship_gate S1 の置き換え
- G2 参照帯の fontdb 凍結（`kana_targets.yaml`）— **parametric 側**。本ループの bbox は失敗検出用の粗い帯のみ
- `の`・`あ` の明示リング生成（parametric §2）
- `make_proofs` への仮名デバッグ機能の混入

## 6. リスクと手当

| リスク | 手当 |
|---|---|
| Gemini観察ノイズ | 語彙固定・severity≤2は無視可 |
| ゲート過剰で窒息 | 失敗検出のみ。美醜は C＋人間 |
| micro-cleanup 偽グリーン | 接合は union 前ポリゴンで判定 |
| 方位の座標バグ | `coordinate_space` 必須・legacy でセクター定義 |
| `.env` 漏洩 | タスク0で gitignore |
| `proofs/review/` が tracked | タスク0で gitignore |
| API費 | SHAキャッシュ＋コール上限 |
| YAML振動 | 反復上限＋編集バジェット＋iter記録 |
| juu skip を合格と誤認 | レポートで skipped 明示・仮名DoDに使わない |
| `gate:` 黙殺で偽green | loader が必須キーを検証 |

## 7. 文書接続

- PLAN §7.4: P1-B の次に「内部ループ: 本ファイル（B必須・C任意）」を1行追加
- `docs/kana_parametric_plan.md` §4 ループ図に `kana_gate` / `kana_render` を挟む
- `docs/weekly.md`: 今週の一手にタスク0–3を記載

## 8. 受け入れ DoD（仕組み全体）

1. タスク0完了（gitignore＋loader）
2. 旧失敗3種 FAIL・現行 shi/i/to PASS（pytest）
3. 単字: regen → kana_render → PNG+meta が一手順で再現
4. C は任意・キー無し skip 可。CI は B のみ
5. 人間 accept テンプレ: 「B green 必須／C 任意／黄金 SHA 凍結」
6. PLAN・parametric・weekly から本計画へ相互リンク済み
