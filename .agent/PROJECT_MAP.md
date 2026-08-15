# MyMincho 向けワークフロー読み替え

`.agent/workflows/` は tango-apps / Aiome 由来。**手順・ゲートの骨格は維持**し、固有名詞とコマンドだけこの表に置き換える。`GOLDENRULES.md` が常に最優先。

## 正本ドキュメント

| 元ワークフローの参照 | このリポジトリ |
|---|---|
| `ARCHITECTURE.md` | `PLAN.md` |
| `.context/RIPPLE_MAP.md` | `docs/weekly.md` ＋該当 `docs/*.md`（波及は grep） |
| `AGENTS.md` / Golden Rule | `GOLDENRULES.md` |
| `CHANGELOG.md` | `docs/weekly.md`（3行）＋必要なら該当計画書 |
| `docs/decisions/` ADR | 該当 `docs/*_plan.md` または `PLAN.md` 追記 |
| `OPEN.md` | `docs/weekly.md` の「今週の一手」 |
| Feature Flag / Canary | 仮名は `kana_mode` / snapshot yaml。出荷は黄金凍結（掟18） |
| `cargo test` / `npm test` | 下表の pytest |
| `cargo check` / `clippy` | `engine/.venv/bin/python -m pytest engine/tests -q` |
| `gitleaks` + `cargo audit` | `.env` 非コミット確認 ＋ 秘密情報の grep。依存は必要時のみ |
| `/deep-scan` / `/release-preflight` | `/preflight` ＋ `engine/scripts/ship_gate.py` |
| Aiome / RIPPLE / TypeState | 使わない。フォント幾何・ゲート・黄金に読み替える |

## 実行コマンド

```bash
# エンジン回帰
engine/.venv/bin/python -m pytest engine/tests -q

# 仮名ゲート / レンダ / 1ステップ帯合わせ
engine/.venv/bin/python engine/scripts/kana_gate.py <gid>
engine/.venv/bin/python engine/scripts/kana_render.py --glyph <gid>
engine/.venv/bin/python engine/scripts/kana_fit_step.py <gid> --char <字> --regen --render

# OTF 再生成
engine/.venv/bin/python engine/scripts/regen.py --params product_r1 --glyphs <ids...>

# 出荷スモーク
engine/.venv/bin/python engine/scripts/ship_gate.py \
  engine/output/regen/product_r1/MyMincho-product_r1-Regular.otf \
  --glyphset <glyphset.txt>
```

## 種別の読み替え

| タスク種別 | このリポジトリでの意味 |
|---|---|
| `[FEAT]` | 新字・DSL拡張・エンジン経路（curve_refit / winding / loop_closure） |
| `[FIX]` | ゲート赤・穴破壊・フィット超過・黄金 DIFF |
| `[SEC]` | ライセンス・トレース禁止（掟9）・秘密情報・計測経路の偽科学 |
| `[DOCS]` | PLAN / weekly / 各計画書 / 黄金マニフェスト |

## /ship の読み替え

1. pytest 全緑
2. 仮名なら `kana_gate` ＋ `--compare-golden` MATCH
3. `ship_gate` の outline_sample ok
4. 黄金更新はバージョン付き（掟18）。コミットはユーザー指示があるときだけ

## /chaos の読み替え

LLM 障害注入の代わりに、フォント固有の破壊実験を最低3つ:

1. 穴字（口・の）でカウンターが黒塗りにならない
2. `cubic_fit` ゲート超過で fail-closed（黙って折れ線化しない）
3. QUAD/CUBIC が `extract_contours_xy` で潰されず raise

## /tdd の読み替え

テストは `engine/tests/test_*.py`。先に失敗する pytest を書き、最小実装、回帰全緑。TypeScript 例は無視。

## /docs-sync の読み替え

更新候補: `docs/weekly.md`、触った計画書、`PLAN.md` の該当節、黄金マニフェスト。英語 README 同期は不要。
