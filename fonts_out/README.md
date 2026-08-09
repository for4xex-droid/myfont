# UFO 正本置き場

- 手設計・マージ後の UFO をここに置く（git 管理可）
- ビルド成果物 OTF は `fonts_out/build/`（gitignore・掟10）
- 手設計保護リスト: `manual_glyphs.txt`（掟13）

## P1 手順（ひらがな核心20字）

1. `data/glyphset_p1_kana_core20.txt` の字を紙／iPad でラフ
2. Glyphs で清書 → UFO エクスポート → 本ディレクトリへ
3. `manual_glyphs.txt` にグリフ名があることを確認
4. `python scripts/make_proofs.py --font fonts_out/build/….otf` で UI/HUD 組見本
5. `docs/blind_test.md` の盲検へ

エンジン量産で仮名を上書きしないこと（掟13・20）。
