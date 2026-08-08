# spike4 レポート — fontdb MVP 縮小実装による T1〜T6 実証

作業日: 2026-08-09  
作業場所: `/Users/motista/Desktop/antigravity/myfont/spike4/`  
対象計画: `PLAN.md` v4 トラックB（§2）  
前提: `spike/SPIKE_REPORT.md`（freetype 計測・交点回避・うろこ簡易検出）  
venv: `spike/.venv` 流用（matplotlib / PyYAML 追加）

---

## 1. 成果物一覧

| パス | 役割 |
|---|---|
| `spike4/fetch_corpus.py` | T1: 5書体取得＋可変→wght400＋`corpus_actual.yaml` 生成 |
| `spike4/run_mvp.py` | T2〜T6: DDL適用・glyph_metric・probe・散布図 |
| `spike4/schemas/schema.sql` | PLAN §2.2 準拠スキーマ |
| `spike4/corpus_actual.yaml` | 実取得記録（URL / SHA256 / ライセンス / 可変有無） |
| `spike4/data/fontdb.sqlite` | 計測結果 DB |
| `spike4/output/mvp_report.json` | 機械可読サマリ |
| `spike4/output/scatter_contrast_uroko.png` | コントラスト×うろこ散布図 |
| `spike4/output/raster_*_{十,三}*.png` | 書体別ラスタ／二値プレビュー |
| `spike4/fonts/*-Regular.{otf,ttf}` | 計測用フェイス（gitignore 想定） |
| `spike4/SPIKE4_REPORT.md` | 本報告書 |

散布図フルパス:

`/Users/motista/Desktop/antigravity/myfont/spike4/output/scatter_contrast_uroko.png`

---

## 2. A. 計測コーパス5書体の実取得（T1 実証）

**結果: 5/5 取得成功。いずれも静的 Regular（可変なし → インスタンス化不要）。**

| family_id | 表示名 | 取得 | URL | SHA256（計測ファイル） | ライセンス | 可変 |
|---|---|---|---|---|---|---|
| source_han_serif_jp | 源ノ明朝 | ✅ | `adobe-fonts/source-han-serif` release `2.003R` / `12_SourceHanSerifJP.zip` → `SubsetOTF/JP/SourceHanSerifJP-Regular.otf` | `e5f502bb193c28829895b098498f0f9dd8f658c760b0f83656ad41c1137a8785` | OFL-1.1 | 否 |
| ipaex_mincho | IPAex明朝 | ✅ | `https://moji.or.jp/wp-content/ipafont/IPAexfont/ipaexm00401.zip` → `ipaexm.ttf` | `7a306386f930fee80922f71eebf4ffe0f1ff2817da8e619230953487673d71c7` | IPA Font License | 否 |
| shippori_mincho | しっぽり明朝 | ✅ | `google/fonts` `ofl/shipporimincho/ShipporiMincho-Regular.ttf` | `769b5269f0f9bc6534b352c0e6bd856a566e03ff788f107191c2d835863570b2` | OFL-1.1 | 否 |
| zen_old_mincho | Zen Old Mincho | ✅ | `google/fonts` `ofl/zenoldmincho/ZenOldMincho-Regular.ttf` | `4c051a78a21c4e8e9dccf1c754776d33f356b8cc6ef95d9b64761b9bae814b84` | OFL-1.1 | 否 |
| biz_ud_mincho | BIZ UD明朝 | ✅ | `google/fonts` `ofl/bizudmincho/BIZUDMincho-Regular.ttf` | `468ee6d9b149ca144809e03841bf18740ecf014e055a00da6ecaf1aaf4165af2` | OFL-1.1 | 否 |

補足:
- **IPAex**: moji.or.jp 公式 zip がそのまま取得可。ミラー（旧 `ipafont.ipa.go.jp`）は未使用（本線成功のため）。取得スクリプトにはフォールバック URL を記録済み。
- **源ノ明朝**: フル OTF 一式ではなく JP subset zip（≈35MB）で十分。静的 Regular。
- **google/fonts 3書体**: METADATA 上も静的ウェイト別ファイル。可変インスタンス化は不要だった（T1 の可変分岐はコード上実装済みで、今回は未発火）。
- UPM: SourceHan/Shippori/Zen=1000、IPAex/BIZ=2048。ラスタは `set_pixel_sizes(1024,1024)` で EM 正規化。

