# MyMincho 端到端スパイク検証レポート（spike3）

作業日: 2026-08-09  
作業場所: `/Users/motista/Desktop/antigravity/myfont/spike3/`  
対象計画: `PLAN.md` v3  
venv: `spike/.venv` を流用

---

## 1. 成果物一覧

| パス | 役割 |
|---|---|
| `spike3/verify_e2e.py` | A/B/C 一括検証スクリプト |
| `spike3/MyMinchoSpike.ufo/` | 最小 UFO（十/二/永 + .notdef） |
| `spike3/output/MyMinchoSpike-Regular.otf` | fontmake 出力 |
| `spike3/output/verify_e2e_report.json` | 機械可読結果 |
| `spike3/output/verify_e2e_run.log` | 実行ログ |
| `spike3/SPIKE3_REPORT.md` | 本報告書 |

---

## 2. 主要コマンド

```bash
cd /Users/motista/Desktop/antigravity/myfont
# venv は spike/.venv を流用（ufoLib2 / fontmake 済み）
spike/.venv/bin/python spike3/verify_e2e.py

# 内部で実行される相当処理:
#   pathops union（prototype 十/二/永）
#   Y反転 → ufoLib2 UFO 構築
#   fontmake -u spike3/MyMinchoSpike.ufo -o otf --output-path spike3/output/MyMinchoSpike-Regular.otf
#   freetype / poly_pillow 計測比較
#   uharfbuzz+freetype 組見本 / hb-view / pip install diffenator2
```

---

## 3. 検証結果と判定

### A. union → UFO → OTF（P3 経路）

| 字 | before→after contours | unicode | ビルド |
|---|---|---|---|
| 十 | 6→2 | U+5341 | OK |
| 二 | 6→4 | U+4E8C | OK |
| 永 | 13→4 | U+6C38 | OK |

- fontmake: **成功**（OTF 生成）
- 塗り反転: ink_ratio(十)≈0.207、inverted_suspect=false → **塗り正常**
- Y 反転: 組見本「十二永」が正立 → **§0.1 変換は有効**
- 永の微小島・非接触点は spike と同じく残存（単一輪郭化は未達）

**判定: 条件付き成立**（PLAN **§3.1 P3** / **§0.1**）

- 成立: 「接合済み輪郭→UFO→fontmake」の最小パイプ
- 不成立部分: P3 DoD 全体（手設計同居・FontBakery universal・自己交差別建て・cmap 差分 CI）は未実施
- §3.3 と同趣旨: Stage A＋微小輪郭除去なしでは製品品質に届かない

### B. 物差し1本化（§2.3 理想経路）

同一「十」（classic）を二経路で計測（1024px/EM, T=128, 交点回避走査）。

| 指標 | freetype（OTF） | poly_pillow（ポリゴン直描画） | 差 (ft − poly) |
|---|---:|---:|---:|
| 縦画太さ (px) | 102.0 | 104.0 | **−2.0** |
| 横画太さ (px) | 46.0 | 47.0 | **−1.0** |
| コントラスト比 (縦/横) | 2.2174 | 2.2128 | **+0.0046** |
| コントラスト相対差 | — | — | **≈0.21%** |

判定閾値（本スパイク定義）:
- 成立: Δ太さ≤2px かつ コントラスト相対差≤5%
- 条件付き: Δ太さ≤5px かつ ≤15%
- 不成立: それ以上 → profile 分離必須

**判定: 成立**（PLAN **§2.3**「将来の理想経路: エンジン出力→一時 UFO/TTF 化→freetype profile」）

一時フォント化で物差しを1本化する方針は、少なくとも十のコントラスト計測において妥当。  
ただし比較グラフでの profile 混在平均禁止（§2.3）は、接合前 synthetic や穴系 probe では引き続き維持すべき。

### C. 組見本スモーク（P1 / §3.2）

