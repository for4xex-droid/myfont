# アルファベット書体の自動生成 先行研究の調査と採否

2026-09-29 調査。論文とリポジトリを調べ、`docs/latin_impl_plan.md` へ何を取り込むかを決めた記録。
調査はサブエージェント（Grok 4.7）2本で行い、ライセンスと URL は本体側で GitHub API と HTTP 取得で照合した。

正本の優先順は変えない: `docs/生成書体の仕様.md` ＞ `GOLDENRULES.md` ＞ `docs/latin_impl_plan.md` ＞ 本書。
本書は仕様の未決定項目（太さの数・命名・収録追加）を一切決めない。

---

## 0. 結論（計画への反映は5点）

1. **骨格の書き方**: 制御点を直接書く cubic 列をやめ、Hobby（1985）の節点＋張力と、Spiro（Levien 2009）の節点型（smooth / corner / line）で書く。内部の正本は、展開後の cubic 列とそのハッシュにする
2. **パラメータの層**: Hu & Hersch（2001）の3層（全体 → 役割グループ → 字ごとの上書き）にする。字ごとの自由スカラー ≤12 の上限は据え置く
3. **端物と接合**: セリフ・頂点・ボールはペンで掃かずに「塗りの部品」として置き、union で結合する（Romer 2012、FlexyFont）。ストロークごとに自己重なりを先に解消してから、字全体の union をかける（Farouki & Neff 1990 の尖点の扱い）
4. **曲線と輪郭の決定性**: 既存の Schneider 型フィットは使い続ける。節点の上限を超えたときだけ、Plass & Stone（1983）の動的計画法で区間数を最小化する。輪郭の開始点と向きを固定し、差分とハッシュを安定させる（VecFusion の観察）
5. **字間**: Tracy 法（H を基準にし、O は HHOHH で決め、側面を5段で分類）を正本にする。面積法（HT Letterspacer の文書に書かれた方法）は照合用の第2測定として自作する。GPL のコードは読まない・写さない

深層学習による生成（DeepVecFont 系、Im2Vec、SVGFormer など）は採らない。37字×4様式の規模では学習データの権利と再現性の負担が大きく、輪郭を直接出す必要もない。ベクター表現の知見（直線コマンドの分離、角での点の重複）だけを借りる。

---

## 1. 論文（出典は [Latin font generation papers](ce63232b-26db-48b0-8a9c-1686e3545342)）

