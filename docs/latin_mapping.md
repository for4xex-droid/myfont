# ラテン骨格の語彙

工程 2 の閉じた語彙。骨格 YAML は、ここにない値を書くとロードが失敗する。

## 節点

| 型 | 意味 |
|---|---|
| `smooth` | 接線が連続。Hobby 展開 |
| `corner` | 接線が不連続。ここで曲線を分ける |
| `line` | 隣の節点と直線で結ぶ。角度は付けられない |

接線を固定するときは、節点の4番目に角度（度。+x から反時計回り）を書く。`line` には付けない。

## 役割 `role`

`thick` / `thin` / `bar` / `bowl`

## 端 `ends`

`foot` / `apex` / `none` / `open` / `round_end`

どのテンプレになるかは様式が決める。

## 側面 `sides`（Tracy の5段）

`straight` / `near_straight` / `round` / `diagonal` / `open`

左右は独立。グループ名には使わない。

## 接合 `joins.type`

`apex` / `apex_cut` / `T` / `L` / `crotch` / `bowl_join`

## グループ `groups`

`straight` / `round` / `diagonal` / `open` / `bar`

ペンと比だけを上書きする。側面の空き（`sidebearing`）は書けない。

## 構造 `structure`

`stem_pair` / `bowl` / `apex_diagonals` / `spine` / `branch`

## 様式名（`variants` のキー）

`modern` / `classic` / `chic` / `pop`