---

## 3. B. スキーマ＋計測＋probe（T2〜T5α 実証）

### 3.1 スキーマ

`family` / `face` / `render_profile` / `extractor` / `glyph_metric` / `probe_def` / `probe_metric` を SQLite に適用。profile=`ft_1024_nohint_gray_v1`、extractor=`spike4_v1`。

### 3.2 glyph_metric

代表字 12: `三・十・口・田・国・日・東・鬱・永・あ・の・ん`  
条件: 1024px/EM・hinting off・T=128（spike 流用）

| 指標 | 結果 |
|---|---|
| 行数 | 5 face × 12 字 = **60** |
| status=ok | **60/60**（欠字なし） |

### 3.3 probe 計測値（全書体）

| 書体 | juu_contrast（縦/横） | 横太さ px | san_uroko 相対 | うろこ突出 px | juu | san |
|---|---:|---:|---:|---:|---|---|
| 源ノ明朝 | **2.414** | 29 | **0.862** | 25 | ok | ok |
| IPAex明朝 | **2.500** | 26 | **0.852** | 23 | ok | ok |
| しっぽり明朝 | **2.464** | 28 | **0.862** | 25 | ok | ok |
| Zen Old Mincho | **2.400** | 30 | **0.839** | 26 | ok | ok |
| BIZ UD明朝 | **1.346** | 52 | **0.412** | 21 | ok | ok |

源ノ明朝の十コントラスト ≈2.41 は spike の Noto Serif JP Regular アンカーと一致（同一系統）。

### 3.4 san_uroko 書体別安定性（本丸）

**判定: 書体別チューニングなしで 5/5 が ok。**

実装: 水平投影ピーク検出 → 上横画帯 ROI → 右端12%の突出高さ / 本体太さ。  
共通閾値: `protrusion≥3px & rel≥0.15` → clear ok / `protrusion<2 & rel<0.08` → 様式的ゼロも ok / 中間 → low_confidence。

| 書体 | status | 所見 |
|---|---|---|
| 源ノ明朝 | ok | 明確なうろこ（rel≈0.86） |
| IPAex明朝 | ok | 同上（rel≈0.85） |
| しっぽり明朝 | ok | 同上（rel≈0.86） |
| Zen Old Mincho | ok | 同上（rel≈0.84） |
| BIZ UD明朝 | ok | **うろこは小さいが閾値超え**（rel≈0.41, 21px）。予想された「閾値未満 fail」にはならなかった。低コントラスト（UD 設計）とセットで外れ値 |

fail / low_confidence は今回 **0件**。  
ただし BIZ は従来明朝クラスタから離れており、閾値を厳しくすると最初に落ちる候補（安定化策は §5）。

---

## 4. C. 散布図（T6 実証）

ファイル: `/Users/motista/Desktop/antigravity/myfont/spike4/output/scatter_contrast_uroko.png`

| 指標 | 値 |
|---|---|
| contrast_span | **1.15**（1.35〜2.50） |
| uroko_span | **0.45**（0.41〜0.86） |
| 意味のある差 | **あり**（判定閾値 0.15 を両軸で超過） |

読み取り: 伝統的明朝4書体は (contrast≈2.4–2.5, uroko≈0.84–0.86) に密集。BIZ UD だけ (1.35, 0.41) に孤立 → 指標として様式差を分離できている。

---

## 5. D. 総括

### 5.1 fontdb MVP（T0〜T7）残作業の再見積もり

今回の縮小実装コード量: **≈960 LOC**（fetch 289 + run_mvp 588 + schema 81）。これで T1〜T6 の **危険箇所（取得可能性・san_uroko 安定性・散布図分離）は実証済み**。

