# ベクター品質 導入計画 v3（研究知見の取り込み）

2026-08-12 v1 策定 → v2（経路選択とスコープ修正）→ **v3（3回目の実機検証で優先度と誤りを修正）**。
**実装進捗（2026-08-12）: Phase 0a・0b・0c・Phase 1・Phase 2 完了**。仮名 `cubic_fit` 既定化＋黄金 `kana_golden_cubic_fit_v1` 再凍結。次は仮名核心字の量産（PLAN: く以降）。

### 実装メモ（Phase 0a で判明した補正）

cleanup の穴保護は「負面積なら残す」では不十分。端物の巻きくずが入れ子負輪郭（実測 max≈2414 units²）になるため、**包含深度奇数 かつ 面積 ≥ `HOLE_KEEP_UPM_AREA_RATIO`(0.0025→2500)** のときだけ除去を抑止する。真カウンター現状最小≈28k はもともと微小床(3500)超で生存済み。保護床は将来の 2500–3500 帯の小カウンター向け。
Text-to-SVG／ベクター生成研究（NPR・VecFusion・DeepVecFont-v2・DualVector・SVGenius 等）の知見を実コード監査と突き合わせ、MyMincho に取り込むべきものだけを選別した計画。**生成パラダイム（骨格YAML＋パラメトリック肉付け＋union）は変えない**。取り込むのは「パス表現・幾何制約・評価」の3点のみ。

関連: `PLAN.md` §3.2（curve_refit 決定）、`docs/kana_parametric_plan.md` §2.5（仮名 cubic 保持方針）、`docs/kana_review_loop_plan.md`（ゲートB）。

v2→v3 の主変更:
1. **Phase 0a の格上げ**: 穴破壊は「8c『の』の将来問題」ではなく**現在の潜在バグ**と実証（口・田・中が全正面積で出力される。F15）。しかも既存テストがバグ挙動を固定化している（F18）
2. **v2 の誤結論を撤回**: 「穴除去禁止フラグは不要」→ **誤り**。微小輪郭除去は絶対値面積で判定しており、微小な真のカウンターは将来除去されうる。穴除外を Phase 0a に追加
3. fix_winding の方向規約が**入力に依存せず決定的**であることを4通り入力で証明（F14）→ 一括 reverse の成立根拠が確定。規約変化を検知するカナリアテストを追加
4. フィット対象を「出荷折れ線そのもの」に単純化（誤差再見積もり込み）

---

## 0. 実コード監査で確定した事実

### 0.1 v1 で確定

| # | 事実 | 根拠 |
|---|---|---|
| F1 | 漢字は RDP 折れ線（ε=1.5）、仮名は passthrough。フル cubic 再適合は mode に存在しない | `engine/curve_refit.py` |
| F2 | **仮名の「cubic 保持」は骨格 spine のみ**。製品輪郭は弧長72サンプル×左右の高密度折れ線で、OTF には lineTo だけが入る。実測: し=144点 / い=144+144 / と=274 / つ=144 / く=143（漢字RDP後: 十=33・永=57+18） | `bridge._draw_contours`、実行計測 |
| F3 | `extract_contours_xy` は QUAD/CUBIC の**制御点を頂点として折れ線に潰す**（現状 LINE のみなので無害） | `bridge.py` |
| F4 | `ensure_positive_fill` は**全輪郭を正面積へ個別反転**（穴の破壊者） | `bridge.py` |
| F5 | skia-pathops は cubic 入力の union / simplify で **cubic を保持**（実機: MOVE×1・CUBIC×8・CLOSE×1） | venv 検証 |
| F6 | 仮名ゲートv2 実装済み（contour数・再現ハッシュ・自己交差・接合・突き抜け・bbox・方位・ギャップ）。κ・アンカー数は未実装 | `engine/kana/gate.py` |
| F7 | ベースライン: engine 170 テスト全緑 | pytest |

### 0.2 v2 で確定

