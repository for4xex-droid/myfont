# Spike5 検証報告: 黒み減衰カーブ実測 ＋ 文書整合性監査

日付: 2026-08-09  
作業場所: `/Users/motista/Desktop/antigravity/myfont/spike5/`  
venv: `spike/.venv` 流用  
フォント: `spike/fonts/NotoSerifJP-Regular-wght400.ttf`（既存・再取得不要）  
対象計画: `PLAN.md` v4 / `GOLDENRULES.md` / `WORKFLOW.md`  
**文書本体の修正は行っていない**（指摘と修正案のみ）。

---

## タスク1: 黒み減衰カーブの実在検証（P5 前提）

### プロトコル

| 項目 | 値 |
|---|---|
| 解像度 | 1024 px/EM |
| ロード | `FT_LOAD_NO_HINTING \| FT_LOAD_RENDER`、閾値 T=128 |
| (a) ink密度 | 黒画素数 / 字面 bbox 面積 |
| (b) 線幅代理 | `median_h_run`（水平走査黒ラン中央値≈縦画太さ）、`median_v_run`（垂直走査≈横画太さ）、結合 `√(h·v)` |
| サンプル | 画数既知の漢字 31 字（1〜29画） |
| 外れ値除外（回帰時） | 一（横画のみ）、乙・人（曲線・斜画でラン長汚染） |

### 計測表

| 字 | 画数 | ink密度 | 線幅代理(px) | H-run≈縦(px) | V-run≈横(px) |
|---|---:|---:|---:|---:|---:|
| 一 | 1 | 0.341 | 28.7 | 25 | 33 |
| 乙 | 1 | 0.208 | 80.8 | 96 | 68 |
| 二 | 2 | 0.096 | 47.7 | 76 | 30 |
| 十 | 2 | 0.109 | 45.1 | 70 | 29 |
| 人 | 2 | 0.129 | 85.7 | 68 | 108 |
| 口 | 3 | 0.233 | 45.2 | 68 | 30 |
| 三 | 3 | 0.115 | 46.8 | 73 | 30 |
| 土 | 3 | 0.143 | 46.2 | 69 | 31 |
| 日 | 4 | 0.277 | 44.8 | 67 | 30 |
| 木 | 4 | 0.190 | 54.7 | 68 | 44 |
| 月 | 4 | 0.222 | 44.8 | 67 | 30 |
| 田 | 5 | 0.306 | 44.8 | 67 | 30 |
| 目 | 5 | 0.294 | 45.2 | 68 | 30 |
| 永 | 5 | 0.193 | 55.9 | 68 | 46 |
| 本 | 5 | 0.201 | 45.2 | 68 | 30 |
| 字 | 6 | 0.178 | 45.9 | 68 | 31 |
| 年 | 6 | 0.196 | 46.6 | 70 | 31 |
| 東 | 8 | 0.268 | 45.2 | 68 | 30 |
| 国 | 8 | 0.323 | 45.6 | 67 | 31 |
| 明 | 8 | 0.309 | 43.8 | 64 | 30 |
| 書 | 10 | 0.290 | 44.5 | 66 | 30 |
| 時 | 10 | 0.291 | 44.2 | 65 | 30 |
| 語 | 14 | 0.287 | 42.7 | 63 | 29 |
| 質 | 15 | 0.298 | 44.9 | 65 | 31 |
| 論 | 15 | 0.325 | 42.4 | 60 | 30 |
| 講 | 17 | 0.354 | 43.5 | 63 | 30 |
| 職 | 18 | 0.378 | 43.1 | 60 | 31 |
| 議 | 20 | 0.350 | 43.5 | 63 | 30 |
| 競 | 20 | 0.345 | 43.1 | 62 | 30 |
| 鑑 | 23 | 0.376 | 44.8 | 59 | 34 |
| 鬱 | 29 | 0.398 | 45.4 | 59 | 35 |

CSV: `/Users/motista/Desktop/antigravity/myfont/spike5/output/density_curve_table.csv`

### プロット（フルパス）

- `/Users/motista/Desktop/antigravity/myfont/spike5/output/strokes_vs_density_width.png` — (a)密度 / (b)線幅代理
- `/Users/motista/Desktop/antigravity/myfont/spike5/output/strokes_vs_width_loglog.png` — 縦画代理の log-log
- `/Users/motista/Desktop/antigravity/myfont/spike5/output/strokes_vs_ink_per_stroke.png` — 参考: ink/画数

機械可読: `/Users/motista/Desktop/antigravity/myfont/spike5/output/density_curve_report.json`  
スクリプト: `/Users/motista/Desktop/antigravity/myfont/spike5/measure_density_curve.py`

### 回帰結果

