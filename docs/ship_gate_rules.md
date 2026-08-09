# 出荷ゲート採否ルール（S1）

`engine/scripts/ship_gate.py` が参照する合否方針。FontBakery の全警告ゼロは非現実なため、**fatal / warn-as-fail / ignore** をここで固定する。

## 必須（fail で非ゼロ終了）

| 検査 | 基準 |
|---|---|
| cmap 欠字 | `--glyphset` 必須。1行1字・非空。全字が cmap に存在し、かつ `.notdef` を指さない |
| unitsPerEm | `head.unitsPerEm = 1000`（`docs/design_rules.md`） |
| `.notdef` | グリフ名 `.notdef` が存在 |
| OS/2・hhea 縦方向メトリクス | ascender=880 / descender=−120（`docs/design_rules.md`） |
| name 必須レコード | Family / Subfamily / UniqueID / Full name / PostScript / 著作権 or ライセンス文字列のいずれか |
| `ulUnicodeRange` / `ulCodePageRange` | ハングル等の誤ビットを立てない（α/β: CJK＋Basic Latin 範囲のみ許可） |
| 輪郭サンプル (`outline_sample`) | pathops で代表グリフが描画・simplify できること。**pathops 欠落は未検証＝fail**（skip を ok にしない）。完全な自己交差ゼロ証明は別途 checkoutlinesufo 等（本ゲートはスモーク） |

## FontBakery universal

- 実行は任意（`fontbakery` が PATH / venv にあれば）。
- 次を **fail 扱い**: `com.google.fonts/check/family/win_ascent_and_descent` 相当で design_rules と矛盾するもの、cmap 欠落、壊れたテーブル。
- 次は **warn のみ（α では無視可）**: hinting 系、STAT 不在、GF 固有のメタデータ、縦書き関連。

詳細な check id のホワイトリストは FontBakery 導入後に本ファイルへ追記する。

## fsType（α）

α 配布は「商用保証なし・埋め込み可否は Embeddable（Installable / 0x0000 または Editable）」方針。最終ビットは S2b 確定後に固定し、S1⑦ で突合する。

## GSUB / GPOS

α/β は **未搭載でよい**。搭載していないことを確認するのみ（勝手に `liga` 等を売らない）。