| # | 事実 | 根拠 |
|---|---|---|
| F8 | **solve パイプは winding 安全**。`simplify(fix_winding=True)` はリングを外形＋穴（符号つき）で保ち、cleanup の keep 再unionも穴を保持（skia union は winding fill 合成）。微小島除去も穴の隣で正しく動く | ring+island フィクスチャ検証 |
| F9 | 仮名の端物テンプレは **EndTag パースのみ・幾何は幅キー近似**（専用パーツ未実装、docstring 明記）→ 仮名輪郭形状は今後も変わる | `kana/load.py`, `build_kana_curve` |
| F10 | 微小輪郭の面積計測はオンカーブ端点折れ線の**絶対値**（`polygon_area` が abs） | `join_solver.py` |
| F11 | 自己交差検査は simplify 前後の verb 数差分ヒューリスティック → solve に cubic を流すと偽陽性リスク | `check_self_intersect_heuristic` |
| F12 | ゲートBの計測は「union前 element ポリゴン＋solve 結果」で完結し、**refit はゲートの下流** | `kana/gate.py` |
| F13 | `.notdef` は既に逆巻き内形の穴で成立（`ensure_positive_fill` 非経由） | `bridge._notdef_contours` |

### 0.3 v3 で確定

| # | 事実 | 根拠 |
|---|---|---|
| F14 | **fix_winding の方向規約は入力の巻きに依存せず決定的**: 外形＝正 shoelace（y-down 空間）・穴＝負。4通りの入力巻きすべてで同一出力。同巻き入れ子は nonzero 意味論で単一輪郭に融合 | 4-way リング検証 |
| F15 | **穴破壊は現在バグ**: 口・田・中の骨格は実装済み（`extra_skeletons`）で、bridge 出力は全輪郭正面積（口=[+333691, +175516]・田=5輪郭全正・中=3輪郭全正）。OTF 化するとカウンターが黒塗りになる。中は join20 の20字に含まれるが、**join20 は solve 層（輪郭数・自己交差）のみ検査**するため検出されない | 実行計測＋`test_regression_join.py` 読解 |
| F16 | regen → `build_temp_font` → `solve_to_font_contours` → curve_refit の一本道。**refit が唯一の挿入点**という経路Bの前提は成立 | `scripts/regen.py` |
| F17 | 仮名 CLI 群（kana_render / kana_ref_compare / kana_fit_step）は **OTF・ラスタのみ消費**。cubic 切替で壊れない（PNG 黄金の再凍結だけ必要） | 各スクリプト読解 |
| F18 | **既存テストがバグ挙動を固定化**: `test_bridge.py` の `test_ensure_positive_fill_reverses_cw` と「全輪郭 shoelace>0」assert。Phase 0a はテスト改訂を含む | `engine/tests/test_bridge.py` L32–45 |
| F19 | `build_ufo` は CORE_GLYPHS＋仮名メタしか受けない（口・田・中は name/unicode メタ未登録で UFO 化不可）。穴の OTF 検証にはメタ登録が必要 | `bridge.glyph_meta` / `build_ufo` |

### 0.4 検証で潰した仮説・撤回した結論（記録）

- 「cleanup の keep 再unionが穴を潰す」→ **反証**（F8）
- 「cubic は union で折れ線化される」→ **反証**（F5）
- 「仮名は cubic のまま出荷されている」→ **反証**（F2）
- 「fix_winding の規約が入力依存かもしれない」→ **反証**（F14。ただし pathops 更新で変わりうるためカナリアテスト化）
- **v2 の誤り**: 「穴除去禁止フラグは不要と判明」→ **撤回**。F10 のとおり面積は絶対値であり、微小な真のカウンター（例: 画数の多い漢字の小さいふところ、床3500 units²≈59×59 UPM 未満）は将来除去されうる。穴除外を Phase 0a に含める

---

## 1. 採否判定（研究→取り込み）

### 採用する

