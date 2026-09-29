# タイポアート用アルファベット書体 実装計画 v1

2026-09-29 策定。実装はまだ行わない。
正本の優先順: `docs/生成書体の仕様.md` ＞ `GOLDENRULES.md` ＞ 本書 ＞ `docs/latin_display_plan.md`（制作計画。様式定義と工程の粗い順番）。

本書は「どのファイルに、何を、どの順で、どのテストを先に書いて作るか」を決める。数値の初期値は設計パラメータであり、仕様の未決定項目ではない。仕様の未決定項目は本書でも埋めない。

---

## 0. 監査で確定した事実（2026-09-29、実コード）

| # | 事実 | 計画への影響 |
|---|---|---|
| F1 | ツールは engine/.venv に揃っている: fontmake 3.12.1、ufo2ft 3.9.0、fontTools 4.63.0（cu2qu 同梱）、skia-pathops 0.9.2、freetype、numpy、Pillow。`hb-view` は CLI にある。uharfbuzz は engine/.venv に**ない** | 組見本は `hb-view` 経由（`scripts/make_proofs.py` と同じ）。依存を増やさない |
| F2 | 回帰の基準: `engine/tests` 233 件が緑 | ラテン書体の作業中も 233 件の緑を保つ。既存モジュールは原則変更しない |
| F3 | `bridge.build_ufo` は字メタ（CORE/EXTRA/kana）必須・全字幅 1000 固定・ascender 880・capHeight 800 を埋め込む | ラテン書体用 UFO 書き出しは**新規**にする。`build_ufo` は触らない |
| F4 | `bridge.compile_otf` は OTF だけを出す | OTF と TTF の両方を出すコンパイラを**新規**にする（仕様 §2 の決定） |
| F5 | `join_solver.micro_area_threshold` の床は 3,500 UPM²（打ち込みの島対策） | ポップの A・4・R の小さい穴や、ディドンの細い部分が消えるおそれがある。ラテン書体用は床を様式ごとにし、**穴（負面積）は除去禁止**にする |
| F6 | `curve_fit.fit_closed_contour` は角検出＋cubic フィット＋Hausdorff ゲートを持つ。**x/y 極値への点挿入はない** | 極値挿入と直線スナップを**新規**にする |
| F7 | `geometry._offset_sides` は法線オフセット（半幅列を受け取る） | ペンは「半幅列を作る関数」として足せる。既存の関数は変えない |
| F8 | `ship_gate.py` は cmap 欠字・`.notdef`・垂直メトリクス（既定 880/−120）・name・輪郭スモークを見る。**収録外の字があっても落ちない**。GSUB/GPOS は情報表示だけ | ラテン書体の収録は「37字ちょうど」のため、完全一致の検査を足す。メトリクスは様式の値を引数で渡す |
| F9 | `ship_gate.check_name_table` は name ID 1/2/3/4/6 と、著作権またはライセンス（ID 0/13/14）を要求する | 命名（仕様で未決定）と著作権・ライセンス文（**仕様に項目がない**）が決まるまで出荷ゲートは通らない。これは正しい挙動 |
| F10 | `*.otf` / `*.ttf` は gitignore（掟10） | 生成物はコミットしない。正本は YAML、黄金はハッシュと PNG |
| F11 | `scripts/generated_face_spec.py` が仕様を読み、未決定があれば引き渡しを拒否する（現状は「太さの数」「命名の規則」でブロック） | 書き出し CLI の入口に組み込む。命名などが決まったら値を読む機能を足す |
| F12 | 仮名 DSL（`engine/kana/schema.py`）は未知キーを拒否する厳格スキーマ | ラテン書体の DSL も同じ流儀で作る（黙って無視しない） |

---

## 1. 決定ゲート（仕様の項目と、仕様にない項目）

