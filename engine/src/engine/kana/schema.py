"""仮名骨格 YAML の joins / gate スキーマ（実装契約）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_TOP_KEYS = frozenset(
    {"char", "glyph_id", "unicode", "name", "motif", "elements", "joins", "gate"}
)
_ELEMENT_KEYS = frozenset({"id", "spine", "width", "ends"})
_JOIN_KEYS = frozenset({"from", "to", "mode"})
_GATE_KEYS = frozenset(
    {"expect_contours", "max_overshoot_upm", "bbox", "tips", "gaps"}
)
_BBOX_KEYS = frozenset({"width", "height", "aspect_w_over_h"})
_TIP_KEYS = frozenset({"element", "end", "bearing_deg"})
_GAP_KEYS = frozenset({"a", "b", "min_upm", "max_upm"})
_JOIN_MODES = frozenset({"abut", "separate"})
_TIP_ENDS = frozenset({"entry", "exit"})


def _reject_unknown(path: str, raw: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{path}: unknown keys {unknown}; allowed={sorted(allowed)}")


def _pair_f(
    path: str, key: str, raw: Any, *, allow_wrap: bool = False
) -> tuple[float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{path}: {key} must be [lo, hi], got {raw!r}")
    lo, hi = float(raw[0]), float(raw[1])
    if lo > hi and not allow_wrap:
        raise ValueError(f"{path}: {key} lo>hi ({lo}>{hi})")
    return lo, hi


@dataclass(frozen=True)
class JoinSpec:
    from_id: str
    to_id: str
    mode: str  # abut | separate


@dataclass(frozen=True)
class GateTipSpec:
    element: str
    end: str  # entry | exit
    bearing_deg: tuple[float, float]


@dataclass(frozen=True)
class GateGapSpec:
    a: str
    b: str
    min_upm: float
    max_upm: float


@dataclass(frozen=True)
class GateBBoxSpec:
    width: tuple[float, float]
    height: tuple[float, float]
    aspect_w_over_h: tuple[float, float] | None = None


@dataclass(frozen=True)
class GateSpec:
    expect_contours: int
    max_overshoot_upm: float | None = None
    bbox: GateBBoxSpec | None = None
    tips: tuple[GateTipSpec, ...] = ()
    gaps: tuple[GateGapSpec, ...] = ()


def parse_joins(path: str, raw: Any) -> tuple[JoinSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{path}: joins must be a list")
    out: list[JoinSpec] = []
    for i, item in enumerate(raw):
        p = f"{path}:joins[{i}]"
        if not isinstance(item, dict):
            raise ValueError(f"{p}: must be mapping")
        _reject_unknown(p, item, _JOIN_KEYS)
        for req in ("from", "to", "mode"):
            if req not in item:
                raise ValueError(f"{p}: missing required key '{req}'")
        mode = str(item["mode"])
        if mode not in _JOIN_MODES:
            raise ValueError(f"{p}: mode must be abut|separate, got {mode!r}")
        out.append(
            JoinSpec(from_id=str(item["from"]), to_id=str(item["to"]), mode=mode)
        )
    return tuple(out)


def parse_gate(path: str, raw: Any) -> GateSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: gate must be mapping")
    _reject_unknown(f"{path}:gate", raw, _GATE_KEYS)
    if "expect_contours" not in raw:
        raise ValueError(f"{path}:gate: missing required key 'expect_contours'")
    expect = int(raw["expect_contours"])
    if expect < 1:
        raise ValueError(f"{path}:gate: expect_contours must be ≥1")

    max_over: float | None = None
    if "max_overshoot_upm" in raw:
        max_over = float(raw["max_overshoot_upm"])
        if max_over < 0:
            raise ValueError(f"{path}:gate: max_overshoot_upm must be ≥0")

    bbox: GateBBoxSpec | None = None
    if "bbox" in raw:
        br = raw["bbox"]
        bp = f"{path}:gate.bbox"
        if not isinstance(br, dict):
            raise ValueError(f"{bp}: must be mapping")
        _reject_unknown(bp, br, _BBOX_KEYS)
        for req in ("width", "height"):
            if req not in br:
                raise ValueError(f"{bp}: missing required key '{req}'")
        aspect = None
        if "aspect_w_over_h" in br:
            aspect = _pair_f(bp, "aspect_w_over_h", br["aspect_w_over_h"])
        bbox = GateBBoxSpec(
            width=_pair_f(bp, "width", br["width"]),
            height=_pair_f(bp, "height", br["height"]),
            aspect_w_over_h=aspect,
        )

    tips: list[GateTipSpec] = []
    if "tips" in raw:
        tr = raw["tips"]
        if not isinstance(tr, list):
            raise ValueError(f"{path}:gate.tips must be a list")
        for i, item in enumerate(tr):
            tp = f"{path}:gate.tips[{i}]"
            if not isinstance(item, dict):
                raise ValueError(f"{tp}: must be mapping")
            _reject_unknown(tp, item, _TIP_KEYS)
            for req in ("element", "end", "bearing_deg"):
                if req not in item:
                    raise ValueError(f"{tp}: missing required key '{req}'")
            end = str(item["end"])
            if end not in _TIP_ENDS:
                raise ValueError(f"{tp}: end must be entry|exit, got {end!r}")
            tips.append(
                GateTipSpec(
                    element=str(item["element"]),
                    end=end,
                    # ±180 近傍のセクターは lo>hi のラップ帯を許可
                    bearing_deg=_pair_f(
                        tp, "bearing_deg", item["bearing_deg"], allow_wrap=True
                    ),
                )
            )

    gaps: list[GateGapSpec] = []
    if "gaps" in raw:
        gr = raw["gaps"]
        if not isinstance(gr, list):
            raise ValueError(f"{path}:gate.gaps must be a list")
        for i, item in enumerate(gr):
            gp = f"{path}:gate.gaps[{i}]"
            if not isinstance(item, dict):
                raise ValueError(f"{gp}: must be mapping")
            _reject_unknown(gp, item, _GAP_KEYS)
            for req in ("a", "b", "min_upm", "max_upm"):
                if req not in item:
                    raise ValueError(f"{gp}: missing required key '{req}'")
            lo, hi = float(item["min_upm"]), float(item["max_upm"])
            if lo > hi:
                raise ValueError(f"{gp}: min_upm>max_upm")
            gaps.append(
                GateGapSpec(
                    a=str(item["a"]),
                    b=str(item["b"]),
                    min_upm=lo,
                    max_upm=hi,
                )
            )

    return GateSpec(
        expect_contours=expect,
        max_overshoot_upm=max_over,
        bbox=bbox,
        tips=tuple(tips),
        gaps=tuple(gaps),
    )


def validate_top_level(path: str, raw: dict[str, Any]) -> None:
    _reject_unknown(path, raw, _TOP_KEYS)


def validate_element_keys(path: str, el: dict[str, Any]) -> None:
    _reject_unknown(path, el, _ELEMENT_KEYS)
