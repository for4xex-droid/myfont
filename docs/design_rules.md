# 字面・advance 規則（P0）

製品候補パラメータ `product_r1`（frozen）に紐づくレイアウト正本。

## 単位

| 項目 | 値 |
|---|---|
| `units_per_em` | **1000** |
| 内部設計座標 | フォント空間・Y上（書き出し直前変換。現状 engine は legacy SVG Y下＋`y_for_font`） |

## Advance

| 種別 | 方針 |
|---|---|
| 漢字（常用ほかエンジン生成） | **全角幅 = 1000**（固定） |
| 仮名 | P1 手設計で決定。当面の方針は「読みやすさ優先のプロポーショナル可」。未設計字は全角 1000 でプレースホルダ可 |
| 約物・数字 | P1 で手設計。等幅数字は後続で検討 |
| `.notdef` | 幅 1000 |

## 字面ボックス（縦メトリクス）

| 項目 | 値（UPM） |
|---|---|
| ascender | **880** |
| descender | **-120** |
| 行の高さ目安 | 1000（ascender − descender） |
| xHeight / capHeight（仮） | 500 / 800（Latin 混植時のプレースホルダ） |

インクの主領域は概ね x∈[80, 920]、y∈[80, 880]（フォント空間）を想定。厳密な仮想ボディは P1 組見本で再確認する。

## パラメータ固定

- 正本 YAML: `engine/params/product_r1.yaml`（`status: frozen`）
- DB 登録: `cd fontdb && python scripts/08_freeze_p0.py`  
  → `design_param_snapshot.snapshot_id = product_r1`（YAML の `frozen_at` を保持）
- 自作計測面: 上記スクリプトが `mymincho_t7_product_r1_regular` を `face_param_link` で紐付け（face が既にある場合）
- 再生成: `engine/scripts/regen.py --params product_r1`

## 変更ルール（掟16）

パラメータを変えるときは **新しい snapshot_id** を切り、旧 `product_r1` を上書きしない（`product_r2` 等）。  
既に `frozen` の行で `params_sha256` が変わった UPSERT はコードが拒否する。無名の「最新params」で DB を汚染しない。
