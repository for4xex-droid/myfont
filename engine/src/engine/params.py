"""明朝体ディテールのパラメータセット。

product_r1 は engine/params/product_r1.yaml を正本とする（GOLDENRULES 掟16）。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


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


def _params_dir() -> Path:
    """snapshot ディレクトリ。repo の engine/params を優先し、なければパッケージ内。"""
    repo = Path(__file__).resolve().parents[2] / "params"
    if repo.is_dir():
        return repo
    return Path(__file__).resolve().parent / "snapshots"


def load_params_snapshot(snapshot_id: str, params_dir: Path | None = None) -> MinchoParams:
    """params/{snapshot_id}.yaml を読み MinchoParams にする。"""
    if "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise ValueError(f"invalid snapshot id: {snapshot_id!r}")
    root = (params_dir or _params_dir()).resolve()
    path = (root / f"{snapshot_id}.yaml").resolve()
    if path.parent != root or not path.is_file():
        raise FileNotFoundError(f"params snapshot not found: {snapshot_id}")
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict) or "params" not in doc:
        raise ValueError(f"invalid params snapshot: {path}")
    raw = dict(doc["params"])
    allowed = {f.name for f in fields(MinchoParams)}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown param keys in {snapshot_id}: {sorted(unknown)}")
    missing = allowed - set(raw)
    if missing:
        raise ValueError(f"missing param keys in {snapshot_id}: {sorted(missing)}")
    coerced: dict[str, str | float] = {"name": str(raw["name"])}
    for k in allowed - {"name"}:
        try:
            coerced[k] = float(raw[k])
        except (TypeError, ValueError) as e:
            raise ValueError(f"param {k!r} in {snapshot_id} must be numeric") from e
    return MinchoParams(**coerced)


PRODUCT_R1 = load_params_snapshot("product_r1")


PARAM_SETS = {
    "classic": CLASSIC,
    "modern": MODERN,
    "product_r1": PRODUCT_R1,
}