| ID | 内容 | 状態 | 止まる工程 | 決めるまでの扱い |
|---|---|---|---|---|
| S-形式 | OTF / TTF | 済: 両方 | — | — |
| S-幅 | 等幅 / プロポーショナル | 済: プロポーショナル | — | — |
| S-太さ | ウェイト数 | **未決定** | 工程 11 | 1ウェイト分の設計値だけで進める |
| S-命名 | ファミリー名・スタイル名・ファイル名、4様式を別ファミリーにするか | **未決定** | 工程 12 | 内部ビルドは WIP 印付きの作業名。出荷ゲートは通らない |
| S-収録追加 | 小文字・約物・日本語 | **未決定** | — | 作らない |
| D5 | **空白 U+0020 を入れるか**（必須37字に含まれていない。`SALE 50` のような組版には空白が要る） | **未決定（仕様に項目なし）** | 工程 10 の文面・工程 12 | 空白は入れない。組見本は `/` 区切りの文面だけにする |
| D6 | **著作権表記・ライセンス文・fsType・ベンダーID・バージョン文字列**（ship_gate が name ID 0/13 を要求する） | **未決定（仕様に項目なし）** | 工程 12 | 埋めない。出荷ゲートの失敗で止める |
| D0 | 4様式の定義 | 済: モダン＝幾何サンセリフ、シック＝ディドン | — | — |

D5 と D6 は、仕様書に項目を足してから決める。この計画では決めない。

---

## 2. 設計の核（実装前に固定する判断）

### 2.1 正本と生成物

- 正本は YAML（骨格・様式・比例・字間・カーニング）。UFO・OTF・TTF は毎回生成する
- 生成は決定的にする。同じ YAML と同じコードからは同じ輪郭ハッシュが出る
- 手描きへの撤退（§8）が起きた様式だけ、UFO が正本になる（`fonts_out/latin/<style>.ufo`、git 管理）

### 2.2 座標

- 内部はフォント空間（Y 上向き、UPM 1000）。掟1
- 骨格 YAML は**正規化座標**で書く: x は字の本体幅に対する比 [0, 1]、y はキャップハイトに対する比（0 がベースライン、1 がキャップハイト）
- 実座標 = 様式の比例表（本体幅）× キャップハイトで展開する。字幅を様式ごとに変えても骨格は1つで済む
- オーバーシュートは骨格に書かない。様式が「丸」「尖り」の役割に応じて足す

### 2.3 太さの割り当て

角度だけで太細を決めると、ディドンの A の左脚が太くなる（垂直軸のペンでは左右どちらの脚も太く出る）。そこで太細は2段で決める。

1. **役割（role）で直線の太細を決める**: 骨格の各 stroke に `thick` / `thin` / `bar` / `bowl` を付ける。伝統的な割り当てを骨格側に持つ（A=左細・右太、V=左太・右細、N=縦細・斜め太、M=左縦細・第1斜め太・第2斜め細・右縦太、K=腕細・脚太、X=＼太・／細、Y=左太・右細、Z=斜め太・横細、W=太細太細、7=斜め太、4=斜め細）
2. **曲線（bowl）の中の太さ変化だけペン式で出す**: `nib(θ, c)` の |sin(φ − θ)| 型

モダンとポップは役割を無視して一定幅（横画だけ 0.88–0.93 倍）。

### 2.4 ウェイトの作り方

ウェイトごとにパラメータから**直接生成**する。マスター補間はしない。

理由: 納品物は静的な OTF/TTF（仕様 §2）で、可変フォントは要らない。ウェイトごとに cubic フィットすると節点数が一致せず補間できないが、直接生成ならその問題が起きない。S-太さの決定後は、様式 YAML にウェイトの段を足すだけで済む。

### 2.5 曲線

- 輪郭の生成経路: 骨格 → 密サンプル → ペンで左右オフセット → 多角形 → pathops union → 穴保護付き微小除去 → 向きの正規化 → cubic フィット → 直線スナップ → 極値挿入 → 整数丸め → 再検査
- 漢字用 `rdp_polyline` は使わない
- 丸め後に自己交差と輪郭数を**もう一度**検査する（丸めで交差が生まれうる）

