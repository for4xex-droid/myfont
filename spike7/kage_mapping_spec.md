# KAGE → prototype 写像仕様（spike7 下書き）

本番文書は `docs/kage_mapping.md` へ昇格予定。本ファイルは P4a スパイクの写像仕様ドラフト。

## 座標

| 空間 | 範囲 | Y |
|---|---|---|
| KAGE | 200×200 | 下向き |
| prototype（本スパイク） | UPM=1000 | 下向き（SVG互換） |
| 製品内部（PLAN §0.1） | UPM=1000 | **上向き** |

変換（スパイク）: `(x', y') = (5x, 5y)` のみ。  
製品移行時: さらに `y'' = 1000 - y'` と輪郭巻き方向の正規化が必要。

## 筆画タイプ

| KAGE type | 処理 | prototype kind | フォールバック |
|---|---|---|---|
| 1 直線 | 傾きで H/V | `horizontal` / `vertical` | — |
| 2 曲線 | 2次→3次次数上げ、方向で種別 | `left_hara` / `right_hara` / `ten` | 短曲線→`ten` |
| 3 折れ | 2直線に分割 | H/V ×2 | `bend_split` |
| 4 乙 | 2セグメント近似 | H/V ×2 | `otsu_split` |
| 6 複曲線 | 4点を cubic として使用 | はらい/点 | `complex_curve_as_cubic` |
| 7 縦払い | 次数上げ＋左はらい | `left_hara` | `vertical_sweep_as_left_hara` |
| 0 特殊 | スキップ | — | `special_skip` |
| 99 部品 | 展開器で解決済み前提 | — | — |

曲線種別ヒューリスティック（UPM空間）:
- `|dx|<125` かつ `|dy|<200` かつ 長さ`<275` → `ten`
- それ以外 `dx<0` → `left_hara`、`dx≥0` → `right_hara`

## 端点タグ

| KAGE tag | 始点 | 終点 |
|---|---|---|
| 0 | none（※） | none（※） |
| 2 | uchikomi | uroko |
| 4 / 24 | hane | hane |
| 5 | taper | taper |
| 7 | none | tome |
| 8 | none | none |
| 12 / 32 | uchikomi | （接続） |
| 22 / 23 | uchikomi | tome |

※ **両端 tag=0（完全 open）のときだけ黙定**: 横=`uchikomi`+`uroko`、縦=`uchikomi`+`tome`。  
KAGE描画エンジンの黙定ディテールをタグ駆動の prototype に近づけるためのスパイク規則。接続タグ付き画には適用しない。

## 既知の損失

1. 接続文脈依存のタグ意味（同じ数値でも役割が違う）は未モデル化
2. 囲みの右上角でうろこ＋縦画打ち込みが二重に飛び出す（接合未実装と相乗）
3. type6 の複曲線は厳密な KAGE 描画と一致しない
4. 製品座標（Y上）への変換は本スパイク範囲外
