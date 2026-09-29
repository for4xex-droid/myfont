"""様式 YAML。数値を変えたら style_id を上げる。内容ハッシュは決定的。"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from engine.latin.pens import Pen
from engine.latin.schema import ENDS, GROUPS, SIDES

_TOP_KEYS = frozenset(
    {
        "style_id",
        "cap_height",
        "overshoot",
        "pen",
        "terminals",
        "joins",
        "proportions",
        "sidebearing",
        "vertical",
        "micro_area_floor",
        "curve",
        "groups",
        "metrics",
    }
)
_PEN_KEYS = frozenset({"type", "stem", "bar_ratio", "hairline", "theta_deg"})
_OVERSHOOT_KEYS = frozenset({"round", "apex"})
_SIDE_KEYS = frozenset({"base"}) | SIDES
_VERTICAL_KEYS = frozenset({"ascender", "descender"})
_CURVE_KEYS = frozenset({"max_error", "corner_deg", "max_anchors_per_contour"})
_GROUP_KEYS = frozenset({"stem_ratio", "bar_ratio", "hairline_ratio"})
_JOIN_KEYS = frozenset({"crotch_thin"})
_METRIC_KEYS = frozenset({"serif_length", "serif_thick", "round_frac", "bracket"})
_TERMINALS = frozenset(
    {
        "flat",
        "round",
        "serif_bracketed",
        "serif_hairline",
        "apex_sharp",
        "apex_cut",
        "ball",
        "spur",
        "none",
    }
)


def _reject_unknown(path: str, raw: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{path}: unknown keys {unknown}")


def _num(path: str, raw: Any) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{path}: number required, got {raw!r}")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{path}: number required, got {raw!r}")
    return value


def _pen(raw: Any) -> Pen:
    if not isinstance(raw, dict):
        raise ValueError("pen: mapping required")
    _reject_unknown("pen", raw, _PEN_KEYS)
    kind = raw.get("type")
    if kind not in ("mono", "nib"):
        raise ValueError(f"pen: unknown type {kind!r}")
    stem = _num("pen.stem", raw.get("stem"))
    bar = _num("pen.bar_ratio", raw.get("bar_ratio"))
    if stem <= 0.0 or stem > 0.5:
        raise ValueError(f"pen.stem: {stem} outside (0, 0.5]")
    if bar <= 0.0 or bar > 1.5:
        raise ValueError(f"pen.bar_ratio: {bar} outside (0, 1.5]")
    if kind == "nib":
        hairline = _num("pen.hairline", raw.get("hairline"))
        theta = _num("pen.theta_deg", raw.get("theta_deg"))
        if hairline <= 0.0 or hairline > stem:
            raise ValueError("pen.hairline: must be in (0, stem]")
    else:
        hairline = stem
        theta = 0.0
    return Pen(str(kind), stem, bar, hairline, theta)


def _groups(raw: Any) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        raise ValueError("groups: mapping required")
    out: dict[str, dict[str, float]] = {}
    for name, body in raw.items():
        if name not in GROUPS:
            raise ValueError(f"groups: unknown group {name!r}")
        if not isinstance(body, dict):
            raise ValueError(f"groups.{name}: mapping required")
        if "sidebearing" in body:
            raise ValueError(f"groups.{name}: sidebearing cannot be set on a group")
        _reject_unknown(f"groups.{name}", body, _GROUP_KEYS)
        out[str(name)] = {key: _num(f"groups.{name}.{key}", value) for key, value in body.items()}
    return out


def _canonical(raw: dict[str, Any]) -> str:
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class Style:
    name: str
    style_id: str
    cap_height: float
    overshoot: dict[str, float]
    pen: Pen
    terminals: dict[str, str]
    joins: dict[str, float]
    proportions: dict[str, float]
    sidebearing: dict[str, float]
    vertical: dict[str, float]
    micro_area_floor: float
    curve: dict[str, float]
    groups: dict[str, dict[str, float]]
    metrics: dict[str, float]
    content_hash: str


def parse_style(raw: dict[str, Any], *, name: str) -> Style:
    if not isinstance(raw, dict):
        raise ValueError("style: mapping required")
    _reject_unknown("style", raw, _TOP_KEYS)
    style_id = raw.get("style_id")
    if not isinstance(style_id, str) or not style_id:
        raise ValueError("style: style_id must be a non-empty string")
    cap = _num("cap_height", raw.get("cap_height"))
    if cap <= 0.0:
        raise ValueError("cap_height: must be positive")
    over_raw = raw.get("overshoot")
    if not isinstance(over_raw, dict):
        raise ValueError("overshoot: mapping required")
    _reject_unknown("overshoot", over_raw, _OVERSHOOT_KEYS)
    overshoot = {key: _num(f"overshoot.{key}", over_raw[key]) for key in _OVERSHOOT_KEYS}
    pen = _pen(raw.get("pen"))
    term_raw = raw.get("terminals")
    if not isinstance(term_raw, dict):
        raise ValueError("terminals: mapping required")
    _reject_unknown("terminals", term_raw, ENDS)
    if set(term_raw) != set(ENDS):
        raise ValueError(f"terminals: need every end {sorted(ENDS)}")
    terminals: dict[str, str] = {}
    for key, value in term_raw.items():
        if value not in _TERMINALS:
            raise ValueError(f"terminals.{key}: unknown template {value!r}")
        terminals[str(key)] = str(value)
    joins_raw = raw.get("joins")
    if not isinstance(joins_raw, dict):
        raise ValueError("joins: mapping required")
    _reject_unknown("joins", joins_raw, _JOIN_KEYS)
    joins = {key: _num(f"joins.{key}", joins_raw[key]) for key in joins_raw}
    if "crotch_thin" not in joins:
        raise ValueError("joins: crotch_thin required")
    prop_raw = raw.get("proportions")
    if not isinstance(prop_raw, dict) or not prop_raw:
        raise ValueError("proportions: non-empty mapping required")
    proportions = {str(key): _num(f"proportions.{key}", value) for key, value in prop_raw.items()}
    side_raw = raw.get("sidebearing")
    if not isinstance(side_raw, dict):
        raise ValueError("sidebearing: mapping required")
    _reject_unknown("sidebearing", side_raw, _SIDE_KEYS)
    if set(side_raw) != set(_SIDE_KEYS):
        raise ValueError("sidebearing: base and every Tracy class required")
    sidebearing = {str(key): _num(f"sidebearing.{key}", value) for key, value in side_raw.items()}
    vert_raw = raw.get("vertical")
    if not isinstance(vert_raw, dict):
        raise ValueError("vertical: mapping required")
    _reject_unknown("vertical", vert_raw, _VERTICAL_KEYS)
    vertical = {key: _num(f"vertical.{key}", vert_raw[key]) for key in _VERTICAL_KEYS}
    if vertical["descender"] >= 0.0 or vertical["ascender"] <= cap:
        raise ValueError("vertical: ascender must exceed cap height and descender must be negative")
    floor = _num("micro_area_floor", raw.get("micro_area_floor"))
    curve_raw = raw.get("curve")
    if not isinstance(curve_raw, dict):
        raise ValueError("curve: mapping required")
    _reject_unknown("curve", curve_raw, _CURVE_KEYS)
    curve = {key: _num(f"curve.{key}", curve_raw[key]) for key in _CURVE_KEYS}
    groups = _groups(raw.get("groups", {}))
    metrics_raw = raw.get("metrics", {})
    if not isinstance(metrics_raw, dict):
        raise ValueError("metrics: mapping required")
    _reject_unknown("metrics", metrics_raw, _METRIC_KEYS)
    metrics = {str(key): _num(f"metrics.{key}", value) for key, value in metrics_raw.items()}
    return Style(
        name,
        style_id,
        cap,
        overshoot,
        pen,
        terminals,
        joins,
        proportions,
        sidebearing,
        vertical,
        floor,
        curve,
        groups,
        metrics,
        hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest(),
    )


def load_style(path: Path) -> Style:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_style(raw, name=path.stem)
