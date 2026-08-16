# MyMincho ワークフロー

日常の作業を3つのループに分けて定義する。各ループは「トリガー → 手順 → 検収基準 → 成果物の置き場所」で構成。
コマンドはリポジトリ整備後の目標形（パスは実装時に確定）。すべての作業で `GOLDENRULES.md` を優先する。

```
①計測ループ ──(実測比・snapshot)──► ②エンジンループ の params
②エンジンループ ──(OTF/UFO)──► ①へ ingest（同一物差しで自作を再計測）
③字形制作ループ ──(手設計UFO)──► ②へマージ（manual_glyphs で上書き禁止）
③で見つけた違和感 ──► ①新probe or ②接合バグ修正 or ③再描画 に振り分け
```

---

## ① fontdb 計測ループ

**トリガー**
- 新しい face（書体・ウェイト・自作snapshot）の追加
- extractor_version のバンプ（計測数式・ROI・閾値の変更）
- render_profile の追加・変更
- 隔週レビューでの校正見直し

**手順**
```bash
cd fontdb
source .venv/bin/activate                      # 初回: python3 -m venv .venv && pip install -e ".[dev]"
python scripts/01_fetch.py                     # SHA256 を corpus.yaml と突合
python scripts/02_init_db.py                   # 冪等
python scripts/03_render.py --profile ft_1024_nohint_gray_v1 --faces all
python scripts/04_glyph_metrics.py
python scripts/05_probes.py --probes juu_contrast,san_uroko
python scripts/06_ingest_prototype.py --params classic,modern \
       --route tempfont                         # 第一候補: union→一時OTF化→freetype計測（spike3実証済み）
       # union前の暫定値が要る場合のみ --route poly（別profile。掟4）
python scripts/07_viz_scatter.py -o output/scatters/
pytest tests/
```

**検収基準**
- 5 face × 代表字が `glyph_metric.status=ok`（欠字は missing として明示）
- probe: 合成 fixture テスト緑。実書体の fail 率が `probe_defs.yaml` の上限以下
- 散布図に family＋render_profile の凡例。**profile 混在の平均・回帰が無いこと**（掟3）
- SHA256 不一致ゼロ

**成果物**
- DB: `fontdb/data/db/fontdb.sqlite`
- 図: `fontdb/output/scatters/`
- プロトコル文書: `docs/measurement_protocol.md`（profile 間差異の記録を含む）

---

## ② エンジン開発ループ

**トリガー**
- 接合バグ・回帰20字の赤
- 新しい StrokeKind / 接続タイプの追加
- params 変更後の輪郭破綻
- fontmake ビルド失敗

**手順**
```bash
# 1. 目視確認（十・永）。engine/generate.py は無い。--glyphs は空白区切り。
engine/.venv/bin/python engine/scripts/regen.py --params product_r1 --glyphs juu ei
# 出力: engine/output/regen/product_r1/

# 2. コード変更（strokes / join / skeletons）

# 3. 回帰テスト（着手前に regression_join20.yaml が存在すること。掟14）
engine/.venv/bin/python -m pytest engine/tests/test_regression_join.py -q

# 4. エンジンUFOは dest 以外へ出す（掟13）。出荷へ足すときだけマージ。
engine/.venv/bin/python engine/scripts/regen.py --params product_r1 --glyphs shi
engine/.venv/bin/python scripts/merge_engine_ufo.py \
  --engine engine/output/regen/product_r1/MyMincho-product_r1.ufo \
  --dest fonts_out/MyMincho.ufo
engine/.venv/bin/python scripts/compile_manual_otf.py

# 5. 検証
fontbakery check-universal fonts_out/build/*.otf   # サブセットでよい
engine/.venv/bin/python scripts/check_manual_overwrite.py --ufo fonts_out/MyMincho.ufo

# 6. params を変えた場合は snapshot 登録 → ループ①へ
```