| 対象 | α（幅 ∝ 画数^-α） | log-log r | 備考 |
|---|---:|---:|---|
| 結合線幅 √(h·v)、外れ値除外 | **0.036** | −0.45 | ほぼ平坦。主モデルに不適 |
| 縦画代理 median_h_run、除外後 | **0.072** | **−0.90** | 十 70px → 鬱 59px の弱い減衰 |
| 横画代理 median_v_run、除外後 | **0.001** | ≈0 | ≈30px で一定（明朝コントラストの横画） |
| ink密度 vs 画数（線形） | — | r=**+0.76** | 画数↑で密度↑（減衰で抑え切れていない） |

縦画のみの概算式（外れ値除外）:

```
median_h_run_px ≈ 76.1 × strokes^(-0.072)
```

### 判定（P5 前提）

**減衰カーブは「縦画に限った弱い減衰」として部分観測。結合線幅の明確な減衰カーブは観測できない。**

- 「画数が多い字ほど線を細くする」を**全体線幅の強いべき乗則**として読むなら **不成立**（α_combined≈0.04）。
- 縦画だけなら α≈**0.07** の弱い減衰は Noto Serif JP Regular で観測できる（十→鬱で約 −16%）。
- それでも **ink密度は画数と強く正相関**（r≈0.76）。実フォントは密度を一定に保つほどは細くしていない。

#### P5 への含意（前提修正案）

1. **主モデルは現状の「密度ヒューリスティック＋例外リスト」のままでよい**（密度上昇が実測の主現象）。
2. **「線幅 ∝ 画数^-α」を主ヒューリスティックにしない。** α の初期値を全体線幅に当てるなら非推奨。
3. 局部スケールを入れるなら **縦画のみ α≈0.07 を初期値**（従属）。横画は画数連動させない。
4. 例外判定の入力は画数より **ink密度（および字面内ムラ）** を優先する。

---

## タスク2: 文書群の整合性監査

対象: `PLAN.md` / `GOLDENRULES.md` / `WORKFLOW.md` / `prototype/REPORT.md` / `spike/SPIKE_REPORT.md` / `spike2/SPIKE2_REPORT.md` / `spike3/SPIKE3_REPORT.md`

重要度順。各指摘に修正案1行。

### 重要

1. **PLAN §1 依存図の T7 脚注が古い（v2 表現の残留）**  
   図下 `※ T7 は「同一freetype経路に載せる」か「別profileとして明示」が条件付きDoD` は、§2.3・T7 本文の「一時フォント化第一候補」と矛盾する。  
   **修正案:** 脚注を「T7 は一時フォント化→`ft_*` 第一候補。`poly_pillow_*` は union 前の暫定のみ（§2.3）」に置換。

2. **90日バックログの T6/T7 文言が古い**  
   §4 項目3: `T6/T7: 散布図＋bridge（profile 分離で）` は、現行の tempfont 第一候補方針とズレる。  
   **修正案:** `T6/T7: 散布図＋bridge（一時フォント化→ft 計測。poly は別profile明示）` に更新。

3. **90日バックログの「P4aスパイク」が spike2 完了後も未消化のまま**  
   項目5が「KAGE変換器＋100字品質レポート」のまま。spike2 で取得・カバー率・部品展開統計・写像表下書きは済んでいる。  
   **修正案:** 「P4a本番: 部品展開器本実装＋`docs/kage_mapping.md` 固定＋100字品質ゲート（spike2 前提は完了）」へ書き換える。

4. **PLAN §5 流用マップの組見本記述が §3.2 / WORKFLOW と不一致**  
   §3.2・WORKFLOW③ は hb-view/uharfbuzz 第一候補、diffenator2 は Py3.14 で失敗→条件付き。§5 は `diffenator2 proof / hb-view` を並列並記。  
   **修正案:** §5 を「第一候補: uharfbuzz/hb-view。diffenator2 は 3.12 別venv検証後のみ」に合わせる。

### 中

5. **正本パス `data/glyphset_*.txt` が未作成のまま「正」と書かれている**  
   PLAN §3.2・GOLDENRULES 掟19・配置表は `data/glyphset_*.txt`。実体は `spike2/output/glyphset_joyo2136.txt` のみ（`data/` ディレクトリ無し）。  
   **修正案:** 「試作: spike2/output/…。本番正本は `data/` へ凍結コミット後に切替」と一文で現状を明示する。

6. **render_profile 戦略が4箇所に重複し、片側だけ古い**  
   正本候補: PLAN §2.3＋T7、WORKFLOW①（tempfont）、掟4/5。§1脚注と§4バックログだけ旧表現が残存（指摘1・2と同根）。  
   **修正案:** 戦略の正本を §2.3 に一本化し、他は「§2.3 参照」に短縮して二重更新を防ぐ。