| 手段 | 結果 |
|---|---|
| uharfbuzz + freetype「十二永」 | **成功** → PNG |
| hb-view | **成功**（`-o`/`-O`。`--output` は Homebrew 版で無効） |
| diffenator2 | **install 成功 / 実行失敗** — `ModuleNotFoundError: pkg_resources`（Python 3.14 で setuptools 未同梱）。深追いせず |

**判定: 成立**（組見本経路。diffenator2 は **条件付き不成立**）

---

## 4. 座標系・輪郭方向でハマった点（§0.1 追記候補）

1. **Y 反転必須**: `y_font = UPM - y_svg`。忘れると字形が上下逆。
2. **Y 反転＝巻き方向逆転**: shoelace 符号が反転する。CFF/OTF は塗り輪郭 CCW（正面積）が必要。
3. **一括反転は危険**: 最大輪郭に合わせて全 contour を反転すると、打ち込み由来の微小島が**穴**になり塗り欠けする。
4. **bbox 内包による穴判定も誤爆**: 微小島の bbox が本体に入るため穴扱いになる。十/二/永のような意図的カウンター無し字形では「全輪郭を正面積（塗り）」が安全。
5. **真の穴（口・国）**は点-in-polygon の入れ子判定が別途必要（製品パイプライン課題）。
6. **検証手段**: ビルド後に freetype ラスタの ink_ratio で塗り反転を検出可能（十で ≈0.05–0.35 が妥当帯、>0.55 は反転疑い）。

---

## 5. PLAN.md を修正すべき点

1. **§0.1**: 上記 1–6 を追記（Y反転後の巻き方向手順・一括反転禁止・島≠穴）。
2. **§2.3**: 理想経路は本スパイクで端到端実証済みと明記。十コントラストで ft↔poly 差は縦2px/横1px/比0.21%。接合後の太さ・コントラスト系は一時フォント化＋`ft_*` へ寄せてよい。穴・黒み系は接合前 poly との混在禁止を維持。
3. **§3.1 P3**: 最小パイプ（union→UFO→fontmake）は成立。DoD 残り（FB/自己交差/cmap/手設計同居）は別チェックとして残す。
4. **§3.2**: hb-view は macOS Homebrew で `-o`/`-O`。diffenator2 は Py3.14 で `pkg_resources` 欠落により現状失敗 — 依存（setuptools）または代替を注記。
5. **§3.3**: 端到端でも永 13→4・微小島残存。Stage A＋微小輪郭除去は製品ビルド前の必須工程（変更なし・再確認）。
6. **§3.2 ポリゴン→ベジェ**: 本スパイクは polyline のまま UFO 搭載で fontmake 成功。節点爆発の実害は未定量 — 早期決定ゲートは継続。

---

## 6. 生成画像フルパス

- `/Users/motista/Desktop/antigravity/myfont/spike3/output/A_fill_check_juu.png`
- `/Users/motista/Desktop/antigravity/myfont/spike3/output/B_ft_juu.png`
- `/Users/motista/Desktop/antigravity/myfont/spike3/output/B_ft_juu_bin.png`
- `/Users/motista/Desktop/antigravity/myfont/spike3/output/B_poly_juu.png`
- `/Users/motista/Desktop/antigravity/myfont/spike3/output/B_poly_juu_bin.png`
- `/Users/motista/Desktop/antigravity/myfont/spike3/output/C_proof_juuni_ei.png`
- `/Users/motista/Desktop/antigravity/myfont/spike3/output/C_proof_hbview_juuni_ei.png`

OTF: `/Users/motista/Desktop/antigravity/myfont/spike3/output/MyMinchoSpike-Regular.otf`

---

## 7. 総括

| 検証 | PLAN 節 | 判定 |
|---|---|---|
| A P3 パイプ | §3.1 P3 / §0.1 | **条件付き** |
| B 物差し1本化 | §2.3 | **成立** |
| C 組見本 | §3.2 / P1 | **成立**（diffenator2 のみ失敗） |
