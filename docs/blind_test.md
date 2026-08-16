# 仮名盲検プロトコル（S4）

α 版の唯一の Go/No-Go 判定装置。事業ポジション（インディー／同人のゲーム・アプリ組込）に合わせ、**主面は短文 UI とゲーム HUD**とする。文芸本文は参考観測であり、合否に使わない。

## 合否定義（α Go/No-Go）

| 面 | 文面ファイル | 役割 | 合格ライン |
|---|---|---|---|
| UI | `proofs/texts/ui.txt` | **主** | 評価者 3 名中 **≥2** が「使える」 |
| HUD | `proofs/texts/hud.txt` | **主** | 評価者 3 名中 **≥2** が「使える」 |
| 文芸本文 | `proofs/texts/literary.txt` | 副・参考 | 記録のみ（Go/No-Go に使わない） |

**α Go = UI≥2/3 かつ HUD≥2/3。**

## 評価者

- 人数: **3 名**
- うち **ゲーム／同人制作者 ≥2 名**（属性を記録シートに明記）
- 残り 1 名はデザイナ／一般読者でも可
- 作者本人は評価者に含めない

## 提示手順（操作耐性）

1. 比較対象書体を **1 種**混入する（既存明朝。ファイル名は下記「比較対象の固定」）。
2. 各面（UI / HUD / 文芸）について、MyMincho と比較対象を **提示順ランダム**で並べる（コイン／乱数。順序を記録）。
3. 評価者には書体名を見せない（ファイル名を伏せ、A/B ラベルのみ）。
4. 質問は二択のみ: **「この用途で使えるか？」→ Yes / No**。
5. 面ごとに独立して回答させる（UI の結果を HUD に引きずらない）。

## 比較対象の固定

| キー | 書体 | 備考 |
|---|---|---|
| `compare_a` | IPAex明朝（コーパス登録済み） | 既定の混入書体。`fontdb/config/corpus.yaml` の IPAex エントリ |

変更する場合は本ファイルとコミットメッセージで明示する（掟18）。

## 記録シート（最小）

```
日付:
評価者ID / 属性（ゲーム・同人 / その他）:
面: UI | HUD | literary
提示順: A=____ B=____
回答: A=Yes/No  B=Yes/No
（MyMincho がどちらかは集計時に開封）
コメント（任意・1行）:
```

集計後、MyMincho 側の Yes 数だけを面ごとに数え、上記合格ラインに照らす。

## 組見本の生成

```bash
# α OTF（または比較用フォント）に対して
python scripts/make_proofs.py --font path/to/MyMincho-Regular.otf
# → proofs/out/{ui,hud,literary}.png

# 凍結版と比較（黄金画像がある場合）
python scripts/make_proofs.py --font path/to/MyMincho-Regular.otf --compare-golden
```

黄金画像の更新はバージョン付きコミット（掟18）。`proofs/golden/` に置く。

## P1 との関係

- P1 のひらがな核心20字（`data/glyphset_p1_kana_core20.txt`）が組める状態になってから本盲検を実施する。
- 盲検不合格時はエンジン開発より P1 に回帰する（掟20）。例外リスト増で誤魔化さない。

## 文面と収録字の注意

`proofs/texts/{ui,hud,literary}.txt` は α 本盲検の代表文。漢字・カタカナ・英数を含む。

P1 核心20字＋の だけの今は、豆腐で落とさないために **仮名縮小文面** を使う。

| 面 | 文面 | 役割 |
|---|---|---|
| UI | `proofs/texts/ui_kana.txt` | P1 主 |
| HUD | `proofs/texts/hud_kana.txt` | P1 主 |
| 歩行 | `proofs/texts/walk_kana.txt` | 内部目視。合否に使わない |

収録字以外（ん・は・濁点・小書きつ など）は使っていない。α 本盲検に戻すときは `ui.txt` / `hud.txt` に戻す。

```bash
engine/.venv/bin/python scripts/compile_manual_otf.py
engine/.venv/bin/python scripts/make_proofs.py \
  --font fonts_out/build/MyMincho.otf \
  --faces ui_kana,hud_kana,walk_kana \
  --out proofs/out
engine/.venv/bin/python scripts/make_blind_packet.py \
  --font fonts_out/build/MyMincho.otf --seed 20260816
# → proofs/out/blind/{ui_kana,hud_kana}/{A,B}.png
# 対応表は proofs/out/blind/SEALED_order.json（評価者に見せない）
```

黄金: `proofs/golden/g3_blind/`（MyMincho 側のみ。比較書体の画像は凍結しない）。
