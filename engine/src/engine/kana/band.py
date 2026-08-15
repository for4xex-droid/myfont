"""参照帯の文字列（kana_ref_compare の min..max）をスカラー照合する。

合否は kana_fit_step 専用。kana_gate には接続しない（帯は未凍結・掟8）。
"""

from __future__ import annotations

import math
from typing import Any


def parse_band_range(text: str) -> tuple[float, float] | None:
    """'1.065 .. 1.142' → (1.065, 1.142)。読めなければ None。"""
    s = text.strip()
    if ".." not in s:
        return None
    left, right = s.split("..", 1)
    try:
        lo = float(left.strip())
        hi = float(right.strip())
    except ValueError:
        return None
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def band_violations(
    ours: dict[str, Any] | None,
    band: dict[str, str] | None,
) -> list[str] | None:
    """帯外キー名。照合できたキーが1つも無ければ None（空リストは「全キー帯内」）。"""
    if not ours or not band:
        return None
    bad: list[str] = []
    compared = 0
    for key, raw in band.items():
        if key not in ours:
            continue
        rng = parse_band_range(str(raw))
        if rng is None:
            continue
        compared += 1
        try:
            val = float(ours[key])
        except (TypeError, ValueError):
            bad.append(key)
            continue
        lo, hi = rng
        if not math.isfinite(val) or val < lo or val > hi:
            bad.append(key)
    if compared == 0:
        return None
    return bad


def interpret_band_ok(
    ours: dict[str, Any] | None,
    band: dict[str, str] | None,
    viol: list[str] | None,
) -> bool | None:
    """None=未計測。False=帯外または照合不能。True=帯内。"""
    if viol is None:
        if ours and band:
            return False
        return None
    return len(viol) == 0


_OURS_KEYS = (
    "aspect_w_over_h",
    "top_ink_left_frac",
    "top_ink_right_frac",
    "bottom_cx_frac",
    "centroid_y_frac",
    "ink_density",
)


def parse_ours_line(line: str) -> dict[str, float] | None:
    """kana_ref_compare の 'OURS ...' 行。列不足・非有限は None。"""
    parts = line.split()
    if len(parts) < 7 or parts[0] != "OURS":
        return None
    try:
        vals = [float(parts[i]) for i in range(1, 7)]
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in vals):
        return None
    return dict(zip(_OURS_KEYS, vals, strict=True))


def fit_step_exit(
    *,
    gate_ok: bool,
    width_ok: bool,
    band_ok: bool | None,
    ref_exit: int | None,
    otf_present: bool,
    ours_present: bool,
    band_present: bool,
) -> int:
    """0=測れて帯内, 1=gate/width/帯外, 2=計測不能。"""
    if not otf_present or ref_exit != 0 or not ours_present or not band_present:
        return 2
    if not gate_ok or not width_ok or band_ok is not True:
        return 1
    return 0


def width_keys_ok(strokes: Any) -> bool:
    """各 element の入口 hw≤18、全キー∈[3, 40]。キー無し element は無視。"""
    saw = False
    for s in strokes:
        keys = getattr(s, "width_keys", None)
        if not keys:
            continue
        saw = True
        vals = [float(w) for _t, w in keys]
        if min(vals) < 3.0 or max(vals) > 40.0:
            return False
        if vals[0] > 18.0:
            return False
    return saw
