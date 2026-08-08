# KAGE type × endpoint tag → internal mapping (sample)

| combo | type | start | end | count | → kind | → start_tag | → end_tag | status |
|---|---|---|---|---|---|---|---|---|
| `t1_s0_e0` | straight | 0 | 0 | 74 | horizontal | none | none | ok |
| `t1_s2_e2` | straight | 2 | 2 | 54 | horizontal | uchikomi | uroko | ok |
| `t2_s7_e8` | curve | 7 | 8 | 36 | right_hara | none | none | ok |
| `t2_s0_e7` | curve | 0 | 7 | 24 | right_hara | none | tome | ok |
| `t1_s12_e13` | straight | 12 | 13 | 19 | horizontal | uchikomi | none | ok |
| `t1_s22_e23` | straight | 22 | 23 | 19 | horizontal | uchikomi | tome | ok |
| `t2_s7_e0` | curve | 7 | 0 | 10 | right_hara | none | none | ok |
| `t2_s32_e7` | curve | 32 | 7 | 6 | right_hara | uchikomi | tome | ok |
| `t1_s0_e32` | straight | 0 | 32 | 6 | horizontal | none | uchikomi | ok |
| `t1_s32_e32` | straight | 32 | 32 | 6 | horizontal | uchikomi | uchikomi | ok |
| `t1_s32_e0` | straight | 32 | 0 | 6 | horizontal | uchikomi | none | ok |
| `t1_s0_e13` | straight | 0 | 13 | 3 | horizontal | none | none | ok |
| `t1_s0_e23` | straight | 0 | 23 | 3 | horizontal | none | tome | ok |
| `t1_s2_e0` | straight | 2 | 0 | 3 | horizontal | uchikomi | none | ok |
| `t1_s0_e4` | straight | 0 | 4 | 3 | horizontal | none | hane | ok |
| `t1_s0_e2` | straight | 0 | 2 | 3 | horizontal | none | uroko | ok |
| `t1_s22_e4` | straight | 22 | 4 | 3 | horizontal | uchikomi | hane | ok |
| `t2_s22_e7` | curve | 22 | 7 | 3 | right_hara | uchikomi | tome | ok |
| `t7_s0_e7` | vertical_sweep | 0 | 7 | 2 | left_hara | none | tome | ok |
| `t0_s0_e0` | special | 0 | 0 | 2 | UNSUPPORTED:special | none | none | needs_work |
| `t2_s12_e7` | curve | 12 | 7 | 2 | right_hara | uchikomi | tome | ok |
| `t6_s0_e5` | complex_curve | 0 | 5 | 2 | APPROX:complex_curve→polyline/cubic | none | taper | needs_work |
| `t1_s12_e0` | straight | 12 | 0 | 2 | horizontal | uchikomi | none | ok |
| `t6_s22_e4` | complex_curve | 22 | 4 | 1 | APPROX:complex_curve→polyline/cubic | uchikomi | hane | needs_work |
| `t1_s32_e4` | straight | 32 | 4 | 1 | horizontal | uchikomi | hane | ok |
| `t3_s0_e5` | bend | 0 | 5 | 1 | SPLIT:bend→2 segments | none | taper | needs_work |
| `t7_s32_e7` | vertical_sweep | 32 | 7 | 1 | left_hara | uchikomi | tome | ok |
| `t3_s32_e5` | bend | 32 | 5 | 1 | SPLIT:bend→2 segments | uchikomi | taper | needs_work |
| `t1_s12_e32` | straight | 12 | 32 | 1 | horizontal | uchikomi | uchikomi | ok |
| `t2_s22_e4` | curve | 22 | 4 | 1 | right_hara | uchikomi | hane | ok |

## Hard cases

- `t0_s0_e0` (n=2): UNSUPPORTED:special — 特殊行
- `t6_s0_e5` (n=2): APPROX:complex_curve→polyline/cubic — 複曲線は4制御点→3次ベジェor分割
- `t6_s22_e4` (n=1): APPROX:complex_curve→polyline/cubic — 複曲線は4制御点→3次ベジェor分割
- `t3_s0_e5` (n=1): SPLIT:bend→2 segments — 折れは2直線に分割が必要（内部に bend kind なし）
- `t3_s32_e5` (n=1): SPLIT:bend→2 segments — 折れは2直線に分割が必要（内部に bend kind なし）

## Effort verdict

条件付き妥当: ダンプ行パース自体は軽いが、部品再帰展開・エイリアス解決・折れ/複曲線の分割・端点タグ写像表が本体。変換器骨格は数日〜1週間、100字品質レポート（目視＋スコア）が主コスト。PLANのP4aを「写像仕様書＋100字ゲート」と置いているのは妥当。ただし『パース数十行で常用2,136字の骨格が得られる』は『展開後polylineが得られる』意味では条件付き成立、『製品品質の内部形式』意味では不成立（層A〜Cが必要）。