| ID | 残作業 | 見積 h | 根拠 |
|---|---|---:|---|
| T0 | pyproject 分割・パッケージ化・空 pytest | 8–12 | 未着手。依存は spike venv で確認済 |
| T1 | 本番 fetch（欠落非ゼロ・ライセンス条文固定・SHA 突合 CI） | 4–6 | 取得経路は確定。製品化のみ |
| T2 | 冪等シードスクリプト | 2–4 | schema は流用可 |
| T3 | 黄金画像＋hint on/off ハッシュテスト | 8–12 | ラスタは動く。テスト資産が本体 |
| T4 | ≈20字・欠字ケース・API 整備 | 4–6 | 12字 ok 済み |
| T5α | fixture 単体テスト・fail率 yaml 固定 | 8–12 | probe は 5/5 ok。回帰テストが残 |
| T6 | 散布図①（字面×黒み）＋SVG・凡例 | 4–6 | ②は完了 |
| T7 | bridge（union→UFO→OTF→freetype） | 12–18 | spike3 経路あり。登録配線が残 |
| **合計** | | **50–76h** | PLAN の 60–100h から **下方修正** |

リスク消化分: T1 取得失敗・san_uroko 全面不安定は今回否定できた。残はエンジニアリング（テスト・パッケージ・T7 配線）が主。

### 5.2 PLAN §2.4 に追記すべき安定化策

1. **san_uroko 手順を固定**: 「行投影を平滑化 → 上部45%内ピーク → 投影45%帯を上横画 → 帯±マージン ROI → 中央35–70%列で本体上面 → 右端12%列で突出」。帯幅が異常なら上部28%フォールバック。
2. **共通閾値の文書化**: clear / stylistic-zero / ambiguous の3帯。書体別チューニング禁止を明示。
3. **BIZ UD を校正アンカー外れ値として登録**: 低コントラスト＋小うろこでも ok になること、閾値厳格化時の最初の脱落候補であること。
4. **様式的ゼロと検出不能の分離**: value≈0 かつ status=ok（stylistic zero）vs low_confidence（ambiguous）。今回5書体はすべて clear。
5. **juu_contrast**: 交点回避オフセット（±0.15/0.22 face）＋中央値は維持。源ノ明朝≈2.41 を期待値アンカーに追加（Noto と併記可）。
6. **UPM 混在**: IPAex/BIZ は 2048。必ず `set_pixel_sizes(EM_PX,EM_PX)` で正規化し、px 比較を EM 正規化キャンバス上で行う。
7. **散布図ラベル**: matplotlib 既定フォントは CJK 欠ける → family_id / ASCII 名を使う。

### 5.3 PLAN 修正点リスト

1. **§2.6 T1**: 5書体の確定 URL を追記（本レポート §2 表）。IPAex は moji.or.jp で取得可（取得不能前提を撤回）。
2. **§2.6 T1**: 今回コーパスはすべて静的 Regular。可変分岐は「将来の可変コーパス用」として残すが、現行5書体では必須発火しない旨を注記。
3. **§2.4 san_uroko**: 上記安定化策（投影ピーク手順＋共通閾値）をプロトコル本文へ。
4. **§2.4**: BIZ UD は「小うろこで fail しやすい」ではなく「相対値は小さいが共通閾値では ok、クラスタ外れ値」と実測に合わせて修正。
5. **§2.6 見積もり**: 60–100h → **50–76h**（取得・probe 安定性リスク消化後）。
6. **§2.5**: 散布図②は書体間差が実証済み（BIZ 分離）。①の優先度を上げてよい。

---

## 6. 実行コマンド

```bash
cd /Users/motista/Desktop/antigravity/myfont
# 依存（初回）: spike/.venv/bin/pip install matplotlib pyyaml
spike/.venv/bin/python spike4/fetch_corpus.py
spike/.venv/bin/python spike4/run_mvp.py
```

---

## 7. 総合判定

| 項目 | 判定 |
|---|---|
| A 5書体取得 | **成立（5/5）** |
| B glyph_metric | **成立（60/60 ok）** |
| B juu_contrast | **成立（5/5 ok）** |
| B san_uroko 無調整安定 | **成立（5/5 ok）** |
| C 散布図の意味差 | **成立**（BIZ が明確に分離） |
| MVP 残工数 | **50–76h に下方修正推奨** |
