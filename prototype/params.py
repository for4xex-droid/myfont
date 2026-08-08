"""明朝体ディテールのパラメータセット。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MinchoParams:
    name: str
    # 基本太さ (UPM=1000)
    h_thickness: float  # 横画
    v_thickness: float  # 縦画
    # 横画の右上がり角度（度）
    h_slope_deg: float
    # うろこ（横画右端セリフ）
    uroko_height: float
    uroko_width: float
    uroko_dent: float  # 輪郭の凹み量（大きいほどクラシックな食い込み）
    # 打ち込み
    uchikomi_depth: float
    uchikomi_angle_deg: float
    # はね
    hane_length: float
    hane_thickness: float
    # 止め（縦画下端のわずかな広がり/斜めカット）
    tome_slant: float
    # はらい
    left_hara_root: float
    right_hara_max: float
    right_hara_bulge_t: float  # 膨らみ位置 0..1
    # 点
    ten_length: float
    ten_width: float


CLASSIC = MinchoParams(
    name="classic",
    h_thickness=45.0,
    v_thickness=100.0,
    h_slope_deg=1.6,
    uroko_height=78.0,
    uroko_width=72.0,
    uroko_dent=18.0,
    uchikomi_depth=28.0,
    uchikomi_angle_deg=38.0,
    hane_length=140.0,
    hane_thickness=38.0,
    tome_slant=22.0,
    left_hara_root=100.0,
    right_hara_max=110.0,
    right_hara_bulge_t=0.62,
    ten_length=95.0,
    ten_width=78.0,
)


MODERN = MinchoParams(
    name="modern",
    h_thickness=42.0,
    v_thickness=92.0,
    h_slope_deg=1.2,
    uroko_height=42.0,
    uroko_width=38.0,
    uroko_dent=6.0,
    uchikomi_depth=16.0,
    uchikomi_angle_deg=32.0,
    hane_length=110.0,
    hane_thickness=28.0,
    tome_slant=14.0,
    left_hara_root=92.0,
    right_hara_max=96.0,
    right_hara_bulge_t=0.58,
    ten_length=82.0,
    ten_width=62.0,
)


# 正本は engine/params/product_r1.yaml（部分P0）。ここは prototype 互換のミラー。
# 骨格（本の下部横など）の正本は engine/src/engine/extra_skeletons.py。
PRODUCT_R1 = MinchoParams(
    name="product_r1",
    h_thickness=45.0,
    v_thickness=110.0,
    h_slope_deg=1.5,
    uroko_height=78.0,
    uroko_width=72.0,
    uroko_dent=16.0,
    uchikomi_depth=26.0,
    uchikomi_angle_deg=36.0,
    hane_length=135.0,
    hane_thickness=36.0,
    tome_slant=20.0,
    left_hara_root=100.0,
    right_hara_max=108.0,
    right_hara_bulge_t=0.60,
    ten_length=92.0,
    ten_width=74.0,
)


PARAM_SETS = {
    "classic": CLASSIC,
    "modern": MODERN,
    "product_r1": PRODUCT_R1,
}
