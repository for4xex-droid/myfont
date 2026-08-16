# UFO 正本置き場

- 手設計・マージ後の UFO をここに置く（git 管理可）
- ビルド成果物 OTF は `fonts_out/build/`（gitignore・掟10）
- 手設計保護リスト: `manual_glyphs.txt`（掟13）

## P1 手順（ひらがな核心20字）

**第一候補は P1-B**（`docs/kana_parametric_plan.md`）:
骨格 YAML（`engine/src/engine/kana/skeletons/`）→ `engine/scripts/regen.py --glyphs shi` → 組見本／盲検。
合否は人が見、探索空間はコードが閉じる。

方式A（Glyphs 手描き）退避時:
1. `engine/.venv/bin/python scripts/prepare_manual_a.py` で空の `MyMincho.ufo` と参照ラスタ背景を作る（済: 「あ」）
2. `DRAW_A.md` のとおり Glyphs で `uni3042` を3塗りする（なぞり禁止）
3. `manual_glyphs.txt` のコメントなし行が手描き済み（いま あ・う・え・お・か・き・け・こ・さ・す・せ・そ・た・ち・て）
4. エンジン字を足すとき: `scripts/merge_engine_ufo.py`（手描きはスキップ）
5. 重ね塗りを残して OTF 化（素の fontmake は交差が溶ける）:

```bash
engine/.venv/bin/python scripts/compile_manual_otf.py
```
6. `python scripts/make_proofs.py --font fonts_out/build/….otf` で UI/HUD 組見本
7. `docs/blind_test.md` の盲検へ

`manual_glyphs.txt` の uni 名は、P1-B 生成物を本ディレクトリへマージする際の上書き禁止リストとしても使う（掟13・20）。
