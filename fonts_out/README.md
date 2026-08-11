# UFO 正本置き場

- 手設計・マージ後の UFO をここに置く（git 管理可）
- ビルド成果物 OTF は `fonts_out/build/`（gitignore・掟10）
- 手設計保護リスト: `manual_glyphs.txt`（掟13）

## P1 手順（ひらがな核心20字）

**第一候補は P1-B**（`docs/kana_parametric_plan.md`）:
骨格 YAML（`engine/src/engine/kana/skeletons/`）→ `engine/scripts/regen.py --glyphs shi` → 組見本／盲検。
合否は人が見、探索空間はコードが閉じる。

方式A（Glyphs 手描き）退避時:
1. `data/glyphset_p1_kana_core20.txt` の字を紙／iPad でラフ
2. Glyphs で清書 → UFO エクスポート → 本ディレクトリへ
3. `manual_glyphs.txt` にグリフ名があることを確認
4. `python scripts/make_proofs.py --font fonts_out/build/….otf` で UI/HUD 組見本
5. `docs/blind_test.md` の盲検へ

`manual_glyphs.txt` の uni 名は、P1-B 生成物を本ディレクトリへマージする際の上書き禁止リストとしても使う（掟13・20）。