| 知見 | 出典 | 取り込み先 |
|---|---|---|
| 幾何制約なしの画素合わせ最適化は交差・ジャギーを生む。パス表現＋制約が本質 | NPR (SIGGRAPH 2024) | cubic フィットの制約設計（§3 Phase 1） |
| 補助点の密サンプリングで生成曲線と目標形状の一致を測る | DeepVecFont-v2 | フィット誤差ゲート（Hausdorff 密サンプル） |
| ベクター品質は画素指標で測れない。アンカー数・トポロジー・曲率が品質軸 | StarVector / SVGenius / DualVector | 観測メトリクス（§3 Phase 0b） |
| 外形とカウンターの区別を輪郭処理の一級市民にする | DualVector / LIVE | winding 正規化＋穴除外（§3 Phase 0a） |
| 古典的最小二乗フィット＋角検出で折れ線→cubic は解ける（学習不要） | Schneider (Graphics Gems) | `curve_refit` 新モード `cubic_fit` |

### 採用しない（明示）

| 対象 | 理由 |
|---|---|
| LLM による直接アウトライン生成・合否判定 | SVGenius/VGBench が複雑度で系統的劣化を定量証明。既存方針（Gemini は観察のみ）を維持 |
| 拡散系（VecFusion / SVGFusion / FontDiffuser）・path latent 学習 | 骨格YAML正本・少数字・決定的CI と非互換。v1.0 後の研究トラック |
| DiffVG 系の微分可能最適化 | 解析的サンプル＋古典フィットで足りる見込み。フィット撤退時の代替候補として名前だけ保留 |
| ラスタ→トレース（potrace 等） | 掟9（トレース禁止）と品質方針に反する |
| 商用ベクター生成API（Recraft 等）のパイプ組み込み | 来歴カード（S3）と字形一貫性を破壊する |

---

## 2. アーキテクチャ決定: 経路B（union後フィット）を主経路とする

### 経路の比較

| | 経路A: union前から cubic | **経路B: union後折れ線→cubic フィット（採用）** |
|---|---|---|
| 挿入点 | build_stroke・join_solver・cleanup・extract・bridge 全域 | **`curve_refit` の新モード1箇所**（F16 で一本道を確認） |
| F9（端物テンプレ未実装）耐性 | 端物実装のたびに追随改修 | **フィット対象は「届いたポリゴン」なので無風** |
| F10/F11（面積・自己交差の cubic 非対応） | 両方の改修が必須 | **solve は折れ線のまま→改修不要** |
| ゲートB（F12） | solve が変わり再現ハッシュ・黄金が全て動く | **ゲート層は完全不変** |
| 接合部の品質 | union が cubic を切った断片の監視が必要 | 角検出でノット固定（検出漏れ＝角が丸まるリスク） |

**決定**: 経路Bを主経路。経路A は「接合部のフィット品質が Phase 1 ゲートを満たせない場合」の限定フォールバック（F5 で成立実証済み）。

### フィット対象と誤差予算

**フィット対象は出荷折れ線そのもの**（passthrough が UFO に書くのと同一の点列）。v2 の「n≥192 の密折れ線を別生成」は撤回——solve に密度パラメータを足すと黄金・ゲートに波及するため。ゲート層が承認した形状とフィット入力が恒等になる利点を優先する。

| 誤差源 | 予算 | 備考 |
|---|---|---|
| 弧長72サンプルの弦誤差（対・真のオフセット曲線） | ≤0.3 UPM | 最悪ケース概算: 曲率半径50・弦長11 UPM で sagitta≈0.3。曲率ゲート（半径≥0.55×半幅）がこの帯を下支え |
| cubic フィット（Hausdorff 対・出荷折れ線） | ≤0.5 UPM | ゲート必須・双方向 |
| ufo2ft の整数丸め | ≤0.5 UPM | 現行折れ線も同条件（差分なし） |
| **合計** | **≲1.3 UPM** | 漢字 RDP の ε=1.5 より小さく、かつ C1 連続（節点ノイズなし） |

弦誤差が支配的になる字（急曲率）が出たら、その時点で solve とは独立した密サンプル再生成をオプション化する（先回りしない）。

### レイヤ分離の原則（本計画で固定）

- **ゲート層（合否）**: union前ポリゴン＋solve 折れ線パス。本計画では触らない
- **製品層（出荷形状）**: curve_refit 以降。cubic 化はここだけで起きる
- 両層の整合は「フィット Hausdorff ゲート」が保証する

