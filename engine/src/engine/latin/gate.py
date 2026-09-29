"""様式分離。閾値は targets/separation.yaml の凍結値。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

_TARGETS = Path(__file__).resolve().parent / "targets" / "separation.yaml"


def separation_path() -> Path:
    return _TARGETS


def load_separation(path: Path | None = None) -> dict[str, Any]:
    raw = yaml.safe_load((path or _TARGETS).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("separation: mapping required")
    axes = tuple(raw["distance_axes"])
    styles = raw["styles"]
    span = {
        axis: (
            min(styles[name][axis] for name in styles),
            max(styles[name][axis] for name in styles),
        )
        for axis in axes
    }
    distances = pairwise_distances(styles, axes, span)
    nearest = min(distances.values())
    frozen = float(raw["min_distance"])
    if abs(nearest - frozen) > 1e-9:
        raise ValueError(f"separation: min distance {nearest} != frozen {frozen}")
    return {
        "axes": axes,
        "styles": styles,
        "span": span,
        "distances": distances,
        "min_distance": frozen,
    }


def _vector(style: dict[str, float], axes: tuple[str, ...], span: dict[str, tuple[float, float]]) -> list[float]:
    out: list[float] = []
    for axis in axes:
        lo, hi = span[axis]
        width = hi - lo
        out.append(0.0 if width == 0.0 else (float(style[axis]) - lo) / width)
    return out


def pairwise_distances(
    styles: dict[str, dict[str, float]],
    axes: tuple[str, ...],
    span: dict[str, tuple[float, float]],
) -> dict[tuple[str, str], float]:
    names = list(styles)
    vectors = {name: _vector(styles[name], axes, span) for name in names}
    distances: dict[tuple[str, str], float] = {}
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            gap = math.sqrt(sum((a - b) ** 2 for a, b in zip(vectors[left], vectors[right], strict=True)))
            distances[(left, right)] = gap
    return distances


def assert_separated(measured: dict[str, dict[str, float]], frozen: dict[str, Any] | None = None) -> None:
    """凍結した幅で測り、最近ペアが凍結距離未満なら ValueError。"""
    spec = frozen if frozen is not None else load_separation()
    distances = pairwise_distances(measured, spec["axes"], spec["span"])
    nearest = min(distances.items(), key=lambda item: item[1])
    if nearest[1] < spec["min_distance"] - 1e-9:
        pair = nearest[0]
        raise ValueError(
            f"G-SEP: {pair[0]}–{pair[1]} distance {nearest[1]:.4f} < {spec['min_distance']:.4f}"
        )