---

## 3. ファイル構成（新規のみ。既存は §9 の波及表）

```
engine/src/engine/latin/
  __init__.py
  glyphset.py        # 必須37字 ⇄ グリフ名（AGL: A..Z, zero..nine, slash）
  schema.py          # 骨格 YAML の厳格スキーマ（未知キー拒否）
  load.py            # 骨格ローダ（variants 解決）
  style.py           # 様式 snapshot（凍結 id＋内容ハッシュ）
  pens.py            # mono / nib の半幅列
  terminals.py       # flat / round / serif_bracketed / serif_hairline / ball / spur / apex
  joins.py           # apex / T / L / crotch / bowl_join の食い込みと細め
  build.py           # 1字の生成パイプライン（§2.5）
  outline.py         # 直線スナップ・極値挿入・丸め・再検査
  spacing.py         # 側面規則
  kerning.py         # ペア候補と光学ギャップ計測
  ufo.py             # ラテン書体用 UFO 書き出し（字幅・メトリクス・kerning・WIP 印）
  compile.py         # OTF と TTF の両方をコンパイルし、両者の差を検査
  gate.py            # 字ゲート・セットゲート（ライブラリ関数。CLI と pytest が同じものを呼ぶ）
  measure.py         # OTF → freetype でスカラー計測（掟4）
  skeletons/*.yaml   # 37字（A.yaml … Z.yaml, zero.yaml … nine.yaml, slash.yaml）
  styles/{modern,classic,chic,pop}.yaml
  targets/{modern,classic,chic,pop}.yaml   # 参照帯（extractor_version 付き。§6）

engine/scripts/
  latin_build.py     # --style --glyphs → UFO＋OTF＋TTF（内部用。WIP 印）
  latin_gate.py      # 字・セットゲートの CLI
  latin_proof.py     # 固定文面の組見本（hb-view）
  latin_sheet.py     # 様式比較シート・1パラメータ感度 PNG
  latin_export.py    # 引き渡し。仕様ゲート → ship_gate → 両形式

engine/tests/test_latin_*.py
data/glyphset_latin_required.txt           # 仕様から派生。一致をテストで保証
fontdb/config/corpus_latin.yaml            # ラテン参照（ライセンス確認済みのみ）
fontdb/src/fontdb/probes/latin_*.py        # ラテン probe
proofs/latin/<style>/                      # 組見本
proofs/golden/latin_<style>/FREEZE_v*.json # 黄金（掟18）
docs/latin_mapping.md                      # 役割・端物・接合の語彙表（骨格を書く人向け）
```

---

## 4. データ形式

### 4.1 骨格 YAML（例: A）

```yaml
glyph: A
unicode: 0x0041
structure: apex_diagonals
strokes:
  - id: left
    spine: [[0.00, 0.00], [0.50, 1.00]]     # 直線は2点、曲線は 3n+1 点の cubic 列
    role: thin
    ends: {start: foot, end: apex}
  - id: right
    spine: [[0.50, 1.00], [1.00, 0.00]]
    role: thick
    ends: {start: apex, end: foot}
  - id: bar
    spine: [[0.22, 0.30], [0.78, 0.30]]
    role: bar
    ends: {start: none, end: none}
joins:
  - {a: left, b: right, type: apex}
  - {a: bar, b: left, type: T}
  - {a: bar, b: right, type: T}
expect: {contours: 2, holes: 1}
variants:
  classic:
    joins: [{a: left, b: right, type: apex_cut}]
```

規則:
- `ends` の値は語彙（`foot` / `apex` / `none` / `open` / `round_end` など）。**どのテンプレに展開するかは様式が決める**（例: `foot` はモダンで `flat`、クラシックで `serif_bracketed`、ポップで `round`）
- `variants` は構造の差だけ。未知キーは拒否する
- 1字あたりの自由スカラー（座標以外の数値）は 12 以下（仮名の編集バジェットを引き継ぐ）

