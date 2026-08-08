# Spike6 レポート — Stage A `join_overlap` + 微小輪郭除去

作業日: 2026-08-09  
作業場所: `/Users/motista/Desktop/antigravity/myfont/spike6/`  
venv: `/Users/motista/Desktop/antigravity/myfont/spike/.venv`（流用）  
対象計画: `PLAN.md` v5 **§3.3**

---

## 1. 成果物一覧

| パス | 役割 |
|---|---|
| `spike6/join_solver.py` | Stage A（T字検出＋延長）+ Stage B（union＋微小輪郭除去） |
| `spike6/extra_skeletons.py` | 木・本・日・田・口の prototype 形式骨格 |
| `spike6/run_spike6.py` | A/B/C 検証ランナー（SVG・JSON 出力） |
| `spike6/regression_join.yaml` | 回帰期待値雛形（8字） |
| `spike6/test_regression_join.py` | yaml 駆動 pytest |
| `spike6/output/*.svg` | before/after・k 感度 SVG（59 ファイル） |
| `spike6/output/spike6_results.json` | 機械可読結果 |
| `spike6/SPIKE6_REPORT.md` | 本報告書 |

実行:

```bash
cd /Users/motista/Desktop/antigravity/myfont
spike/.venv/bin/python spike6/run_spike6.py
spike/.venv/bin/python -m pytest spike6/test_regression_join.py -v
# → 15 passed, 2 xfailed（本・田 = known_gap）
```

---

## 2. 検証 A — 微小輪郭除去

### 実装要点

- union＋`simplify` 後、contour を面積で分類
- 閾値 = `max(area_ratio × ink面積, upm_area_ratio × UPM²)`
  - 既定: `area_ratio=0.005`（PLAN 例の 0.5%）、`upm_area_ratio=0.0008`（=800）
- **proximate モード**: 閾値未満かつ、より大きい輪郭と bbox 距離 ≤ `proximity`(8) のものだけ除去  
  → 意図的な孤立点画を消さない

### 結果（Stage A なし）

| 字 | params | before | union のみ | area 除去 | **proximate** | 期待 |
|---|---|---:|---:|---:|---:|---:|
| 十 | classic | 6 | 2 | **1** | **1** | 1 |
| 十 | modern | 6 | 2 | **1** | **1** | 1 |
| 二 | classic | 6 | 4 | **2** | **2** | 2 |
| 二 | modern | 6 | 3 | **2** | **2** | 2 |
| 永 | classic | 13 | 4 | **2** | **2** | 2 |
| 永 | modern | 13 | 4 | **2** | **2** | 2 |

知見:

1. **ink 比 0.5% だけでは不足**。classic「二」の打ち込み島 ≈420 は ink0.5%≈300 を超え残る → **UPM² 床（≈800）が必要**。
2. proximate でも area でも、コア3字は期待値に到達（点画は面積≈4975で閾値上、かつ孤立扱いで残る）。
3. 十・永の残島は SPIKE_REPORT 通り打ち込み由来（面積数百）。微小除去が主治療。

### 判定（A）

**成立**（PLAN **§3.3** Stage B「微小輪郭除去」）  
ただし閾値は「ink 比のみ」ではなく **UPM² 床との max** を推奨。除去対象は proximate 限定が安全。

---

## 3. 検証 B — Stage A `join_overlap`

### 実装要点

1. 各ストローク端点 → 他ストローク中心線の最短距離
2. `detect_radius = max(join_overlap, 0.5×min(横太,縦太))`
3. 投影 t ∈ (0.08, 0.92) → **T字**、端点付近 → **corner**
4. **TEN はソースにしない**（点画を融合対象にしない）
5. ヒット端点を中心線方向へ `join_overlap = k×min(横太,縦太)` 延長 → 肉付け → union → proximate 除去

### k 感度（永）

| k | classic overlap | hits | union 後 | **A+B 後** | modern A+B |
|---:|---:|---:|---:|---:|---:|
| 0.10 | 4.50 | 4 | 5 | **3** | **2** |
| **0.15** | **6.75** | **4** | **4** | **2** | **2** |
| 0.30 | 13.50 | 4 | 5 | **3** | **2** |

classic「永」で k=0.10/0.30 が悪化する理由: **策（短い挑）のうろこが本体から分離**した中サイズ島（面積≈2413）が現れ、微小閾値（800）を超えて残る。k=0.15 では融合が安定。

### 十・二（k=0.15）

| 字 | hits | union | A+B | 期待 |
|---|---:|---:|---:|---:|
| 十 | 0 | 2 | **1** | 1 |
| 二 | 0 | 4 | **2** | 2 |
| 永 | 4 | 4 | **2** | 2 |

十は十字交差で端点が相手中心線近傍に無い → Stage A ヒット0。期待到達は **微小除去頼み**。

### 点画ギャップ（永）

点端点→他画中心線の最小距離 ≈ **49.2**（啄ルート近傍）。  
detect_radius（classic, k=0.15）≈ 22.5 のため **点は検出されず非融合** — PLAN の「非接触で正しい画は融合しない」と一致。期待 contour=2 が正しい。

### 判定（B）

**条件付き成立**（PLAN **§3.3** Stage A＋B）

| 主張 | 判定 |
|---|---|
| 食い込み＋微小除去で「永」が期待 contour（2）に到達 | **成立**（k=0.15） |
| Stage A が常に必要／単調改善 | **不成立**（コア3字は微小除去だけで到達。悪い k は悪化） |
| T字自動検出が動く | **成立**（永で4ヒット: 縦→横、策→縦、掠→横、磔→縦） |
| 残る主因が「点の骨格非接触が大きすぎる」 | **不成立**（点は意図的非接触で期待2。問題は端物島と k 感度） |

