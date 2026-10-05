"""ラテン骨格 YAML の厳格スキーマ。未知のキーと語彙外は拒否する。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

KNOT_TYPES = frozenset({"smooth", "corner", "line"})
ROLES = frozenset({"thick", "thin", "bar", "bowl", "run"})
ENDS = frozenset({"foot", "apex", "none", "open", "round_end"})
SIDES = frozenset({"straight", "near_straight", "round", "diagonal", "open"})
JOIN_TYPES = frozenset({"apex", "apex_cut", "T", "L", "crotch", "bowl_join"})
GROUPS = frozenset({"straight", "round", "diagonal", "open", "bar"})
STRUCTURES = frozenset({"stem_pair", "bowl", "apex_diagonals", "spine", "branch"})
STYLES = frozenset({"modern", "classic", "chic", "pop"})

_TOP_KEYS = frozenset(
    {"glyph", "unicode", "structure", "groups", "strokes", "joins", "sides", "expect", "variants"}
)
_STROKE_KEYS = frozenset({"id", "knots", "closed", "role", "ends", "tension", "tensions"})
_ENDS_KEYS = frozenset({"start", "end"})
_EXPECT_KEYS = frozenset({"contours", "holes"})
_JOIN_KEYS = frozenset({"a", "b", "type"})
_VARIANT_KEYS = _STROKE_KEYS | {"joins", "sides", "groups", "pen", "strokes"}

TENSION_MIN = 0.75
TENSION_MAX = 4.0
SCALAR_MAX = 12
COORD_MIN = 0.0
COORD_MAX = 1.0


def _reject_unknown(path: str, raw: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{path}: unknown keys {unknown}")


@dataclass(frozen=True)
class Knot:
    x: float
    y: float
    kind: str
    angle_deg: float | None = None


@dataclass(frozen=True)
class Stroke:
    id: str
    knots: tuple[Knot, ...]
    closed: bool
    role: str
    ends: tuple[str, str]
    tension: float | None
    tensions: tuple[float, ...] | None


@dataclass(frozen=True)
class Join:
    a: str
    b: str
    type: str


@dataclass(frozen=True)
class Skeleton:
    glyph: str
    unicode: int
    structure: str
    groups: tuple[str, ...]
    strokes: tuple[Stroke, ...]
    joins: tuple[Join, ...]
    sides: tuple[str, str]
    expect_contours: int
    expect_holes: int
    variants: dict[str, dict[str, Any]]


def _num(path: str, raw: Any) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{path}: number required, got {raw!r}")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{path}: number required, got {raw!r}")
    return value


def _coord(path: str, raw: Any) -> float:
    value = _num(path, raw)
    if value < COORD_MIN or value > COORD_MAX:
        raise ValueError(f"{path}: coordinate {value} outside [{COORD_MIN}, {COORD_MAX}]")
    return value


def _tension(path: str, raw: Any) -> float:
    value = _num(path, raw)
    if value < TENSION_MIN or value > TENSION_MAX:
        raise ValueError(f"{path}: tension {value} outside [{TENSION_MIN}, {TENSION_MAX}]")
    return value


def _knot(path: str, raw: Any) -> Knot:
    if not isinstance(raw, (list, tuple)) or len(raw) not in (3, 4):
        raise ValueError(f"{path}: knot must be [x, y, kind] or [x, y, kind, angle]")
    x = _coord(f"{path}.x", raw[0])
    y = _coord(f"{path}.y", raw[1])
    kind = raw[2]
    if kind not in KNOT_TYPES:
        raise ValueError(f"{path}: unknown knot type {kind!r}")
    angle: float | None = None
    if len(raw) == 4:
        if kind == "line":
            raise ValueError(f"{path}: line knot cannot take an angle")
        angle = _num(f"{path}.angle", raw[3])
    return Knot(x, y, str(kind), angle)


def _stroke(path: str, raw: Any, seen: set[str]) -> Stroke:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: stroke must be a mapping")
    _reject_unknown(path, raw, _STROKE_KEYS)
    sid = raw.get("id")
    if not isinstance(sid, str) or not sid:
        raise ValueError(f"{path}: id must be a non-empty string")
    if sid in seen:
        raise ValueError(f"{path}: duplicate stroke id {sid!r}")
    seen.add(sid)
    knots_raw = raw.get("knots")
    if not isinstance(knots_raw, list) or len(knots_raw) == 0:
        raise ValueError(f"{path}: knots must be a non-empty list")
    knots = tuple(_knot(f"{path}.knots[{i}]", item) for i, item in enumerate(knots_raw))
    closed = bool(raw.get("closed", False))
    if closed and len(knots) < 3:
        raise ValueError(f"{path}: closed stroke needs at least 3 knots")
    if not closed and len(knots) < 2:
        raise ValueError(f"{path}: open stroke needs at least 2 knots")
    role = raw.get("role")
    if role not in ROLES:
        raise ValueError(f"{path}: unknown role {role!r}")
    ends_raw = raw.get("ends")
    if not isinstance(ends_raw, dict):
        raise ValueError(f"{path}: ends must be a mapping")
    _reject_unknown(f"{path}.ends", ends_raw, _ENDS_KEYS)
    start, end = ends_raw.get("start"), ends_raw.get("end")
    if start not in ENDS or end not in ENDS:
        raise ValueError(f"{path}: unknown ends {(start, end)!r}")
    if "tension" in raw and "tensions" in raw:
        raise ValueError(f"{path}: set tension or tensions, not both")
    tension = _tension(f"{path}.tension", raw["tension"]) if "tension" in raw else None
    tensions: tuple[float, ...] | None = None
    if "tensions" in raw:
        raw_t = raw["tensions"]
        if not isinstance(raw_t, list):
            raise ValueError(f"{path}.tensions: list required")
        tensions = tuple(_tension(f"{path}.tensions[{i}]", v) for i, v in enumerate(raw_t))
        expect = len(knots) if closed else len(knots) - 1
        if len(tensions) != expect:
            raise ValueError(f"{path}.tensions: length {len(tensions)} != {expect}")
    return Stroke(sid, knots, closed, str(role), (str(start), str(end)), tension, tensions)


def _segment_count(stroke: Stroke) -> int:
    n = len(stroke.knots)
    return n if stroke.closed else n - 1


def free_scalar_count(skeleton: Skeleton) -> int:
    """張力と接線角度だけを数える。座標は数えない。"""
    count = 0
    for stroke in skeleton.strokes:
        if stroke.tension is not None:
            count += 1
        if stroke.tensions is not None:
            count += len(stroke.tensions)
        count += sum(1 for knot in stroke.knots if knot.angle_deg is not None)
    return count


def _joins(path: str, raw: Any, ids: set[str]) -> tuple[Join, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{path}: list required")
    joins: list[Join] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{path}[{i}]: mapping required")
        _reject_unknown(f"{path}[{i}]", item, _JOIN_KEYS)
        a, b, kind = item.get("a"), item.get("b"), item.get("type")
        if a not in ids or b not in ids:
            raise ValueError(f"{path}[{i}]: unknown stroke in join {(a, b)!r}")
        if kind not in JOIN_TYPES:
            raise ValueError(f"{path}[{i}]: unknown join type {kind!r}")
        joins.append(Join(str(a), str(b), str(kind)))
    return tuple(joins)


def parse_skeleton(raw: dict[str, Any]) -> Skeleton:
    if not isinstance(raw, dict):
        raise ValueError("skeleton: mapping required")
    _reject_unknown("skeleton", raw, _TOP_KEYS)
    glyph = raw.get("glyph")
    if not isinstance(glyph, str) or not glyph:
        raise ValueError("skeleton: glyph must be a non-empty string")
    unicode = raw.get("unicode")
    if isinstance(unicode, bool) or not isinstance(unicode, int):
        raise ValueError("skeleton: unicode must be an int")
    structure = raw.get("structure")
    if structure not in STRUCTURES:
        raise ValueError(f"skeleton: unknown structure {structure!r}")
    groups_raw = raw.get("groups", [])
    if not isinstance(groups_raw, list) or any(g not in GROUPS for g in groups_raw):
        raise ValueError(f"skeleton: unknown groups {groups_raw!r}")
    strokes_raw = raw.get("strokes")
    if not isinstance(strokes_raw, list) or not strokes_raw:
        raise ValueError("skeleton: strokes must be a non-empty list")
    seen: set[str] = set()
    strokes = tuple(_stroke(f"strokes[{i}]", item, seen) for i, item in enumerate(strokes_raw))
    joins = _joins("joins", raw.get("joins", []), seen)
    sides_raw = raw.get("sides")
    if not isinstance(sides_raw, dict):
        raise ValueError("skeleton: sides must be a mapping")
    _reject_unknown("sides", sides_raw, frozenset({"left", "right"}))
    left, right = sides_raw.get("left"), sides_raw.get("right")
    if left not in SIDES or right not in SIDES:
        raise ValueError(f"skeleton: unknown sides {(left, right)!r}")
    expect = raw.get("expect")
    if not isinstance(expect, dict):
        raise ValueError("skeleton: expect must be a mapping")
    _reject_unknown("expect", expect, _EXPECT_KEYS)
    contours, holes = expect.get("contours"), expect.get("holes")
    if isinstance(contours, bool) or not isinstance(contours, int) or contours < 1:
        raise ValueError("skeleton: expect.contours must be a positive int")
    if isinstance(holes, bool) or not isinstance(holes, int) or holes < 0:
        raise ValueError("skeleton: expect.holes must be a non-negative int")
    variants_raw = raw.get("variants", {})
    if not isinstance(variants_raw, dict):
        raise ValueError("skeleton: variants must be a mapping")
    variants: dict[str, dict[str, Any]] = {}
    for name, body in variants_raw.items():
        if name not in STYLES:
            raise ValueError(f"variants: unknown style {name!r}")
        if not isinstance(body, dict):
            raise ValueError(f"variants.{name}: mapping required")
        _reject_unknown(f"variants.{name}", body, _VARIANT_KEYS)
        variants[str(name)] = body
    skeleton = Skeleton(
        glyph,
        int(unicode),
        str(structure),
        tuple(str(g) for g in groups_raw),
        strokes,
        joins,
        (str(left), str(right)),
        int(contours),
        int(holes),
        variants,
    )
    if free_scalar_count(skeleton) > SCALAR_MAX:
        raise ValueError(f"skeleton: free scalars {free_scalar_count(skeleton)} > {SCALAR_MAX}")
    return skeleton


def segment_count(stroke: Stroke) -> int:
    return _segment_count(stroke)
