# 「き」を Glyphs で描く

**済（G1）**。正本: `fonts_out/MyMincho.ufo` の `uni304D`。黄金 `proofs/golden/kana_ki/FREEZE_g1.json`。
「あ」は触らない。

参照4書体の「き」は出荷では 1〜2 輪郭（union 済み）だが、**描くときは分けたまま**にする。合体しない。

## 開く

1. Glyphs で `MyMincho.ufo` を開く
2. `uni304D`（き）をダブルクリック
3. **表示 → 画像を表示** をオン
4. 見えなければ `proofs/review/き/glyphs_bg/き_guide_ipaex.png` をキャンバスへドラッグ

空のときの灰色の「き」は仮表示。点を置くと消える。本物は画像ガイド。

## 3塗り

1. **上の横**
2. **下の横**（上より短いことが多い）
3. **縦** … 二つの横を下り、下で左へ払う

重なってよい。穴パスは作らない。**Filter → Remove Overlap** は使わない。

交差が白くなったら、そのパスだけ右クリック **Reverse Selected Contours**。

描画時の目安は LSB 126・幅 1000。G1 実測は LSB 182 / RSB 162（字間帯は未調整）。
