# fontdb

自作明朝の設計支援用フォント要素データベース（PLAN トラックB）。

## セットアップ

```bash
cd fontdb
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## パイプライン

```bash
python scripts/01_fetch.py          # T1: 5書体取得（SHA256検証）
python scripts/02_init_db.py --reset  # T2: スキーマ＋シード
python scripts/03_render.py         # T3: 十のラスタ（hint on/off 差確認）
python scripts/04_glyph_metrics.py  # T4/T5α: glyph + probe → SQLite
python scripts/05_probes.py         # T5α: probe 結果表示
python scripts/07_viz_scatter.py    # T6: コントラスト×うろこ散布図
# T7/T7+ は engine 依存（pathops/fontmake）。fontdb venv に engine を入れる例:
#   pip install -e "../engine[join,bridge]"
python scripts/06_ingest_prototype.py          # 一時OTF → SQLite synthetic face
python scripts/06_ingest_prototype.py --no-db  # ファイル成果物のみ
python scripts/08_freeze_p0.py                 # P0: product_r1 を design_param_snapshot に frozen
# エンジン再生成（別 venv）:
#   cd ../engine && python scripts/regen.py --params product_r1
```

成果物:
- `data/db/fontdb.sqlite`
- `data/synthetic/*.otf`（gitignore）
- `output/measure_report.json`
- `output/scatters/scatter_contrast_uroko.png`
- `output/t7_bridge/`・`output/t7_ingest_report.json`

## 状態（2026-08-09）

- T0〜T6 実装済み・実行確認済み（5書体、glyph 60/60 ok、san_uroko 5/5 ok）
- T7: `engine.bridge` で一時フォント化（classic/product_r1）
- T7+: `face_kind=synthetic` で SQLite 正式 ingest（`config/synthetic_faces.yaml`）。juu contrast classic≈2.22 / product_r1≈2.43
- P0: `product_r1` frozen（`design_param_snapshot`）。字面規則は `docs/design_rules.md`
