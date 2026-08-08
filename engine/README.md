# mymincho-engine

自作明朝フォントのエンジン本実装（PLAN トラックA / P2 以降）。  
spike6 の交差ソルバと prototype の肉付け・骨格、spike3 の一時フォント bridge（T7）をここへ集約。

## セットアップ

```bash
cd engine
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,join,bridge]"
pytest
```

交差ソルバのみ / bridge なしスモーク:

```bash
pip install -e ".[dev,join]"
pytest tests/test_smoke.py tests/test_regression_join.py
```

## レイアウト

```
engine/
  src/engine/
    geometry.py / strokes.py / skeletons.py / params.py
    join_solver.py          # Stage A+B 接合
    bridge.py               # T7: y_for_font → UFO → OTF → 計測
    extra_skeletons.py
  params/product_r1.yaml
  scripts/t7_bridge.py
  tests/
```

パラメータ: `classic` / `modern` / `product_r1`（正本 `params/product_r1.yaml`）。

### 座標（掟1）

内部は `COORDINATE_SPACE = "svg_y_down_legacy"`。  
T7 bridge が UFO 書き出し時に `y_for_font()` でフォント空間へ変換する（内部の一括移行は肉付け符号と同時にのみ）。

## T7 bridge

```bash
cd engine
python scripts/t7_bridge.py --params classic
python scripts/t7_bridge.py --params product_r1
```

または fontdb 側:

```bash
cd fontdb
python scripts/06_ingest_prototype.py
```

実測例（ft_1024_nohint_gray_v1）: classic 十 contrast≈2.22 / product_r1≈2.43（アンカー 2.44 に近い）。

## 接合回帰（掟14）

正本: リポジトリ根の `tests/regression_join20.yaml`（20字）。

```bash
pytest tests/test_regression_join.py -v
```

20字×3 params（classic/modern/product_r1）グリーン（`upm_area_ratio=0.0035`）。