**検収基準**
- 回帰20字で交差破綻ゼロ、自己交差・開放パスゼロ
- 「永」「十」が期待どおりの contour 数
- manual_glyphs との差分ゼロ
- OTF ビルド成功＋FontBakery サブセット通過
- 撤退ライン監視: 手動例外が5字を超えたらアルゴリズム変更を止めて設計レビュー（PLAN §3.3）

**成果物**
- 骨格JSON: `engine/skeletons/`（フォント空間・Y上。掟1）
- params＋snapshot: `engine/params/` → DB の `design_param_snapshot`
- UFO: `fonts_out/*.ufo`（git管理）、OTF: `fonts_out/build/`（gitignore）
- 回帰定義: `tests/regression_join20.yaml`

---

## ③ 字形制作・校正ループ

**トリガー**
- 新規手設計字（仮名・基準漢字）
- 組見本での違和感の発見
- 黒み密度レポートのトップN
- KAGE 層C（頻出字手修正）への昇格
- マイルストーン毎の再読

**手順**
```bash
# 1. ラフ（紙/iPad）→ Glyphs で清書
# 2. 作業 UFO を正本へ（描済み dest は消さない）
engine/.venv/bin/python scripts/merge_manual_kana.py う
# 3. グリフ名を fonts_out/manual_glyphs.txt に追加（掟13）
# 3b. 字間帯（輪郭は動かさず平行移動＋幅）
engine/.venv/bin/python scripts/set_manual_sidebearings.py --out-of-band

# 4. ビルド＋組見本（組見本の本体は uharfbuzz / hb-view を流用。自作は薄いラッパのみ）
engine/.venv/bin/python scripts/compile_manual_otf.py
engine/.venv/bin/python scripts/make_proofs.py --font fonts_out/build/MyMincho.otf --out proofs/out
#    仮名だけの G3 は proofs/golden/g3_kana/（あい／あと／核心20）
#    → 内部で uharfbuzz / hb-view を呼ぶ（spike3で動作実証済み）
#    → diffenator2 は Python 3.14 で失敗実績あり。使うなら 3.12 系の別 venv で
#    → 仮名本文（青空文庫固定文面）/ 漢字交じり / ストレス字羅列 の3種

# 5. 黒みは fontdb/scripts/05_probes.py。重ね塗り字は掟5で low_confidence。
#    scripts/density_report.py は無い。

# 6. 手設計字からうろこ角度・打ち込み深さを逆計測 → params 更新 → ループ①②へ

# 7. 隔週: docs/weekly.md に3行だけ記録
#    「M1デモ可能日 / M2デモ可能日 / 今週の一手」
```

**検収基準**
- P1 の設計順序（ひらがな核心 → 残り → カタカナ → 約物 → 英数 → 基準漢字）を守っている
- 固定文面の組見本で「歩行」チェックリスト合格。`proofs/golden/` の凍結版と比較
- 対象文字セット（`data/glyphset_*.txt`）基準で欠字ゼロ
- 密度例外が `data/density_exceptions.yaml` の閾値以下
- エンジン再実行後も手設計字のアウトラインが一致（掟13の実地確認）

**成果物**
- 手設計ソース: Glyphs ファイル＋ UFO 正本（`fonts_out/MyMincho.ufo`）
- 組見本: `proofs/`（凍結版は `proofs/golden/`）
- 例外リスト: `data/density_exceptions.yaml`
- 週次ログ: `docs/weekly.md`

---

## 違和感トリアージ（ループ③ → どこに戻すか）

| 症状 | 戻し先 |
|---|---|
| 特定の字だけ形が変（接合・輪郭の破綻） | ② 接合バグとして回帰セットに追加 |
| 書体全体の印象がズレる（太い・うろこが主張しすぎ等） | ① 計測して params を再校正 → ② |
| 仮名のリズム・歩行が悪い | ③ 再描画（エンジンより優先。掟20） |
| 特定漢字の骨格が不自然 | ③ KAGE 層C 昇格（頻出）または層D許容（低頻度） |
| 数値上は正常なのに違和感 | ① 新しい probe の候補としてメモ（すぐ実装しない） |
