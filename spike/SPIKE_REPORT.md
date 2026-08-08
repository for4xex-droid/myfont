# MyMincho 技術前提スパイク検証レポート

作業日: 2026-08-09  
作業場所: `/Users/motista/Desktop/antigravity/myfont/spike/`  
対象計画: `PLAN.md` v2

---

## 1. 作成ファイル一覧（`.venv` 除く）

| パス | 役割 |
|---|---|
| `spike/.venv/` | Python 3.14 venv |
| `spike/verify_a_union.py` | A: pathops union 検証 |
| `spike/verify_b_measure.py` | B: freetype 計測検証 |
| `spike/verify_c_buildchain.py` | C: fontmake/fontbakery/uharfbuzz |
| `spike/fonts/NotoSerifJP-Regular.otf` | google/fonts の可変 Noto Serif JP（実体は TTF） |
| `spike/fonts/NotoSerifJP-Regular-wght400.ttf` | fontTools instancer で wght=400 に固定 |
| `spike/output/*.svg` | union 前後比較 SVG |
| `spike/output/raster_*.png` | ラスタ／二値化 PNG |
| `spike/output/verify_{a,b,c}_report.json` | 機械可読結果 |
| `spike/SPIKE_REPORT.md` | 本報告書 |

---

## 2. 実行した主要コマンド

```bash
cd /Users/motista/Desktop/antigravity/myfont
mkdir -p spike/output spike/fonts
python3 -m venv spike/.venv
spike/.venv/bin/pip install --upgrade pip
spike/.venv/bin/pip install fonttools skia-pathops freetype-py pillow numpy uharfbuzz

# フォント取得（GitHub / google/fonts）
curl -L -o spike/fonts/NotoSerifJP-Regular.otf \
  "https://github.com/google/fonts/raw/main/ofl/notoserifjp/NotoSerifJP%5Bwght%5D.ttf"

# 検証
spike/.venv/bin/python spike/verify_a_union.py
spike/.venv/bin/python spike/verify_b_measure.py
spike/.venv/bin/python spike/verify_c_buildchain.py   # 内部で pip install fontmake / fontbakery
```

依存インストール結果:
- **成功**: fonttools, skia-pathops, freetype-py, pillow, numpy, uharfbuzz, fontmake, fontbakery
- **required 権限リトライなし**（初回 `all` で venv 作成。以降も同一環境）

---

## 3. 検証 A — skia-pathops で「永」の接合（P2/M2）

### 結果（classic / modern 同型）

| 指標 | classic | modern |
|---|---|---|
| 入力ポリゴン数（= contour 数） | 13 | 13 |
| union 生出力 contour | 8 | 8 |
| simplify 後 contour | **4** | **4** |
| 「十」 before → after | 6 → **2** | 6 → **2** |
| union 例外 | なし | なし |
| 微小セグメント (len&lt;0.5) | 4 / 701 | 4 / 701 |

残り contour の内訳（classic 分析）:
1. **本体**（横×縦×はらい等が融合した主輪郭）≈ 720×636
2. **点（側）** — 横画に幾何的に重なっておらず別輪郭のまま ≈ 97×88
3. **微小島** ≈ 30×30（端物由来）
4. **微小島** ≈ 12×45（打ち込み左端の点接触/食い込み不足。十でも同種の島が残る）

自己交差: pathops に明示 API は無し。`simplify` 差分ヒューリスティックでは、一部本体ポリゴン（index 1, 7）で verb 数減少＝オフセット由来の自己交差疑い。union 後も simplify で 8→4 に整理。

### 判定

**条件付き成立**（PLAN **§3.3** / P2 Stage B）

- 「重ね塗りポリゴンを `pathops.union` に載せられる」「交差して重なる部分は単一輪郭に融合する」は **成立**
- 「永がそのまま単一輪郭になる」は **不成立**（非接触ストローク＋端物の微小島）
- PLAN の Stage A（`join_overlap` で食い込ませる）と Stage B 後処理（微小線分/微小輪郭除去）は **必須前提**であり、union 単体では P2 DoD（単一輪郭＋自己交差ゼロ）に届かない

---

## 4. 検証 B — freetype-py 計測（T3/T5α）

### フォント

- 入手成功: `google/fonts` の `NotoSerifJP[wght].ttf`（可変、default **wght=200 ExtraLight**）
- 計測には `fontTools.varLib.instancer` で **wght=400** に固定した `NotoSerifJP-Regular-wght400.ttf` を使用
- ヒラギノフォールバックは不要だった

### 「十」コントラスト（1024px/EM, NO_HINTING, gray, T=128）

| 指標 | 値 |
|---|---|
| 縦画太さ | 70 px（0.068 EM） |
| 横画太さ | 29 px（0.028 EM） |
| コントラスト（縦/横） | **≈ 2.41** |

走査は交点そのものではなく、**交点の上下で水平走査（縦画）／左右で垂直走査（横画）**。交点直上の垂直走査は縦画の長さを拾い失敗する（初期実装で horiz≈919 になった）。

