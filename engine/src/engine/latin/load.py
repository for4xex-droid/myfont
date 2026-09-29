"""骨格を読み、様式の3層（全体 → グループ → 字）でパラメータを合成する。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from engine.latin.pens import Pen
from engine.latin.schema import (
    SCALAR_MAX,
    STYLES,
    Knot,
    Skeleton,
    Stroke,
    free_scalar_count,
    parse_skeleton,
)
from engine.latin.style import Style, load_style

_SKELETONS = Path(__file__).resolve().parent / "skeletons"
_STYLES = Path(__file__).resolve().parent / "styles"
_VARIANT_TOP = frozenset({"joins", "sides", "groups", "pen", "strokes", "tension", "tensions"})


def skeletons_dir() -> Path:
    return _SKELETONS


def styles_dir() -> Path:
    return _STYLES


def load_skeleton(path: Path) -> Skeleton:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: skeleton must be a mapping")
    return parse_skeleton(raw)


def load_glyph(name: str) -> Skeleton:
    path = _SKELETONS / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"no skeleton {name!r}")
    return load_skeleton(path)


@dataclass(frozen=True)
class Resolved:
    skeleton: Skeleton
    style: Style
    pen: Pen


def _knot_raw(knot: Knot) -> list[Any]:
    row: list[Any] = [knot.x, knot.y, knot.kind]
    if knot.angle_deg is not None:
        row.append(knot.angle_deg)
    return row


def _stroke_raw(stroke: Stroke) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": stroke.id,
        "knots": [_knot_raw(knot) for knot in stroke.knots],
        "closed": stroke.closed,
        "role": stroke.role,
        "ends": {"start": stroke.ends[0], "end": stroke.ends[1]},
    }
    if stroke.tension is not None:
        raw["tension"] = stroke.tension
    if stroke.tensions is not None:
        raw["tensions"] = list(stroke.tensions)
    return raw


def _skeleton_raw(skeleton: Skeleton) -> dict[str, Any]:
    return {
        "glyph": skeleton.glyph,
        "unicode": skeleton.unicode,
        "structure": skeleton.structure,
        "groups": list(skeleton.groups),
        "strokes": [_stroke_raw(stroke) for stroke in skeleton.strokes],
        "joins": [{"a": join.a, "b": join.b, "type": join.type} for join in skeleton.joins],
        "sides": {"left": skeleton.sides[0], "right": skeleton.sides[1]},
        "expect": {"contours": skeleton.expect_contours, "holes": skeleton.expect_holes},
    }


def apply_variant(skeleton: Skeleton, style_name: str) -> Skeleton:
    """字ごとの variant を骨格へ焼き込む。pen はここでは触らない。"""
    if style_name not in STYLES:
        raise ValueError(f"unknown style {style_name!r}")
    variant = skeleton.variants.get(style_name)
    if not variant:
        return skeleton
    unknown = sorted(set(variant) - _VARIANT_TOP)
    if unknown:
        raise ValueError(f"variants.{style_name}: put stroke fields under strokes, got {unknown}")
    if "sidebearing" in variant:
        raise ValueError(f"variants.{style_name}: sidebearing cannot be set on a glyph")
    raw = _skeleton_raw(skeleton)
    if "joins" in variant:
        raw["joins"] = variant["joins"]
    if "sides" in variant:
        raw["sides"] = variant["sides"]
    if "groups" in variant:
        raw["groups"] = variant["groups"]
    if "tension" in variant or "tensions" in variant:
        key = "tensions" if "tensions" in variant else "tension"
        for stroke in raw["strokes"]:
            stroke.pop("tension", None)
            stroke.pop("tensions", None)
            stroke[key] = variant[key]
    if "strokes" in variant:
        order = [stroke["id"] for stroke in raw["strokes"]]
        by_id = {stroke["id"]: stroke for stroke in raw["strokes"]}
        for patch in variant["strokes"]:
            if not isinstance(patch, dict) or "id" not in patch:
                raise ValueError(f"variants.{style_name}.strokes: each item needs an id")
            sid = patch["id"]
            if sid not in by_id:
                raise ValueError(f"variants.{style_name}: unknown stroke {sid!r}")
            target = by_id[sid]
            if "tension" in patch or "tensions" in patch:
                target.pop("tension", None)
                target.pop("tensions", None)
            for key, value in patch.items():
                if key != "id":
                    target[key] = value
        raw["strokes"] = [by_id[sid] for sid in order]
    resolved = parse_skeleton(raw)
    if free_scalar_count(resolved) > SCALAR_MAX:
        raise ValueError(
            f"variants.{style_name}: free scalars {free_scalar_count(resolved)} > {SCALAR_MAX}"
        )
    return resolved


def merge_pen(style: Style, groups: tuple[str, ...], variant_pen: dict[str, Any] | None) -> Pen:
    """全体 → その字のグループ → 字の pen。側面はグループも字も触れない。"""
    stem = style.pen.stem
    bar_ratio = style.pen.bar_ratio
    hairline = style.pen.hairline
    theta = style.pen.theta_deg
    kind = style.pen.type
    for name in groups:
        body = style.groups.get(name)
        if not body:
            continue
        if "stem_ratio" in body:
            stem *= body["stem_ratio"]
        if "bar_ratio" in body:
            bar_ratio = body["bar_ratio"]
        if "hairline_ratio" in body:
            hairline *= body["hairline_ratio"]
    if variant_pen:
        if "sidebearing" in variant_pen:
            raise ValueError("variant pen cannot set sidebearing")
        allowed = {"type", "stem", "bar_ratio", "hairline", "theta_deg"}
        unknown = sorted(set(variant_pen) - allowed)
        if unknown:
            raise ValueError(f"variant pen: unknown keys {unknown}")
        if "type" in variant_pen:
            kind = str(variant_pen["type"])
        if "stem" in variant_pen:
            stem = float(variant_pen["stem"])
        if "bar_ratio" in variant_pen:
            bar_ratio = float(variant_pen["bar_ratio"])
        if "hairline" in variant_pen:
            hairline = float(variant_pen["hairline"])
        if "theta_deg" in variant_pen:
            theta = float(variant_pen["theta_deg"])
    return Pen(kind, stem, bar_ratio, hairline, theta)


def resolve(skeleton: Skeleton, style: Style) -> Resolved:
    if skeleton.glyph not in style.proportions:
        raise ValueError(f"{style.name}: no proportion for {skeleton.glyph!r}")
    baked = apply_variant(skeleton, style.name)
    pen = merge_pen(style, baked.groups, skeleton.variants.get(style.name, {}).get("pen"))
    return Resolved(baked, style, pen)


def load_resolved(glyph: str, style_name: str) -> Resolved:
    if style_name not in STYLES:
        raise ValueError(f"unknown style {style_name!r}")
    return resolve(load_glyph(glyph), load_style(_STYLES / f"{style_name}.yaml"))