到達しない場合の残因（拡張字）:

- **本**: 現状3（下部横のうろこ／はらい接合不足）
- **田**: 現状6（期待5=外+穴4。右うろこ島≈2413が残存）
- 角接続・端物（うろこ）と本体の安定融合は、単純な端点延長だけでは足りない

---

## 4. 検証 C — 回帰テスト雛形

- `regression_join.yaml`: 十・二・永・木・本・日・田・口
- pytest: 期待 contour + 自己交差ヒューリスティック
- 結果: **15 passed, 2 xfailed**（本・田は `known_gap: true`）

囲み字の期待値は pathops がホールを contour として数える前提（口=2, 日=3, 田=5）。

---

## 5. before / after SVG（フルパス）

### A: 微小除去 compare（overlay → proximate）

- `/Users/motista/Desktop/antigravity/myfont/spike6/output/A_juu_十_classic_compare.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/A_ni_二_classic_compare.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/A_ei_永_classic_compare.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/A_juu_十_modern_compare.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/A_ni_二_modern_compare.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/A_ei_永_modern_compare.svg`

### B: Stage A+B（永 k 感度, classic）

- before/after: `/Users/motista/Desktop/antigravity/myfont/spike6/output/B_ei_永_classic_k0.15_compare.svg`
- k=0.10 full: `/Users/motista/Desktop/antigravity/myfont/spike6/output/B_ei_永_classic_k0.10_full.svg`
- k=0.15 full: `/Users/motista/Desktop/antigravity/myfont/spike6/output/B_ei_永_classic_k0.15_full.svg`
- k=0.30 full: `/Users/motista/Desktop/antigravity/myfont/spike6/output/B_ei_永_classic_k0.30_full.svg`

### B: 十・二（k=0.15）

- `/Users/motista/Desktop/antigravity/myfont/spike6/output/B_juu_十_classic_k0.15_compare.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/B_ni_二_classic_k0.15_compare.svg`

### C: 追加字プレビュー

- `/Users/motista/Desktop/antigravity/myfont/spike6/output/C_preview_ki_木_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/C_preview_hon_本_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/C_preview_nichi_日_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/C_preview_ta_田_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike6/output/C_preview_kuchi_口_classic.svg`

---

## 6. 総括判定（PLAN 引用）

| 項目 | PLAN 節 | 判定 |
|---|---|---|
| union 単体で単一輪郭化 | §3.3（スパイク既知） | **不成立**（再確認: 十 6→2、永 13→4） |
| Stage B 微小輪郭除去で期待 contour | §3.3 | **成立**（十=1, 二=2, 永=2。閾値に UPM² 床必須） |
| Stage A 食い込みで期待 contour | §3.3 | **条件付き成立**（k=0.15 で永=2。コア3字は除去だけでも可。悪 k は悪化） |
| P2 DoD「期待 contour＋自己交差ゼロ」雛形 | §3.3 / P2 | **成立**（pytest 雛形稼働。20字への拡張はこれから） |
| 回帰20字グリーン（M2完了） | M2 | **未達**（本・田が known_gap。ベジェ再適合未着手） |

### M2 見積もり（120〜250h）は妥当か

**妥当（下限寄りは楽観の余地あり）**。

根拠:

- T字検出＋延長自体は半日〜数日で動く（本スパイクで実証）
- しかし本番コストは (1) k／接続タイプ別チューニング (2) 角・うろこ・囲み穴 (3) union 後ベジェ再適合 (4) 回帰20字の骨格整備 — に移る
- 本・田クラスが常用に大量にあるため、Stage A を「端点延長だけ」で閉じるのは危険。旧80〜150h棄却は正しい

---

## 7. PLAN §3.3 に追記すべき知見

1. **推奨 k = 0.15**（`join_overlap = 0.15 × min(横太,縦太)`）。0.10/0.30 は策など短画でうろこ島を作りうる。
2. **T字検出半径** = `max(join_overlap, 0.5×min(横太,縦太))`。TEN は延長ソースから除外。
3. **微小除去**: ink 比 0.5% に加え **UPM² 床（例 0.08%→800）**。除去は「大輪郭に近接する微小片」に限定（proximate）。
4. **十字交差（十）は Stage A ヒット0**が正常。期待1への到達は微小除去が本体。
5. **永の期待 contour は点非接触なら2**。骨格ギャップ≈49 ≫ detect → 融合しないのは仕様。
6. **囲み字はホールを contour に含めて期待値を定義**（口2 / 日3 / 田5）。
7. Stage A は「あれば必ず良くなる」前処理ではなく、**k と接続分類が揃って初めて安定**する。回帰で k を固定し感度テストを残すこと。

---

## 8. PLAN 修正点リスト（提案）

1. §3.3: 微小除去の閾値を「ink 比 **または** UPM² 比の大きい方」＋ proximate 条件と明記。
2. §3.3: 推奨 `k=0.15` と「短画では過大/過小 k が端物島を生む」注意を追記。
3. §3.3: 十字は Stage A 非適用が普通、と注記。
4. §3.3 / P2 DoD: 囲み字の期待 contour にホールを含めるカウント規約を書く。
5. M2 リスク表: 「端点延長だけでは本・田級が残る → 角接続・端物融合の別ルールが必要」を追加。
6. （任意）回帰 yaml を `tests/regression_join20.yaml` へ昇格するとき、本スパイクの `known_gap` 字を初期バックログにする。