7. **掟8b / 12b / 17b の番号参照が PLAN・WORKFLOW に無い**  
   内容自体は T1・§0 GPL・§3.4 部品展開などに分散記載されているが、掟番号へのリンクが無く、追加掟の存在が見落とされやすい。  
   **修正案:** T1 に「（掟8b）」、§0/§6 GPL に「（掟12b）」、P4a/§3.4 に「（掟17b）」を括弧参照で足す。

8. **スパイク報告書の「PLAN を修正すべき点」がオープン課題に見える**  
   spike/spike2/spike3 の修正提案の多くは v4 に取り込まれ済みだが、レポート側は「修正すべき」のまま。  
   **修正案:** 各 SPIKE*_REPORT 冒頭に「対象 PLAN 版と取り込み状況（済/残）」を1行追記するか、PLAN 関連文書欄に「スパイク提案の反映済み」と注記。

9. **計測コーパス5書体リストとスパイク実測フォントの関係が不明瞭**  
   PLAN §0 の正式5書体に Noto は含まれないが、§0/§2.4 の校正アンカーは Noto Serif JP。  
   **修正案:** 「スパイク校正アンカーは Noto（源ノ明朝同系）。本番コーパス5書体とは別枠」と注記する。

10. **組見本ツール記述の重複（3文書）**  
    PLAN §3.2・§5・WORKFLOW③に同趣旨。§5だけ優先順位が古い（指摘4）。  
    **修正案:** WORKFLOW を運用手順の正、PLAN §3.2 を方針の正、§5 は一行参照に落とす。

### 低

11. **M4a/M4b と M2 予算の算術矛盾は無し。週次テンプレが M1/M2 固定**  
    予算自体は整合。`docs/weekly.md` の「M1/M2デモ可能日」は M3 以降で陳腐化する。  
    **修正案:** 「現行マイルストーン2つのデモ可能日」に一般化する（任意）。

12. **GOLDENRULES 掟14 の表記ゆれ**  
    `量産（P5)` と閉じ括弧前スペース欠落。  
    **修正案:** `量産（P5）` に修正。

13. **prototype/REPORT.md は PLAN 節番号をほとんど参照しない**  
    内容（接合未実装が最大穴）は PLAN §0/P2 と整合。宙参照は無し。  
    **修正案:** 冒頭に「PLAN §0・P2 の根拠実験」へのリンクを1行足す程度で十分。

14. **B系番号（B1–B4）は PLAN §2.8 と GOLDENRULES 命名表で一致**  
    衝突は検出されず。  
    **修正案:** なし（確認済み）。

15. **spike 成果物パス**  
    PLAN が指す `spike/SPIKE_REPORT.md`・`spike2/output/glyphset_*.txt`・`spike2/output/kage_mapping_table.md`・`spike3/output/MyMinchoSpike-Regular.otf` はいずれも存在。誤パスはこの監査範囲では未検出（`data/glyphset_*` のみ「将来パス」、指摘5）。  
    **修正案:** 指摘5に同じ。

---

## 観点別サマリ

| # | 観点 | 結果 |
|---|---|---|
| 1 | 節番号・タスクID・マイルストーン | §1 T7脚注と本文の食い違いが主。M4a/M4b↔M2予算は整合。B系OK |
| 2 | 掟番号参照 | 8b/12b/17b は GOLDENRULES のみ。PLAN/WORKFLOW から番号参照なし |
| 3 | render_profile | §2.3・T7・WORKFLOW・掟4/5 は概ね一致。§1脚注と90日BLが旧 |
| 4 | 組見本ツール | §3.2⇔WORKFLOW 一致（hb-view第一）。§5 だけ並列表記で古い |
| 5 | 重複更新リスク | render_profile / 組見本 / KAGE統計(86.8%) が多文書重複 |
| 6 | spikeパス | 参照先は概ね正しい。`data/glyphset_*` は未作成 |
| 7 | 90日BL vs 改訂後タスク | T7「profile分離」と P4aスパイクが改訂後実態と不整合 |

---

## 成果物一覧

| パス | 内容 |
|---|---|
| `spike5/measure_density_curve.py` | 計測・回帰・プロット |
| `spike5/output/density_curve_table.csv` | 31字の表 |
| `spike5/output/density_curve_report.json` | 機械可読結果 |
| `spike5/output/strokes_vs_density_width.png` | 主プロット |
| `spike5/output/strokes_vs_width_loglog.png` | log-log |
| `spike5/output/strokes_vs_ink_per_stroke.png` | 参考プロット |
| `spike5/SPIKE5_REPORT.md` | 本報告書 |

### 再実行

```bash
cd /Users/motista/Desktop/antigravity/myfont
export MPLCONFIGDIR=spike5/.mplconfig
spike/.venv/bin/python spike5/measure_density_curve.py
# 縦画回帰の詳細は density_curve_report.json の refined_fits（本レポート作成時に追記）
```