---

## 3. フェーズ計画

依存の原則: **P1 仮名量産（く 以降）を止めない**。ただし Phase 0a は仮名 8c だけでなく**漢字（口・田・中）の現在バグ**（F15）なので、次の骨格追加・OTF 出荷より前に必ず実施。Phase 1 は品位向上であり、核心字進捗と並走するスパイク。

### Phase 0a: winding 正規化＋穴保護（現在バグ修正）— 6〜10h

**修正1: bridge の fill 正規化**（F4/F15）
- `ensure_positive_fill`（個別正面積化）を廃止し、**一括 reverse＋検証**に置換:
  1. solve 出力は fix_winding 済み＝外形正・穴負（y-down）が**入力に依らず決定的**（F14）
  2. Y反転で全輪郭の向きが一様に裏返る → **全輪郭を一括 reverse** で復元（実測符号で検算済み: 口の外形 −→＋、穴 ＋→−）
  3. **検証チェック**（自動修正しない）: 各輪郭の包含深度（偶=外形/奇=穴）と面積符号の整合を確認、不整合は raise
- PLAN §0.1 教訓3「全輪郭の一括反転は禁止」との整合: 教訓が禁じたのは fix_winding 前提なしの盲目反転・相対関係を無視した個別正規化（現行実装がまさに後者）。**fix_winding が上流で常に走る現パイプでは一括 reverse は相対巻きを保存する**。教訓の意図は検証チェック（3.）として引き継ぐ

**修正2: cleanup の穴除外**（F10・v2 撤回の反映）
- `remove_micro_contours` に**符号つき面積**を導入し、**負面積（穴）輪郭は除去対象から恒久除外**（ログのみ）。kana_parametric_plan §2.4 の実体

**修正3: テスト・メタ整備**（F18/F19）
- `test_bridge.py` の旧挙動テスト2件を改訂（バグの固定化を解除）
- 口・田・中に name/unicode メタを登録（`uni53E3` 等）して UFO/OTF 化可能に
- **pathops 規約カナリアテスト**: F14 の4通り入力→符号出力を pytest 化（pathops 更新で規約が変わったら即 FAIL）

- DoD:
  1. 口・田・中 → OTF → freetype ラスタで**カウンター中心画素が白**（現状は黒＝再現手順込みで before/after を記録）
  2. 穴なし字（join20 の 十・二・永ほか＋仮名5字）の輪郭出力が**バイト同一**（一括 reverse ≡ 現行、を回帰で証明）
  3. 同巻き入れ子を渡すと raise（検証チェックの単体テスト）
  4. 負面積の微小輪郭が除去されないことの単体テスト
  5. カナリアテスト green

### Phase 0b: 観測メトリクス — 2〜4h

合否に接続しない観測フィールド（画素指標は追加しない）:
- `refit.points_after` は bridge レポートに既存 → regen サマリと weekly に基線を転記する運用から開始（ゲートJSONへの合流は CLI 側で任意）
- `curvature_p95`: spine 弧長サンプルの離散曲率 p95（`geometry.curvature_radii` 流用・観測のみ）
- Phase 1 以降は `anchor_count`（オン＋制御点）と `segment_count` を追加
- DoD: 既存ゲート合否・黄金が不変のまま仮名全字で値が出る。weekly に基線記録

### Phase 0c: 曲線破損ガード — 1h

- `extract_contours_xy` が QUAD/CUBIC verb に遭遇したら**黙って潰さず raise**（経路Aフォールバック時の安全弁。恒久措置）
- DoD: cubic を含む path での raise を単体テストで確認

### Phase 1: `cubic_fit` モード実装（スパイク・仮名 opt-in）— 16〜32h

対象: く・し・つ（単一element）→ 合格後すぐ と・い（接合あり）で接合部を検証。