### 4.2 様式 YAML（例: modern）

```yaml
style_id: modern_v1
cap_height: 700
overshoot: {round: 0.018, apex: 0.025}     # キャップハイト比
pen: {type: mono, stem: 0.13, bar_ratio: 0.90}
terminals: {foot: flat, apex: apex_sharp, open: flat, round_end: flat}
joins: {crotch_thin: 0.82}
proportions: {H: 0.74, O: 1.00, E: 0.50, S: 0.52, "/": 0.42, ...}   # 本体幅（キャップハイト比）
sidebearing: {base: 0.30, straight: 1.00, round: 0.60, diagonal: 0.12}
vertical: {ascender: 760, descender: -140}  # 全字の bbox を覆うこと（§5 G-M）
micro_area_floor: 400                        # UPM²。穴は対象外
curve: {max_error: 0.6, corner_deg: 30, max_anchors_per_contour: 12}
```

- `style_id` は凍結 id。数値を変えたら id を上げる（掟16 と同型）。内容ハッシュを UFO lib と黄金に記録する
- 様式 YAML は仕様の値（形式・命名）を持たない

### 4.3 字間・カーニング

- 側面: 各字の左右を `straight` / `round` / `diagonal` / `open` に分類した表を骨格側に持つ（`sides: {left: straight, right: round}`）
- カーニング: 様式 YAML に `kerning:` として明示ペアだけ持つ。値は `kerning.py` の自動計測で**候補**を出し、作者が採用した値だけを書く（選好は `log_preference.py` で keep/discard/shift）

---

## 5. ゲート一覧（どこで何を落とすか）

| ID | 内容 | 実装 | 失敗時 |
|---|---|---|---|
| G-S | 骨格スキーマ（未知キー・座標範囲・自由スカラー ≤12） | `schema.py` | ロード失敗 |
| G-K | 曲率半径 ≥ k×半幅（ペンの折り返し防止） | `build.py`（既存 `min_curvature_radius`） | 字 fail。YAML 側を直す |
| G-C | 輪郭数・穴の数が `expect` と一致 | `gate.py` | fail |
| G-X | 自己交差 0（丸め後に再検査） | `outline.py`＋pathops | fail |
| G-F | cubic フィット誤差 ≤ `max_error`、輪郭あたり節点 ≤ 上限、丸い部分の極値にオンカーブ点 | `outline.py` | fail（折れ線へは戻さない） |
| G-L | 直線部は軸に平行（±0.5° 以内をスナップ、スナップ後は 0°） | `outline.py` | fail |
| G-O | オーバーシュートが帯内（丸・尖り別） | `gate.py` | fail |
| G-M | 全字の bbox が ascender/descender と winAscent/winDescent に収まる（欠け防止） | `gate.py` | fail |
| G-R | 再現性（同じ入力なら輪郭ハッシュ一致） | pytest | fail |
| G-SET | 縦ステム中央値がセット内 ±5%。コントラスト比と応力角が様式帯内 | `gate.py`＋`measure.py` | fail |
| G-SEP | 4様式の分離（§6.3） | `latin_sheet.py`＋`gate.py` | fail |
| G-TT | TTF と OTF の差（二次曲線変換の誤差）: 2000px ラスタで IoU ≥ 0.999、輪郭 Hausdorff ≤ 1.0 UPM | `compile.py` | fail |
| G-SPEC | 仕様に未決定が残っていない。cmap が必須集合と**完全一致**（収録外は fail） | `generated_face_spec.py`＋ship_gate 拡張 | 書き出し拒否 |
| G-SHIP | `ship_gate.py` を OTF と TTF の両方に。様式のメトリクスを引数で渡す。FontBakery universal は WARN の採否を `ship_gate_rules.md` に書く | 既存＋引数 | fail |
| G-EYE | 組見本の作者目視と黄金凍結 | `latin_proof.py` | 凍結しない |
| G-BLIND | 盲検（様式当て 2/3、使えるか 2/3） | パック生成 | 出荷しない |