### 「三」「二」うろこ簡易検出

- 上横画 ROI で右端の上面突出を検出: 三 ≈ 69 px、二 ≈ 72 px（相対 ≈ 2.4×本体太さ）
- 動作はするが、様式差・検出不能と様式的ゼロの区別は未実装（PLAN §2.4 の注意と一致）

### ハマりどころ

1. **可変フォントの default インスタンス**が ExtraLight。ファイル名に Regular とあっても `freetype.Face` は 200 になる → `set_var_design_coords` または instancer 必須
2. **name テーブル**は instancer 後も `ExtraLight` のまま残ることがある（座標は 400）
3. **`set_pixel_sizes(EM, EM)`** が安全。`set_char_size` の pt/dpi 換算は誤りやすい
4. **`bitmap.pitch`** で行送り（≥ width）。buffer を width×rows と決め打ちしない
5. **配置**: `y0 = baseline - bitmap_top`（FT は baseline 基準・画像は Y 下）
6. **TTC** は `Face(path, index=N)`（今回未使用だがヒラギノ時に必要）
7. **十の走査位置**: 交点回避がプロトコルに必須

### 判定

**成立**（PLAN **§2.3** `ft_1024_nohint_gray_v1` / **§2.4** Phase α）

計測プロトコルは実装可能。コーパス取得時は「静的 OTF」か「可変→明示インスタンス」を T1 の完了条件に含めるべき。

---

## 5. 検証 C — ビルドチェーン

| 項目 | 結果 | 判定 |
|---|---|---|
| `pip install fontmake` | 成功 | **成立** |
| `fontmake --help` | rc=0（251 行） | **成立** |
| `pip install fontbakery` | 成功（download フォールバック不要） | **成立** |
| uharfbuzz で「あ」shape | gid=1208, advance=1000 (upem) | **成立** |

uharfbuzz 初回失敗要因: `Font.size = 1000` は **0.56 に属性が無い**。除去後は問題なし。組見本ツール（PLAN §3.2）の実現性は確認できた。

**総合: 成立**

---

## 6. PLAN.md を修正すべき点

1. **§3.3**: union の前提として「端物・非接触画は Stage A で十分な重なり（`join_overlap`）を保証すること」「Stage B 後に微小 contour 除去（面積/bbox 閾値）を DoD に含めること」を明記。現状の「食い込ませてから union」だけでは、プロトタイプの打ち込み形状だと島が残る実測がある。
2. **§2.3 / T1**: 可変フォント（Noto Serif JP 等）は default ≠ Regular。取得スクリプトの DoD に「計測用インスタンス（例 wght=400）固定＋SHA256」を追加。
3. **§2.4 `juu_contrast`**: 走査線は交点を避ける（上下/左右オフセット）とプロトコル文書へ。交点走査は失敗モードとして明記。
4. **§3.2 組見本**: uharfbuzz 利用時は `Font.size` に依存しない（バージョン差）。`hb.shape`＋ Pillow 描画で足りる旨を短く書いてよい。
5. **§2.7**: skia-pathops の API は `union(contours, outpen)`（FillType 引数なし）。実装メモとして有用。
6. （任意）prototype の「永」点ストロークを勒にわずかに重ねるよう骨格を直すと、スパイクの「単一輪郭」デモが分かりやすくなる（本実装の Stage A とは別問題）。

---

## 7. 生成アセット（フルパス）

### SVG（union 比較）

- `/Users/motista/Desktop/antigravity/myfont/spike/output/ei_before_union_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/ei_after_union_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/ei_union_compare_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/ei_before_union_modern.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/ei_after_union_modern.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/ei_union_compare_modern.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/juu_after_union_classic.svg`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/juu_after_union_modern.svg`

### PNG（ラスタ計測）

- `/Users/motista/Desktop/antigravity/myfont/spike/output/raster_juu_1024.png`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/raster_juu_1024_bin.png`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/raster_san_1024.png`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/raster_san_1024_bin.png`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/raster_ni_1024.png`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/raster_ni_1024_bin.png`

### JSON

- `/Users/motista/Desktop/antigravity/myfont/spike/output/verify_a_report.json`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/verify_b_report.json`
- `/Users/motista/Desktop/antigravity/myfont/spike/output/verify_c_report.json`

---

## 8. 総括

| 検証 | PLAN 節 | 判定 |
|---|---|---|
| A pathops union | §3.3 / P2 | **条件付き**（融合は可、単一輪郭化は Stage A+クリーンアップ必須） |
| B freetype 計測 | §2.3 / §2.4 | **成立** |
| C ビルドチェーン | §3.2 / P3 | **成立** |

最大のリスクは REPORT.md / PLAN が既に指摘する通り P2 だが、**skia-pathops 自体は使える**。足りないのは幾何前処理（食い込み保証）と後処理（微小島除去）であり、ライブラリ選定の見直しは不要。
