# Spike2 検証報告: GlyphWiki KAGE → 内部骨格（P4a 前提）

日付: 2026-08-09  
対象: PLAN.md v3 §3.2 / §3.4 / §5、GOLDENRULES.md（KAGE関連）

---

## 成果物一覧

| パス | 内容 |
|---|---|
| `spike2/kage_parser.py` | dump行＋KAGE筆画＋部品展開パーサ |
| `spike2/verify_a_joyo.py` | 常用/教育漢字カウント |
| `spike2/verify_b_kage.py` | ダンプ取得後のパース・統計・SVG |
| `spike2/verify_c_mapping.py` | 内部形式写像表・工数判定 |
| `spike2/make_compare_svg.py` | 永の KAGE vs prototype 比較 |
| `spike2/output/glyphset_joyo2136.txt` | 常用2,136字リスト試作 |
| `spike2/output/glyphset_kyoiku1026.txt` | 教育1,026字 |
| `spike2/output/verify_{a,b,c}_report.json` | 機械可読レポート |
| `spike2/output/kage_mapping_table.md` | type×tag 写像表 |
| `spike2/output/kage_skeleton_u6c38_永.svg` | 永の折れ線骨格 |
| `spike2/output/kage_skeleton_u56fd_国.svg` | 国の折れ線骨格 |
| `spike2/output/compare_ei_kage_vs_prototype.svg` | 永の並置比較 |
| `spike2/data/dump.tar.gz` | GlyphWiki公式ダンプ（gitignore） |

### 主要コマンド

```bash
cd spike2
# venv は spike/.venv を流用
../spike/.venv/bin/pip install kanji-lists
curl -L -o data/dump.tar.gz https://glyphwiki.org/dump.tar.gz
tar -xzf data/dump.tar.gz -C data

../spike/.venv/bin/python verify_a_joyo.py
../spike/.venv/bin/python verify_b_kage.py
../spike/.venv/bin/python verify_c_mapping.py
../spike/.venv/bin/python make_compare_svg.py
```

---

## A. 常用漢字リスト（§3.2）

**判定: 前提成立**

| 項目 | 期待 | 実測 |
|---|---|---|
| `kanji-lists.JOYO` | 2,136 | **2,136** |
| `kanji-lists.KYOIKU` | 1,026 | **1,026** |
| KYOIKU ⊆ JOYO | — | True |

Unihan 代替は不要。`spike2/output/glyphset_joyo2136.txt` を試作済み（本番は `data/glyphset_joyo2136.txt` へ凍結コミットする想定）。

引用（PLAN §3.2）:
> リスト自体は自作せず Unihan の `kJoyoKanji` フィールド（または PyPI `kanji-lists`）から生成して凍結コミット

---

## B. GlyphWiki KAGE（§3.4 / §5）

### 取得

- URL: `https://glyphwiki.org/dump.tar.gz`
- サイズ: **111 MB**（展開後 `dump_newest_only.txt` ≈ **330 MB**）
- 取得成功のため API フォールバックは未使用
- インデックス: **2,443,897** エントリ / 読込 ≈ 2.2s

### 常用漢字カバー

| 指標 | 値 |
|---|---|
| カバー率 | **2136/2136 = 100%** |
| 表面が alias（ほぼ `uXXXX`→`uXXXX-j`） | **2026**（94.9%） |
| 表面に type99 あり | **2135**（99.95%） |
| **エイリアス解決後も type99 あり（真の部品合成）** | **1854（86.8%）** |
| エイリアス解決後が素筆画のみ | 282（13.2%） |
| 再帰展開失敗/空 | **0** |
| 再帰深度 max / mean / p95 | **5 / 2.21 / 3** |

### サンプル30字

- 部品解決が必要な字: **30/30 = 100%**（すべて alias または部品参照）
- サンプル深度 max: 3（国=3、議/論/鬱=3）

### 「数十行」主張

引用（PLAN §3.4 / §5）:
> GlyphWiki ダンプのパース（`name|related|data` の `|` 区切り）は数十行で書ける  
> KAGEダンプパース | 自作（数十行）

| 範囲 | 実測 LOC（関数本体） | 判定 |
|---|---|---|
| dump行分解のみ (`parse_dump_line`+`iter_dump`+`load_dump_index`) | **24行** | **前提成立** |
| 筆画パース＋alias | 77行 | 数十〜百行 |
| 部品展開＋座標写像 | 95行 | 別コスト |
| パーサファイル全体（コード行） | 279行 | 「数十行」の対象外 |

**判定: dump行パース＝前提成立。ただし「常用2,136字の骨格が得られる」は部品再帰展開が必須のため条件付き成立。**

### 可視化（写像可能性の目視）

- `/Users/motista/Desktop/antigravity/myfont/spike2/output/kage_skeleton_u6c38_永.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike2/output/kage_skeleton_u56fd_国.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike2/output/compare_ei_kage_vs_prototype.svg`