---

## 6. 参照と計測（並走トラック R）

### 6.1 コーパス

- `fontdb/config/corpus_latin.yaml` を新設。候補: Jost・Poppins（幾何サンセリフ）、Cinzel・EB Garamond（ローマン）、Playfair Display・Bodoni Moda（ディドン）、Nunito・Fredoka（丸ゴシック）
- 各エントリの完了条件は、ライセンス条文の確認と SHA256（掟12・掟10）
- 可変フォント（Jost・Playfair Display・Bodoni Moda・Nunito・Fredoka は可変の可能性が高い）は、wght を明示してインスタンス化してから測る（掟8b）。どの wght を「Regular 相当」とするかをエントリに記録する

### 6.2 probe（ラテン）

`fontdb/config/probe_defs.yaml` に定義を置く（掟7）。extractor_version は 1 から始める。

| probe | 測るもの |
|---|---|
| `latin_h_stem` | H の縦ステム・横画（交点を避けた複数走査線の中央値） |
| `latin_o_contrast` | O の最大幅/最小幅、最小幅の方向（応力角） |
| `latin_overshoot` | O・A・V の上下はみ出し（キャップハイト比） |
| `latin_proportion` | O/H/E/S/M の幅÷キャップハイト |
| `latin_serif` | H 足元の突出長・厚み（セリフなしは値 0 の ok。掟6） |

自作面は必ず OTF にコンパイルしてから同じ freetype profile で測る（掟4）。

### 6.3 様式分離

- 空間: （コントラスト比、応力角、セリフ長、角丸半径、O の幅/高、ステム/キャップハイト）
- 各軸を参照8書体の範囲で正規化し、様式間のユークリッド距離を出す
- 閾値は工程 6（パイロット）の実測で決め、`targets/` に凍結する。凍結前は fail にしない（掟8の精神）

### 6.4 独自性（権利）

- IoU とレイ距離（`scripts/rights_distance.py`）で、自作と同じ系統の参照との距離を測る。参照同士の距離を基準線とし、それより近い字を「寄りすぎ」として記録する
- 合否や自動調整の目的関数にはしない。寄りすぎの字は骨格を人が見直す
- 各様式に**シグネチャ特徴**を3つ以上決め、骨格に明記する（例: モダンの M の開き角、G のひげの有無、R の脚の出方）。幾何サンセリフは互いに似やすいため

---

## 7. 工程（TDD。各工程で先に失敗するテストを書く）

表の「テスト（先に書く）」が工程ごとの RED。緑にしてから次へ進む。どの工程でも `engine/tests` の既存 233 件は緑のまま。