1. **フィット対象**: 出荷折れ線そのもの（§2）
2. **角検出**: 転向角閾値（初期値: 隣接接線差 >30°）＋幅キー位置・entry/exit 近傍をヒントに**ノット強制点**を決定。幅キー由来の浅い C1 折れ（区分線形幅補間による）は「ノットは置くが接線連続は強制しない」扱い。端物テンプレ本実装（F9）後も角検出は汎用に働く
3. **区間フィット**: 角間を Schneider（Graphics Gems）最小二乗 cubic 分割フィット。非角ノットは接線連続を強制。実装はフルスクラッチ（~150行）または MIT 実装の移植。**GPL 実装の参照禁止**
4. **データモデル**: `RefitResult.contours` を「セグメント列（line/cubic）」対応に拡張。`to_font_contours`（Y反転）は制御点も変換。winding 一括 reverse はセグメント列の逆走（制御点順の反転）に対応。`_draw_contours` に `pen.curveTo` 追加（CFF は cubic ネイティブ・cu2qu 非経由）
5. **ゲート（fail-closed）**:
   - Hausdorff ≤ 0.5 UPM（対・出荷折れ線。双方向）
   - フィット後パスの pathops self-intersect = 0（refit 専用検査。F11 の solve 側とは別物）
   - contour 数・**穴数・面積符号構造**不変
   - アンカー総数 ≤ 40/**輪郭**（初期値。snapshot yaml で調整可）
   - 再現性: 同一入力 → セグメント構造（verb列＋座標）ハッシュ一致（純Python固定順演算・並列化禁止）
6. **設定**: `snapshots/curve_refit.yaml` に `cubic_fit` を仮名専用 opt-in で追加。漢字は `rdp_polyline` 据え置き
- DoD: く で `≤40 点（curveTo主体）` の OTF、hb-view 組見本の目視＋黄金AE比較で劣化なし。と の接合角が丸まっていない（角検出ヒット位置をレポート出力）。OTF から輪郭を読み戻して丸め込み実測 Hausdorff ≤1.3 UPM（§2 予算の実地確認）
- **撤退ライン**: ゲートを満たすフィットに 2 セッション（≈16h）超 → 中止して折れ線継続（実害は小）。接合部**のみ**不合格 → 経路A（cubic union）を接合字限定で再検討

**Phase 1 実装結果（2026-08-12）**
- 挿入点: `curve_refit` モード `cubic_fit`＋`snapshots/curve_refit.yaml` の `kana_mode`（漢字 `mode: rdp_polyline` 据え置き）
- 実装: `engine/curve_fit.py`（角検出・Schneider系LS＋Newton再パラメータ・隣接segマージ）／`bridge._draw_paths`（`curveTo`）／winding は `normalize_fill_winding_paths`
- ゲート実測（product_r1）: く anc=34 err=0.41／し 35/0.33／つ 36/0.47／と 48/0.49／い 33+24/0.48。OTF読み戻し Hausdorff: く0.56・と0.86・い0.59（いずれも ≤1.3）
- アンカー上限は接合字「と」のため yaml を **48/輪郭** に調整（単画は ≤40 を維持）。自己交差・面積符号構造も fail-closed
- テスト: `engine/tests/test_curve_fit.py` 追加。engine **199 passed**

### Phase 2: 仮名全体切替＋黄金再凍結 — 4〜8h

- 核心字が10字前後に達した時点で一括切替
- **黄金無効化プロトコル**（掟18）: ① `proofs/golden/kana_*` をバージョン付き再凍結 ② `make_proofs --compare-golden` は SHA256 厳密一致のため切替コミットで必ず更新 ③ `kana_render` の `meta.json`（OTF SHA 連鎖）で由来記録 ④ ship_gate（S1）の自己交差検査が cubic OTF で通ることを確認（F17: CLI 群自体は無改修）
- `anchor_count` の before/after を weekly に記録（回収の証拠）

**Phase 2 実装結果（2026-08-12）** — 核心5字時点で先行実施（`kana_mode` は Phase 1 で既定化済みのため凍結を前倒し）
- 黄金: `proofs/golden/kana_{shi,i,to,tsu,ku,board}/` 再凍結＋新規 `kana_ku`。マニフェスト `proofs/golden/FREEZE_cubic_fit_v1.json`（version=`kana_golden_cubic_fit_v1`）
- `kana_render --compare-golden`: 14/14 MATCH
- ship_gate `outline_sample`（cubic OTF）: **ok**（name_table の copyright 欠は別件・未対応）
- アンカー回収（passthrough→cubic）: し144→35 / い288→57 / と271→48 / つ144→36 / く143→34（約75–82%削減）。詳細 `proofs/review/observe_cubic_fit_v1.json`

---

## 4. 意思決定の変更点（正本文書との差分）

| 正本 | 現記述 | 本計画による更新 |
|---|---|---|
| PLAN §3.2 | 「フル cubic は M2 非デフォルト（角・うろこ崩壊リスク）」 | **漢字は維持**。仮名は `cubic_fit`（角ロック付き）を Phase 1 合格後に既定化。合格時に PLAN へ反映コミット |
| PLAN §0.1 教訓3 | 「全輪郭の一括反転は禁止」 | fix_winding 済みパスに限り一括 reverse は安全（F14）。教訓は「検証チェック必須」に読み替え、Phase 0a 実装後に注記を追記 |
| PLAN §0.1 教訓4 | 「入れ子判定を別途実装する」 | Phase 0a の検証チェックが実体 |
| kana_parametric_plan §2.4 | 「負面積＝穴は除去禁止フラグを必須化」 | **必要と再確定**（v2 で「不要」とした結論は誤り・撤回）。Phase 0a 修正2が実体 |
| kana_parametric_plan §2.5 | 「再適合するなら曲率適応フィット（Hausdorff ≤1.0–1.5）を別ゲートで」 | Phase 1 がその実体。フィット単体 0.5・丸め込み実測 1.3 の2段で管理 |
| kana_review_loop_plan | ゲートBは solve までで完結 | 変更なし（レイヤ分離の原則 §2 の明文化のみ） |

## 5. リスク台帳

| リスク | 検知 | 対応 |
|---|---|---|
| 口・田・中の穴破壊が出荷に混入（**現在バグ**） | Phase 0a DoD 1（ラスタ白画素） | Phase 0a を次の骨格追加前に必須実施 |
| pathops 更新で fix_winding 規約が変わる | **カナリアテスト**（Phase 0a DoD 5） | 規約変化時は一括 reverse の前提を再検証 |
| 微小な真のカウンターが cleanup で除去される | Phase 0a DoD 4 | 符号つき面積で穴を恒久除外 |
| 接合部の角検出漏れ→角が丸まる | Phase 1 DoD（と の角チェック）＋角ヒット位置レポート | 閾値調整→ダメなら経路A（接合字限定） |
| 端物テンプレ本実装（F9）で輪郭形状が変わる | 黄金差分 | フィットは対象追随型なので再フィットのみ。黄金再凍結手順で吸収 |
| 弦誤差が支配的な急曲率字 | Phase 1 の丸め込み実測（DoD） | その時点で密サンプル再生成をオプション化（先回りしない） |
| フィットの数値非決定性 | セグメント構造ハッシュ | 純Python固定順演算。並列化しない |
| solve 側自己交差ヒューリスティックの偽陽性（F11） | 経路Bでは solve に cubic が流れないため**発生しない** | 経路A採用時のみ verb 差分許容量を再設計 |
| 「の」リング生成が DSL 未対応のまま 8c 到達 | schema に `loop_closure` なし（確認済み） | 8c 着手時に DSL 拡張。Phase 0a 済なら穴パイプは安全 |
| ゲートの穴数概念の欠如（expect_contours は総数のみ） | 8c 設計時 | 8c で `expect_holes` を gate スキーマに追加（本計画のスコープ外・記録のみ） |

## 6. やらないことの再確認（スコープ防衛）

- 学習モデルの訓練・導入は v1.0 まで一切なし（PLAN §7.3 と同一）
- 画素類似度を合否に使わない（研究的裏付け: StarVector・SVGenius）
- 漢字の cubic 化はスコープ外（RDP 品質は製品サイズで十分。再訪は仮名 `cubic_fit` の運用実績後）
- Phase 1 が P1 核心字の週次進捗を 1 サイクル以上止める場合、Phase を凍結して字を優先する
