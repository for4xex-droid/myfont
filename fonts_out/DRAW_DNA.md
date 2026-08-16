# P-D1 デザインDNA（A）— つ・づ・っ の中腹

**済（P-D1）**。黄金 `kana_g3_blind_d1`。E1 以降も同じ DNA を通す。

正本 `fonts_out/MyMincho.ufo` を Glyphs で開かない。
37字は DNA A 済み。つ系の再調整が要るときだけこの手順。

目的: 弧の途中が髪の毛にならない。入口の打ち込みと抜きは触らない。現状（ワープ前）の太さには戻さない。

## 開く

1. Glyphs で `fonts_out/manual_kana/つ.ufo` を開く
2. `uni3064` をダブルクリック
3. 曲がりの中腹だけ少し肉を戻す
4. File → Save
5. づ（`uni3065`）・っ（`uni3063`）も同じ

中腹を戻したあと、骨格だけ離す:

`engine/.venv/bin/python scripts/diverge_dna.py つ づ っ --apply --stem`

終わったら37字まとめて受け取る（3字だけだと他字が HEAD に戻る）:

`engine/.venv/bin/python scripts/receive_manual.py --force あ い う え お か き く け こ さ し す せ そ た ち つ て と の は ひ ほ ま め や る り を ん っ が じ づ ぞ ぼ`

（つ系以外もワープ済みなので、37字まとめて受け入れる）

## やらない

- 正本を開く
- つを元の幅まで戻す（IPAex に寄る）
- 他の34字を「つに合わせて」いじる
- E1 の描き始め（37字の受け入れ後）