| # | 工程 | テスト（先に書く） | 実装 | DoD | 工数 | 依存 |
|---|---|---|---|---|---|---|
| 1 | 字集合 | 仕様の必須集合＝`data/glyphset_latin_required.txt`＝`glyphset.py` の37名。AGL 名の往復。収録外の字は拒否 | `glyphset.py`、txt | 3者一致が pytest で固定 | 2–3h | — |
| 2 | スキーマとローダ | 未知キー拒否、座標範囲外拒否、variants の解決、スカラー上限。`H.yaml`・`O.yaml` の読み込み | `schema.py`、`load.py`、`H.yaml`、`O.yaml` | 2字がロードでき、壊れた YAML が全部拒否される | 6–10h | 1 |
| 3 | 様式とペン | style id とハッシュの凍結、mono の半幅一定、nib で θ に直交する方向が最細、role 優先 | `style.py`、`pens.py`、styles 4本の骨組み | 合成サンプルでペン式が数値どおり | 6–10h | 2 |
| 4 | 端物と接合 | 各テンプレの輪郭が閉じて自己交差なし、食い込み後 union で1輪郭、apex のオーバーシュート量、crotch の細め | `terminals.py`、`joins.py` | H・A・V 相当の合成骨格で G-C・G-X 緑 | 10–16h | 3 |
| 5 | 輪郭パイプラインと UFO/コンパイル | 穴保護（小さい穴が残る）、極値挿入、直線スナップ、丸め後の再検査、TTF/OTF 差（G-TT）、字幅が比例表どおり、WIP 印が付く | `build.py`、`outline.py`、`ufo.py`、`compile.py`、`latin_build.py` | `H` `O` がモダンとポップで OTF・TTF まで通り、G-C/G-X/G-F/G-L/G-TT 緑 | 12–20h | 4 |
| 6 | パイロット | `H O B V S 0` × 4様式で全字ゲート緑、様式分離の計測値が出る | 残り4字の骨格、nib の曲線、`latin_sheet.py`、`measure.py` | 比較シート1枚。作者目視で4様式を区別できる。分離閾値を凍結 | 20–35h | 5・R1 |
| 7 | モダン37字 | 37字の G-C〜G-M、G-SET | 骨格31字、variants | 組見本の黄金 `latin_modern/FREEZE_v1` | 20–35h | 6 |
| 8 | ポップ37字 | 同上。小さい穴の保護（A・4・R・8） | ポップの variants、角丸 | 黄金 `latin_pop/FREEZE_v1` | 15–25h | 7 |
| 9 | シック・クラシック37字 | 同上。ヘアラインの最小幅（ラスタで途切れない下限）、セリフの G-X | nib 様式の variants、serif テンプレの調整 | 黄金 `latin_chic` / `latin_classic` | 70–120h | 8 |
| 10 | 字間・カーニング | 側面分類が全字にある。固定文面の字間ギャップのばらつきが帯内。カーニングは明示ペアだけ（上限 120 ペア/様式） | `spacing.py`、`kerning.py`、UFO の kerning と groups | 固定文面で歩行なし。黄金を v2 へ | 各様式 10–20h | 7–9 |
| 11 | ウェイト（S-太さ決定後） | 各ウェイトで全ゲート緑、ステムが段ごとに単調に増える | 様式 YAML に段を追加 | 各ウェイトの黄金 | 様式あたり 15–30h | S-太さ・10 |
| 12 | 引き渡し（S-命名・D5・D6 決定後） | 仕様パーサが命名を読む。未決定なら終了コード 2。cmap 完全一致。両形式で ship_gate 緑。ファイル名が仕様どおり | `generated_face_spec.py` 拡張、`latin_export.py`、ship_gate に完全一致オプション | 両形式 × 全様式 × 全ウェイトが揃う | 10–15h | S-命名・D5・D6・11 |
| 13 | 盲検 | パックに書体名が出ない、対応表は SEALED | `make_latin_blind_packet.py` | 評価者3名、様式当て 2/3・使えるか 2/3 | 4–8h ＋評価待ち | 10 |

並走トラック R（工程 1 と同時に始められる）:

| # | 内容 | DoD | 工数 |
|---|---|---|---|
| R1 | corpus_latin の取得（ライセンス確認・SHA・インスタンス化） | 8書体が `acquired: true` | 4–8h |
| R2 | ラテン probe 5種＋合成 fixture の単体テスト | 8書体で `ok` | 8–12h |
| R3 | 参照帯 `targets/*.yaml` の凍結（extractor_version 付き） | 工程 6 の前に凍結 | 2–4h |

合計の目安: 1ウェイトで 4様式の完成まで（工程 1–10、13、R）**約 230–370h**。

---

## 8. 撤退ライン

| 条件 | 撤退先 |
|---|---|
| 工程 5 で `O` が G-F（フィット誤差・節点・極値）を 16h 以内に満たせない | 生成後の輪郭を直接書かず、骨格から解析的に cubic オフセットを作る経路（Tiller–Hanson 型）へ切り替える。これも 16h で満たせなければ手描き（下記） |
| 工程 6 で4様式が区別できない | 字を増やす前に `latin_display_plan.md` §1 の定義とシグネチャ特徴を見直す |
| 工程 9 でヘアラインが 48px で途切れる、またはセリフ接合の自己交差が消えない | その様式の Regular を Glyphs で手描きし、`fonts_out/latin/<style>.ufo` を正本にする。エンジンはゲート・字間・カーニング・書き出しだけに使う（仮名の方式Aと同型） |
| 1様式の37字が工数の悲観値を超えた | その様式を後回しにし、他様式を先に閉じる |

