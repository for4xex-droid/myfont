# ステム＋端物テンプレ再構成

開いた接合を閉じ、打ち込みは三角で戻す。copy は残差の二次を戻す。scalar は計測比のテンプレだけ。正本は書いていない。

| 字 | stems IoU | templates IoU | 画素 IoU | 接合 | テンプレ |
|---|---:|---:|---:|---:|---|
| 十 | 0.835 | 0.988 | 0.951 | 1 | bar_uroko,top_cap,uchikomi |
| 二 | 0.669 | 0.986 | 0.989 | 0 | bar_uroko,bar_uroko,uchikomi,uchikomi |
| 三 | 0.646 | 0.985 | 0.985 | 0 | bar_uroko,bar_uroko,bar_uroko,uchikomi,uchikomi,uchikomi |
| 口 | 0.932 | 0.986 | 0.987 | 2 | box_uroko,top_cap |
| 日 | 0.939 | 0.988 | 0.985 | 2 | box_uroko,top_cap |
| 田 | 0.957 | 0.992 | 0.940 | 6 | box_uroko,top_cap |
| 中 | 0.906 | 0.984 | 0.961 | 2 | box_uroko,top_cap,top_cap |
| 永 | 0.277 | 0.973 | 0.954 | 0 | right_hara,left_hara,ten,hane,uchikomi,uchikomi |
| 八 | 0.055 | 0.967 | 0.973 | 0 | right_hara,left_hara,uchikomi |
| 人 | 0.000 | 0.961 | 0.965 | 0 | hara_pair |
| 入 | 0.073 | 0.962 | 0.969 | 0 | hara_pair,uchikomi,roof_shoulder |
| 木 | 0.471 | 0.982 | 0.987 | 0 | hara_pair,bar_uroko,top_cap,uchikomi |
| 本 | 0.460 | 0.980 | 0.981 | 0 | hara_pair,other,bar_uroko,top_cap,uchikomi,uchikomi |
| 大 | 0.267 | 0.947 | 0.953 | 0 | hara_pair,bar_uroko,top_cap,uchikomi |
| 天 | 0.335 | 0.959 | 0.943 | 1 | hara_pair,bar_uroko,bar_uroko,uchikomi,uchikomi |
| 又 | 0.082 | 0.911 | 0.914 | 0 | hara_pair |
| 文 | 0.144 | 0.892 | 0.895 | 0 | hara_pair,top_cap,uchikomi |
| 火 | 0.064 | 0.952 | 0.953 | 0 | hara_pair,hane,hane,top_cap |
| 矢 | 0.296 | 0.968 | 0.969 | 1 | hara_pair,left_hara,bar_uroko,bar_uroko,uchikomi |
| 川 | 0.705 | 0.979 | 0.960 | 0 | left_hara,top_cap,top_cap,top_cap |
| 水 | 0.255 | 0.961 | 0.966 | 0 | right_hara,left_hara,hane,uchikomi |
| 手 | 0.529 | 0.821 | 0.826 | 2 | top_cap,hane,bar_uroko,bar_uroko,uchikomi,uchikomi |
| 上 | 0.752 | 0.982 | 0.985 | 2 | bar_uroko,bar_uroko,top_cap,uchikomi |
| 土 | 0.786 | 0.985 | 0.961 | 2 | bar_uroko,bar_uroko,top_cap,uchikomi,uchikomi |
| 王 | 0.777 | 0.989 | 0.970 | 3 | bar_uroko,bar_uroko,bar_uroko,uchikomi,uchikomi,uchikomi |
| 玉 | 0.706 | 0.990 | 0.990 | 3 | other,bar_uroko,bar_uroko,bar_uroko,uchikomi,uchikomi,uchikomi |
| 力 | 0.221 | 0.971 | 0.964 | 0 | right_hara,left_hara,top_cap,uchikomi |
| 刀 | 0.172 | 0.978 | 0.977 | 0 | left_hara,right_hara,ten,uchikomi |
| 月 | 0.680 | 0.986 | 0.975 | 3 | left_hara,hane,box_uroko,top_cap |
| 用 | 0.785 | 0.990 | 0.971 | 6 | hane,hane,box_uroko,top_cap |
| 小 | 0.341 | 0.984 | 0.984 | 0 | right_hara,left_hara,hane,top_cap |
| 心 | 0.218 | 0.980 | 0.984 | 0 | other,other,left_hara,other,top_cap |
| 少 | 0.200 | 0.976 | 0.978 | 0 | hara_pair,left_hara,other,hane,top_cap |
| 耳 | 0.709 | 0.970 | 0.947 | 4 | other,bar_uroko |
| 言 | 0.736 | 0.978 | 0.981 | 0 | bar_uroko,bar_uroko,bar_uroko,bar_uroko,box_uroko,top_cap,uchikomi,uchikomi,uchikomi,uchikomi |
| 古 | 0.843 | 0.981 | 0.954 | 2 | bar_uroko,box_uroko,top_cap,top_cap,uchikomi |
| 石 | 0.635 | 0.989 | 0.991 | 0 | left_hara,bar_uroko,box_uroko,uchikomi |
| 見 | 0.532 | 0.966 | 0.961 | 4 | hara_pair,other,box_uroko,top_cap |
| 雨 | 0.682 | 0.989 | 0.967 | 2 | hane,other,other,other,other,bar_uroko,box_uroko,top_cap,uchikomi |
| 食 | 0.228 | 0.669 | 0.673 | 0 | hara_pair,bar_uroko,hane |
| 国 | 0.817 | 0.897 | 0.887 | 1 | top_cap,other,other,box_uroko,bar_uroko,top_cap,uchikomi,uchikomi,uchikomi |
| 車 | 0.843 | 0.908 | 0.888 | 5 | box_uroko,bar_uroko,bar_uroko,bar_uroko,top_cap,uchikomi,uchikomi |
| 金 | 0.341 | 0.843 | 0.848 | 2 | hara_pair,top_cap,bar_uroko,hane,bar_uroko,bar_uroko,uchikomi,uchikomi |
| 風 | 0.291 | 0.804 | 0.806 | 0 | right_hara,hane,left_hara,top_cap,hane,top_cap,top_cap |
| 東 | 0.679 | 0.925 | 0.927 | 3 | hara_pair,box_uroko,bar_uroko,bar_uroko,top_cap,uchikomi |
| 花 | 0.396 | 0.823 | 0.808 | 0 | other,other,bar_uroko,other,bar_uroko,top_cap,uchikomi |
