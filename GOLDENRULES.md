# MyMincho ゴールデンルール

このプロジェクト（自作明朝体＋フォント要素DB）固有の鉄の掟。
一般的なコーディング規約ではなく、**違反すると計測・校正・ライセンスが壊れるもの**だけを載せる。
各ルールに「違反時に壊れるもの」を明記。実装・レビュー時は必ずここに照らす。

## 技術スタック

- Python 3.11+（fontdb: freetype-py / numpy / Pillow / fontTools / matplotlib）
- エンジン（P2以降）: skia-pathops（`pyproject` の `engine` グループに分離）
- ビルド: UFO ＋ fontmake。手設計は Glyphs → UFO エクスポート
- DB: SQLite 単体
- pytest（合成fixture＋黄金画像diff）

---

## 鉄の掟（Iron Principles）

### A. 座標と単位

#### 1. 内部座標は「フォント空間: Y上向き・UPM=1000」に統一。SVG出力時のみY反転
```python
# ❌ 禁止: SVG座標(Y下)のまま骨格JSONやDBに保存
skeleton = {"start": (100, 120)}  # これはSVGのY下座標？フォント座標？不明

# ✅ 骨格・params・DB・UFOは常にフォント空間。変換はSVG書き出しの1箇所だけ
def to_svg_y(y_font: float, upm: int = 1000) -> float:
    return upm - y_font
```
**違反時**: うろこROI・重心Y・UFO出力が系統的に裏返り、全計測が静かに壊れる。

#### 2. 計測値は必ずEM正規化してからDBに入れる。px生値をカラムに保存しない
```python
# ❌ 禁止
row["v_thickness"] = run_length_px          # 1024px/EM前提が暗黙

# ✅ EM正規化。px値はdetails_json（デバッグ用）まで
row["v_thickness_em"] = run_length_px / px_per_em
```
**違反時**: `px_per_em` を変えた瞬間に過去データと比較不能になる。

### B. 計測の再現性

#### 3. `render_profile_id` と `extractor_version` が異なる数値を、注記なしで同じグラフ・同じ平均に載せない
**違反時**: 偽の書体差・偽の収束をパラメータ決定に使ってしまう（校正が逆方向に振れる）。

#### 4. synthetic（自作合成面）を freetype profile のフリをして登録しない
外部書体は freetype、接合前の自作はポリゴン直描画。経路が違うものは profile を分ける（`poly_pillow_*`）。同じ物差しに載せたければ一時フォント化して freetype に通す。
**違反時**: classic/modern と源ノ明朝の比較がニセ科学になる。

#### 5. 接合（union）前の重ねポリゴンで、黒み密度・ふところ（穴）系 probe を `ok` にしない
重ね塗りは黒みが二重カウントされ、穴のトポロジが偽になる。接合前は `low_confidence` 固定。
**違反時**: 自作だけ黒み・穴面積が壊れ、うろこ・太さの初期値校正が誤る。

#### 6. probe の失敗と「様式的ゼロ」を混同しない
うろこが無い書体は value=0＋`ok`。検出できなかったら `fail`/`low_confidence`。
**違反時**: モダン明朝の小ぶりなうろこを欠損扱いし、uroko パラメータが過大側に漂移する。

#### 7. probe ROI・代表字セット・閾値をコードにハードコードしない。`config/probe_defs.yaml` を正とする
**違反時**: 「三→二フォールバック」等のプロトコル変更が再現不能になり、extractor_version 管理が無意味化。

#### 8. 計測数式・ROI・二値化閾値を変えたら必ず extractor_version を上げる
**違反時**: 旧定義の数値と新定義の数値が同一版として混ざり、DB全体が汚染される。

#### 8b. 可変フォントは wght を明示してインスタンス化してから計測する。デフォルトインスタンスを信用しない
スパイクで Noto Serif JP のデフォルトが ExtraLight(200) である事故を確認済み。face レコードには必ず可変軸座標を記録する。
**違反時**: Regular のつもりで ExtraLight を測り、コントラスト・太さの校正値が全部ずれる。

### C. ライセンス（絶対）

#### 9. 参照書体のアウトライン座標・部品パスをコード・JSON・UFOにコピーしない。取得するのは計測スカラーと派生比のみ
**違反時**: ライセンス侵害。プロジェクトの成果物全体が公開不能になる。

#### 10. フォントバイナリを git に入れない。URL＋SHA256 のみを正とする
**違反時**: 再配布事故。`data/fonts/` は gitignore、取得は `01_fetch` スクリプト経由のみ。

#### 11. KanjiVG（CC BY-SA）の形状を成果物アウトラインに混入させない。筆順・部品分割の参照のみ
**違反時**: CC BY-SA が成果物に伝染し、ライセンス選択の自由を失う。

