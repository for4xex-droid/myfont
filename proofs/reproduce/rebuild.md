# ステム＋端物テンプレ再構成

開いた接合を閉じ、打ち込みは三角で戻す。はらいと端物の残差は二次を潰さない。正本は書いていない。

| 字 | stems IoU | templates IoU | 画素 IoU | 接合 | テンプレ |
|---|---:|---:|---:|---:|---|
| 十 | 0.835 | 1.000 | 0.962 | 1 | bar_uroko,top_cap,uchikomi |
| 二 | 0.669 | 1.000 | 1.000 | 0 | bar_uroko,bar_uroko,uchikomi,uchikomi |
| 三 | 0.646 | 1.000 | 1.000 | 0 | bar_uroko,bar_uroko,bar_uroko,uchikomi,uchikomi,uchikomi |
| 口 | 0.932 | 1.000 | 1.000 | 2 | box_uroko,top_cap |
| 日 | 0.939 | 1.000 | 0.998 | 2 | box_uroko,top_cap |
| 田 | 0.957 | 1.000 | 0.947 | 6 | box_uroko,top_cap |
| 中 | 0.906 | 1.000 | 0.976 | 2 | box_uroko,top_cap,top_cap |
| 永 | 0.277 | 1.000 | 0.978 | 0 | right_hara,left_hara,ten,hane,uchikomi,uchikomi |
| 八 | 0.055 | 1.000 | 1.000 | 0 | right_hara,left_hara,uchikomi |
| 人 | 0.000 | 1.000 | 1.000 | 0 | hara_pair |
| 入 | 0.073 | 1.000 | 1.000 | 0 | hara_pair,uchikomi,roof_shoulder |
| 木 | 0.471 | 1.000 | 1.000 | 0 | hara_pair,bar_uroko,top_cap,uchikomi |
| 本 | 0.460 | 1.000 | 1.000 | 0 | hara_pair,other,bar_uroko,top_cap,uchikomi,uchikomi |
| 大 | 0.267 | 1.000 | 1.000 | 0 | hara_pair,bar_uroko,top_cap,uchikomi |
| 天 | 0.335 | 1.000 | 0.981 | 1 | hara_pair,bar_uroko,bar_uroko,uchikomi,uchikomi |
| 又 | 0.082 | 1.000 | 1.000 | 0 | hara_pair |
| 文 | 0.144 | 1.000 | 1.000 | 0 | hara_pair,top_cap,uchikomi |
| 火 | 0.064 | 1.000 | 0.996 | 0 | hara_pair,hane,hane,top_cap |
| 矢 | 0.296 | 0.999 | 0.995 | 1 | hara_pair,left_hara,bar_uroko,bar_uroko,uchikomi |
| 川 | 0.705 | 1.000 | 0.982 | 0 | left_hara,top_cap,top_cap,top_cap |
| 水 | 0.255 | 1.000 | 1.000 | 0 | right_hara,left_hara,hane,uchikomi |
| 手 | 0.529 | 1.000 | 1.000 | 2 | top_cap,hane,bar_uroko,bar_uroko,uchikomi,uchikomi |
| 上 | 0.752 | 1.000 | 1.000 | 2 | bar_uroko,bar_uroko,top_cap,uchikomi |
| 土 | 0.786 | 1.000 | 0.974 | 2 | bar_uroko,bar_uroko,top_cap,uchikomi,uchikomi |
| 王 | 0.777 | 1.000 | 0.980 | 3 | bar_uroko,bar_uroko,bar_uroko,uchikomi,uchikomi,uchikomi |
| 玉 | 0.706 | 1.000 | 1.000 | 3 | other,bar_uroko,bar_uroko,bar_uroko,uchikomi,uchikomi,uchikomi |
| 力 | 0.221 | 1.000 | 0.991 | 0 | right_hara,left_hara,top_cap,uchikomi |
| 刀 | 0.172 | 1.000 | 0.999 | 0 | left_hara,right_hara,ten,uchikomi |
| 月 | 0.680 | 1.000 | 0.989 | 3 | left_hara,hane,box_uroko,top_cap |
| 用 | 0.785 | 1.000 | 0.981 | 6 | hane,hane,box_uroko,top_cap |
| 小 | 0.341 | 1.000 | 0.999 | 0 | right_hara,left_hara,hane,top_cap |
| 心 | 0.218 | 1.000 | 1.000 | 0 | other,other,left_hara,other,top_cap |
| 少 | 0.200 | 1.000 | 0.999 | 0 | hara_pair,left_hara,other,hane,top_cap |
| 耳 | 0.709 | 0.999 | 0.975 | 4 | other,bar_uroko |
| 言 | 0.736 | 1.000 | 1.000 | 0 | bar_uroko,bar_uroko,bar_uroko,bar_uroko,box_uroko,top_cap,uchikomi,uchikomi,uchikomi,uchikomi |
| 古 | 0.843 | 1.000 | 0.973 | 2 | bar_uroko,box_uroko,top_cap,top_cap,uchikomi |
| 石 | 0.635 | 1.000 | 1.000 | 0 | left_hara,bar_uroko,box_uroko,uchikomi |
| 見 | 0.532 | 1.000 | 0.991 | 4 | hara_pair,other,box_uroko,top_cap |
| 雨 | 0.682 | 1.000 | 0.977 | 2 | hane,other,other,other,other,bar_uroko,box_uroko,top_cap,uchikomi |
| 食 | 0.228 | 1.000 | 0.982 | 0 | hara_pair,bar_uroko,hane |
| 国 | 0.817 | 0.994 | 0.982 | 1 | top_cap,other,other,box_uroko,bar_uroko,top_cap,uchikomi,uchikomi,uchikomi |
| 車 | 0.843 | 1.000 | 0.977 | 5 | box_uroko,bar_uroko,bar_uroko,bar_uroko,top_cap,uchikomi,uchikomi |
| 金 | 0.341 | 1.000 | 1.000 | 2 | hara_pair,top_cap,bar_uroko,hane,bar_uroko,bar_uroko,uchikomi,uchikomi |
| 風 | 0.291 | 1.000 | 0.994 | 0 | right_hara,hane,left_hara,top_cap,hane,top_cap,top_cap |
| 東 | 0.679 | 1.000 | 0.999 | 3 | hara_pair,box_uroko,bar_uroko,bar_uroko,top_cap,uchikomi |
| 花 | 0.396 | 1.000 | 0.977 | 0 | other,other,bar_uroko,other,bar_uroko,top_cap,uchikomi |