永は展開後7画（点・横・縦はね・挑・左はらい・啄・右はらい）で prototype `char_ei()` と構造対応可能。座標空間は KAGE 200×200（Y↓）↔ prototype UPM1000（製品はY↑）の変換が必須。

---

## C. KAGE→内部形式写像（P4a 核）

**判定: 条件付き（写像は自作正当・工数は「変換器＋100字」で妥当だが「パースだけ」では足りない）**

### 出現した type×tag（サンプル展開後）

ユニーク組み合わせ **30種**。出現ストロークの約 **291/298 がヒューリスティック写像可能**、**7件が要分割/近似**。

対応不能・要処理ケース:
1. **type 3（折れ）** → 内部に bend なし。2直線へ分割
2. **type 6（複曲線）** → 4制御点。polyline または cubic 昇格
3. **type 7（縦払い）** → `left_hara` 近似（専用 kind なし）
4. **type 0（特殊）** → 未対応
5. **曲線 type2 は3点（2次）** → prototype は3次ベジェ想定。次数合わせが必要
6. **端点タグの意味が文脈依存**（同じ数値でも始点/終点/接続で役割が違う）→ 写像表を `docs/kage_mapping.md` に固定する必要あり

### P4a 工数

| 項目 | 見積もり |
|---|---|
| 変換器 MVP（展開＋写像表＋SVG差分） | 16–40h |
| 100字品質レポート | 20–40h |
| **P4a 合計** | **40–80h** |

PLAN の「変換器＋100字品質レポート」という束ね方は**妥当**。ただし前提文が「パース数十行」に偏っており、**部品展開・写像表・座標変換**を P4a 本体と明記すべき。

---

## 総合判定（PLAN 該当節）

| 主張 | 節 | 判定 |
|---|---|---|
| JOYO=2136 / KYOIKU=1026、`kanji-lists` で生成可 | §3.2 / §5 | **成立** |
| dump の `\|` 区切りパースは数十行 | §3.4 / §5 | **成立**（24行） |
| 常用2,136字分の骨格が得られる | 背景前提 / §3.4層A | **条件付き成立**（100%カバーだが 86.8% が部品再帰必須、alias解決が前提） |
| KAGE→StrokeKind/EndTag 写像は自作 | §3.4 / §5 | **成立**（既存なし・正当） |
| P4a = 変換器＋100字品質レポート | §3.1 | **条件付き妥当**（工数40–80h。パースだけの見積もりは楽観） |

---

## PLAN.md / GOLDENRULES.md 修正すべき点

### PLAN.md

1. **§3.4 / §5「数十行」のスコープを限定明記**  
   「`name|related|data` の行分解は数十行。部品参照(99)の再帰展開・矩形写像・alias（`uXXXX`→`uXXXX-j`）解決は別途必要（本スパイクで展開コード≈95行＋筆画パース≈77行）」
2. **§3.4 に実測値を追記**  
   - 公式 dump ≈111MB / newest≈330MB、取得可能  
   - 常用カバー100%、表面alias≈95%、**alias後も部品参照≈87%**、再帰深度 max≈5
3. **§0 / §3.4 に座標系変換を明記**  
   KAGEは200×200・Y↓。内部正規座標は UPM=1000・Y↑（掟1）。変換はインジェスト時に一括
4. **P4a DoD に「部品展開器」を明示**  
   現状「写像仕様書＋100字」だけだと、99参照解決がスコープ外に読める
5. **§5 流用マップの行を分割**  
   - KAGEダンプ行パース: 自作（数十行）  
   - KAGE部品展開器: 自作（必須、中規模）  
   - KAGE→内部写像: 自作（P4a核）
6. **バリアント方針**  
   日本語向けは原則 `uXXXX-j`（なければ `uXXXX`）を正とする、を文書化

### GOLDENRULES.md

1. **掟17の具体化**: ソース名は解決後の実体名（例 `u6c38-j`）と dump リビジョン（ファイル日付 or SHA256）を残す
2. **新規掟案**: KAGE座標を内部JSONに入れる前に必ず UPM1000・Y上へ変換する（掟1のKAGE版）。生の200空間を `engine/skeletons/` に保存禁止
3. **新規掟案**: 部品参照を未展開のまま製品骨格として扱わない（99を StrokeKind に落とさない）
4. **掟12b補足**: dump データ自体は GlyphWiki LICENSE（自由利用・無保証）。エンジン実装の GPL 移植は引き続き禁止、という区別を一文追加

---

## 結論（親エージェント向け一行）

P4a の「自作変換器」方針は正当で、dump取得・行パース・常用100%カバーは実証済み。ただし**製品骨格取得の本体コストは部品再帰（常用の約87%）と写像表**にあり、「数十行で骨格が揃う」は行パース限定の話として PLAN を修正すべき。