#### 12. コーパス追加はライセンス条文確認を corpus.yaml エントリの完了条件にする。「有名だから」で追加しない
**違反時**: 計測資産全体の汚染。1書体の混入で全比較データが要監査になる。

#### 12b. GPL コード（kage-engine 本家・Python ポート）をリンク・移植しない。GlyphWiki のダンプデータのみ利用する
**違反時**: 成果物フォント・エンジン全体のライセンス選択の自由を失う。

### D. フォント制作パイプライン

#### 13. 手設計グリフ（`manual_glyphs.txt`）をエンジンが上書きするパスを、マージ前にツールで拒否する
```python
# ✅ UFO書き込み前に必ずチェック
if glyph_name in manual_glyphs:
    raise RefusedOverwrite(glyph_name)  # 例外でビルドを止めてよい（境界チェック）
```
**違反時**: 書体の核（仮名）がバッチ生成で消え、M1の成果が巻き戻る。

#### 14. P2 の回帰20字（`tests/regression_join20.yaml`）がグリーンになるまで量産（P5)を開始しない
**違反時**: 2,000字分の接合破綻を量産し、修正コストが文字数倍になる。

#### 15. 塗り重ねSVGを「OTF相当」とみなさない。製品経路は必ず union（単一輪郭化）を通す
**違反時**: 重なり輪郭でバリデータ・ヒント処理・黒み計測が全部破綻する。

#### 16. MinchoParams の変更は必ず snapshot として face に紐付ける。無名の「最新params」でDBを上書きしない
**違反時**: 散布図上の自作点がどの世代か分からなくなり、校正の履歴が消える。

#### 17. KAGE由来骨格には変換パイプラインID・**解決後のグリフ名・ダンプのSHA256**を必ず残す
alias（`uXXXX`→`uXXXX-j`）解決後の名前で記録する。表面名だけだと再現できない。
**違反時**: 品位問題が「骨格が悪い」のか「変換が悪い」のか切り分け不能になる。

#### 17b. 未展開の部品参照（KAGE筆画タイプ99）を製品骨格に持ち込まない。骨格JSONは常に展開済み・フラットなストローク列とする
常用漢字の86.8%が再帰展開（深度max=5）を必要とすることが実測済み。展開はP4a変換器の責務で、エンジンは展開済みデータだけを受け取る。
**違反時**: エンジン側に部品解決ロジックが漏れ、骨格の正本が二重化する。

#### 18. 回帰の期待結果（黄金画像・contour数・輪郭ハッシュ・組見本）は黄金ファイル化し、更新はバージョン付きコミットで行う
**違反時**: 「良くなった気がする」の主観回帰で M2/M5 が永遠に閉じない。

#### 19. 文字セットの変更（スコープ撤退含む）は `data/glyphset_*.txt` の明示コミットとして行う
**違反時**: 欠字・cmap・公開文言が不一致のまま出荷候補になる。

#### 20. 仮名が弱いと判断したら、エンジン開発より P1（仮名）に回帰する。例外リスト増で誤魔化さない
**違反時**: 漢字を量産しても「この書体」にならず、時間だけが溶ける。

---

## ファイル配置ルール

| 種別 | 場所 | 備考 |
|---|---|---|
| 計測コード | `fontdb/src/fontdb/` | acquire/render/metrics/probes/ingest/viz/bridge |
| 計測プロトコル定義 | `fontdb/config/*.yaml` | コードにハードコード禁止（掟7） |
| DB | `fontdb/data/db/fontdb.sqlite` | |
| 外部フォント | `fontdb/data/fonts/` | gitignore（掟10） |
| エンジン | `engine/` | prototypeから移行。skia-pathopsはここだけ |
| 骨格JSON | `engine/skeletons/` | フォント空間・Y上（掟1） |
| UFO正本 | `fonts_out/*.ufo` | git管理。OTFは`fonts_out/build/`（gitignore） |
| 手設計保護リスト | `fonts_out/manual_glyphs.txt` | 掟13 |
| 回帰定義 | `tests/regression_join20.yaml` ほか | 掟14・18 |
| 組見本 | `proofs/`（凍結版は`proofs/golden/`） | |
| 文字セット | `data/glyphset_*.txt` | 掟19 |
| 実験場 | `prototype/` | 正本にしない。標準ライブラリのみ維持 |

## 命名規則

| 種別 | 規則 | 例 |
|---|---|---|
| render_profile_id | `経路_解像度_hint_aa_版` | `ft_1024_nohint_gray_v1` |
| extractor_version | semver | `0.2.0` |
| probe_id | `字ローマ字_部位` | `juu_contrast`, `san_uroko` |
| params snapshot | `名前_r連番` | `classic_r2`, `product_r1` |
| fontdb第2期タスク | `B番号`（トラックAのP番号と衝突させない） | `B1`, `B2` |