| 文献 | 要点 | 採否 | 反映先 |
|---|---|---|---|
| Hobby, *Smooth, Easy to Compute Interpolating Splines*, 1985 ([PDF](http://i.stanford.edu/pub/cstr/reports/cs/tr/85/1047/CS-TR-85-1047.pdf)) | 節点・張力・curl から滑らかな cubic を決める。METAFONT の曲線 | **採用** | 計画 §4.1 骨格 DSL、工程 2 |
| Levien, *From Spiral to Spline*（博士論文）, 2009 ([PDF](http://www.levien.com/phd/thesis.pdf)) | 節点型（smooth/corner/line）で書体を設計する流儀 | **型の語彙だけ採用**。libspiro（GPL）は使わない | §4.1 |
| Levien, *Fitting cubic Bézier curves*, 2021 ([blog](https://raphlinus.github.io/curves/2021/03/11/bezier-fitting.html)) | ウェイトごとの独立フィットは補間互換にならない | **既存判断の裏付け**（§2.4 の直接生成） | §2.4 |
| Hu & Hersch, 2001（EPFL, [頁](https://lspwww.epfl.ch/publications/typography/pfbosc.html)） | 全体・グループ・字ごとの3層パラメータ。様式を離散スイッチで切り替える | **採用** | §4.2 |
| Shamir & Rappoport, 1998 | 部品間の距離と比を名前付きの制約で持つ | **名前付き比の考え方だけ採用**（ソルバは作らない） | §4.2 |
| Jakubiak, Perry, Frisken, 2006（MERL [TR2006-119](https://www.merl.com/publications/docs/TR2006-119.pdf)） | 中心線＋法線方向の幅プロファイル＋共有の端部品 | **採用**（計画の構造と一致。端部品を共有オブジェクトにする） | §3 `terminals.py` |
| Romer, TUGboat 33:3, 2012 ([PDF](https://www.tug.org/TUGboat/tb33-3/tb105romer.pdf)) | セリフ・頂点はペンの掃引の外で塗りとして作る。曲率半径より大きいペンは使わない | **採用** | §2.5、G-K |
| Phan ほか, FlexyFont, 2015 | 部品（端・接合）の差し替えで様式を作る | **採用**（端物テンプレの差し替え＝様式） | §4.2 `terminals` |
| Farouki & Neff, 1990 | オフセットは \|κ\|·半幅 ≥ 1 で尖点と自己交差ができる | **採用**: ストローク単位の自己重なり解消を先に行う。G-K は fail のまま残す | §2.5、G-K |
| Balashova ほか, 2019 | セリフ・ボールを離散スイッチとし、部品 ID を字間で共有 | **採用**（`ends` 語彙と様式の対応表がこれに当たる） | §4.1 |
| Plass & Stone, 1983 ([PDF](https://lhf.impa.br/cursos/tmg/Plass-Stone-1983.pdf)) | 誤差の上限の下で区間数を最小にする動的計画法 | **条件付き採用**（節点の上限を超えたときだけ） | §2.5、工程 5 |
| Schneider, *Graphics Gems*, 1990 ([PDF](https://lhf.impa.br/cursos/tmg/Schneider-1990.pdf)) | ニュートン法の再パラメータ化と、最大誤差点での分割 | **既存**（`curve_fit._reparam_newton` が該当）。変更しない | — |
| DeepVecFont-v2, 2023 | 補助サンプル点で誤差を測ると、曲線の中間が暴れない | **採用**: G-F の誤差を節点だけでなく密サンプルで両方向に測る | G-F |
| DeepSVG, 2020 | 直線と曲線を別コマンドにする | **採用**（直線スナップ後は line として書き出す） | G-L |
| VecFusion, 2024 | 角のオンカーブ点の重複、輪郭の開始点の固定 | **開始点の固定を採用**（重複点は作らない） | 新 G-ORD |
| de Mello Vargas, 2007（Tracy 法の解説, [PDF](https://typeculture.com/wp-content/uploads/2016/02/tc_article_49.pdf)） | H を基準、HHOHH で O、側面を5段で分類 | **採用** | §4.3、工程 10 |
| kernagic の考え方（リズム点の間隔） | 縦ステムの間隔を揃える | **考え方だけ採用**（コードは GPL で読まない） | 工程 10 の検査 |
| O'Donovan ほか, 2014 ([PDF](https://www.dgp.toronto.edu/~donovan/font/fontSelection.pdf)) | 書体の印象語（formal, friendly など）で人の評価を取る | **採用**: 盲検に印象語の設問を足す | 工程 13 |
| Campbell & Kautz, 2014 | 書体の潜在空間 | **軸の独立性の確認にだけ使う**（生成には使わない） | §6.3 |
| Suveeranont & Igarashi, EasyFont, DeepVecFont（画像精細化）, Im2Vec | 例示・画像からの生成 | **不採用**。参照の輪郭を写す経路になりうる（掟9）。再現性がない | — |
| Kindersley の4次モーメント法 | 字間を慣性モーメントで決める | **不採用**（原典未確認。Tracy 法で足りる） | — |

未確認（原典を読めていない。計画の根拠には使わない）: SVGFormer、Tracy の原著 *Letters of Credit*、Kindersley の原著、Elber & Cohen 1991。

---

## 2. リポジトリ（出典は [Latin font tool repos](e069c2f1-6b5a-4f99-a3e3-3aa618a924d8)）

ライセンスは 2026-09-29 に GitHub API で照合した。

| リポジトリ | ライセンス | 扱い | 理由 |
|---|---|---|---|
| fontmake / ufo2ft / fontTools / ufoLib2 / skia-pathops | BSD・MIT・Apache 系 | **依存として継続**（既に engine/.venv にある） | 既存の経路。ufo2ft の kernFeatureWriter で kerning を GPOS にする |
| linebender/kurbo | Apache-2.0 | **アルゴリズムを読むだけ**（stroke、fit）。依存にしない | Rust。撤退ライン（解析オフセット）の参考 |
| fontPens | BSD | 必要なら依存に足す（面積・重心の計測ペン） | 面積法の測定に使える |
| simoncozens/Outliner | **LICENSE なし** | 使わない・読まない | 権利が不明 |
| HT Letterspacer | GPL-3.0（コード）。文書は CC BY 4.0 | **文書から面積法を自作**し、出典を明記する。コードは読まない | GPL を持ち込まない |
| Kernagic | GPL-3.0 | 使わない。リズムの検査は実装計画 §4.3 の定義（縦ステム間隔の変動係数）で、Kernagic のコードも README も出典にしない | 計画 §4.3 |
| Metapolator、libspiro、prototypo.js | GPL | 使わない | 同上 |
| Metaflop | GPL（README に「生成フォントも GPL」） | 使わない | 生成物のライセンスが縛られる |
| Prototypo | MPL-2.0 | 使わない | ファイル単位の copyleft。混ぜない |
| drawbot-skia | Apache-2.0 | **候補**: 比較シートの描画（工程 6） | Pillow で足りれば入れない |
| diffenator2 | Apache-2.0 | **候補**: 版ごとの差分表（工程 7 以降） | 別 venv で試す。engine/.venv の依存にはしない |
| gftools（HTML 組見本） | Apache-2.0 | 候補 | 組見本の既定は `hb-view` のまま |
| fontbakery | Apache-2.0 | 検査だけ（既存の G-SHIP） | — |
| ttfautohint | GPL/FreeType 系 | 使わない（ヒンティングなし。`ship_gate_rules.md` に明記する） | 表示用途。バイナリを同梱しない |
| atokern（ニューラルネットの kerning） | — | 参考だけ | 学習の権利と再現性 |

**方針**: engine の依存は permissive（MIT・BSD・Apache・OFL）だけにする。GPL・MPL のコードは vendoring しない・写さない・読みながら書かない。考え方を使うときは、論文か CC BY の文書を出典として本書に書く。

---

## 3. 計画に入れなかったもの（理由付き）

- **学習ベースの生成**: 権利（掟9・掟12）、再現性（G-R）、規模（148字）の3点で合わない
- **METAFONT/Metapost そのものを使う**: 出力のラスタ前提、ペン掃引の輪郭化の品質、依存の重さ。Hobby の曲線だけを Python で実装する。解くのは節点ごとの接線角で、隣接3節点にしか依存しない三重対角の線形方程式になる（式は1本ではない）
- **マスター補間・可変フォント**: 仕様の納品物は静的な OTF/TTF。§2.4 のとおり
- **自動カーニングの全面採用**: 自動は候補の提示まで。値は作者が採る（計画 §4.3 のまま）