撤退した様式でも、ゲート（§5）と引き渡し（工程 12）は同じものを通す。

---

## 9. 既存ファイルへの波及

| ファイル | 変更 | 理由 |
|---|---|---|
| `engine/pyproject.toml` | `package-data` に `latin/skeletons/*.yaml`、`latin/styles/*.yaml`、`latin/targets/*.yaml` を追加 | 入れないとインストール環境で YAML が見つからない |
| `engine/scripts/ship_gate.py` | `--exact-glyphset` オプション（収録外の字も fail）を追加。既定の挙動は変えない | F8 |
| `scripts/generated_face_spec.py` | 工程 12 で命名・ウェイトの値の読み取りを追加 | F11 |
| `fontdb/config/probe_defs.yaml` | ラテン probe の定義を追加 | 掟7 |
| `docs/ship_gate_rules.md` | ラテン書体の節（FontBakery WARN の採否、ヒンティングなしの明記） | G-SHIP |
| `.gitignore` | 変更不要（`*.otf` `*.ttf` は既に除外）。`engine/output/latin/` が build 系の除外に入るか工程 5 で確認 | 掟10 |
| `docs/weekly.md`・`docs/latin_display_plan.md` | 工程の完了ごとに更新 | 運用 |

変更しないもの: `bridge.py`、`join_solver.py`、`curve_fit.py`、`geometry.py`、`strokes.py`、`kana/*`。ラテン書体のコードからは import して使うだけにする。挙動を変えたくなったら、ラテン側でラップする。

---

## 10. 検証（計画の自己監査。/perfect-plan の5観点）

**構造（二重実装・幻覚の排除）**: 新規モジュールは既存に同名・同機能がないことを確認した（UFO 書き出しとコンパイルは F3・F4 の理由で別物が必要）。変更対象の既存ファイルは §9 のとおり実在する。

**要件カバレッジ**: 仕様 §2 の各項目を、決定済み（形式・幅・収録）は工程に、未決定（太さ・命名・収録追加）はゲートに割り当てた。仕様にないが引き渡しに要るもの（空白、著作権・ライセンス・fsType）を D5・D6 として追加した。

**依存と波及**: 既存 233 件のテストに触れない構成にした。pyproject の package-data 漏れを §9 に入れた。

**悪魔の弁護人**:
1. 最悪のシナリオ: エンジン出力が「機械っぽい」と判定され、仮名と同じく手描きに負ける。対策として、工程 6 のパイロットで早期に判定し、撤退先を §8 に決めてある
2. 見落としやすい前提: 既存の微小輪郭除去の床（3,500 UPM²）が小さい穴を消す（F5）。角度だけのペンではディドンの A が崩れる（§2.3）。TTF の二次曲線変換で形が動く（G-TT）。ウェイトごとのフィットで補間できなくなる（§2.4 で補間自体をやめた）
3. やらない選択: 1ウェイトの 148 字（37×4）だけなら、手描きの方が速い可能性がある。エンジンの回収は、ウェイト展開・一貫性ゲート・字間の再計算で得る。S-太さが「1」に決まった場合は、工程 6 の実測時間を見て、手描き中心に切り替えるかを再判断する

**実行順序**: 工程 5（コンパイル）が工程 6（計測）より前、R3（参照帯凍結）が工程 6 より前、工程 10（字間）が工程 11（ウェイト）より前、工程 12 は仕様の決定待ち。R は工程 1 と並走する。

判定: **PATCH 済み**。上の指摘は本文へ反映した。残るのは仕様側の決定（S-太さ・S-命名・D5・D6）だけ。
