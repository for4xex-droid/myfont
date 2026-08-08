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
```

成果物:
- `data/db/fontdb.sqlite`
- `output/measure_report.json`
- `output/scatters/scatter_contrast_uroko.png`

## 状態（2026-08-09）

- T0〜T6 実装済み・実行確認済み（5書体、glyph 60/60 ok、san_uroko 5/5 ok）
- T7（prototype bridge）は未実装（spike3 経路の昇格待ち）
