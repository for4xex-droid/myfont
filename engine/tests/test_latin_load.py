"""工程2: H/O の読み込み、variant、3層の上書き。"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.latin.load import apply_variant, load_glyph, merge_pen, resolve, styles_dir
from engine.latin.schema import parse_skeleton
from engine.latin.style import load_style, parse_style

ROOT = Path(__file__).resolve().parents[1]


def _style(**pen):
    raw = {
        "style_id": "modern_v1",
        "cap_height": 700,
        "overshoot": {"round": 0.01, "apex": 0.01},
        "pen": {"type": "mono", "stem": 0.13, "bar_ratio": 0.9, **pen},
        "terminals": {k: "flat" for k in ("foot", "apex", "none", "open", "round_end")},
        "joins": {"crotch_thin": 1.0},
        "proportions": {"H": 0.7, "O": 1.0, "V": 0.8},
        "sidebearing": {
            "base": 0.08,
            "straight": 1.0,
            "near_straight": 0.8,
            "round": 0.5,
            "diagonal": 0.2,
            "open": 0.3,
        },
        "vertical": {"ascender": 800, "descender": -120},
        "micro_area_floor": 400,
        "curve": {"max_error": 0.6, "corner_deg": 30, "max_anchors_per_contour": 12},
        "groups": {"straight": {"stem_ratio": 1.2}},
    }
    return parse_style(raw, name="modern")


def test_h_and_o_yaml_load():
    h = load_glyph("H")
    o = load_glyph("O")
    assert h.unicode == 0x48
    assert o.unicode == 0x4F
    assert o.strokes[0].closed is True
    assert len(o.strokes[0].knots) == 4


def test_variant_replaces_the_join():
    v = load_glyph("V")
    baked = apply_variant(v, "classic")
    assert baked.joins[0].type == "apex_cut"
    assert apply_variant(v, "modern").joins[0].type == "apex"


def test_group_then_variant_override_pen_but_not_sidebearing():
    style = _style()
    sk = parse_skeleton(
        {
            "glyph": "H",
            "unicode": 0x48,
            "structure": "stem_pair",
            "groups": ["straight"],
            "strokes": [
                {
                    "id": "left",
                    "knots": [[0.1, 0.0, "line"], [0.1, 1.0, "line"]],
                    "role": "thick",
                    "ends": {"start": "foot", "end": "foot"},
                }
            ],
            "joins": [],
            "sides": {"left": "straight", "right": "straight"},
            "expect": {"contours": 1, "holes": 0},
            "variants": {"modern": {"pen": {"stem": 0.20}}},
        }
    )
    grouped = merge_pen(style, ("straight",), None)
    assert grouped.stem == pytest.approx(0.13 * 1.2)
    resolved = resolve(sk, style)
    assert resolved.pen.stem == pytest.approx(0.20)
    assert resolved.style.sidebearing["straight"] == 1.0


def test_group_cannot_carry_sidebearing():
    raw = {
        "style_id": "modern_v1",
        "cap_height": 700,
        "overshoot": {"round": 0.01, "apex": 0.01},
        "pen": {"type": "mono", "stem": 0.13, "bar_ratio": 0.9},
        "terminals": {k: "none" for k in ("foot", "apex", "none", "open", "round_end")},
        "joins": {"crotch_thin": 1.0},
        "proportions": {"H": 0.7},
        "sidebearing": {
            "base": 0.08,
            "straight": 1.0,
            "near_straight": 0.8,
            "round": 0.5,
            "diagonal": 0.2,
            "open": 0.3,
        },
        "vertical": {"ascender": 800, "descender": -120},
        "micro_area_floor": 400,
        "curve": {"max_error": 0.6, "corner_deg": 30, "max_anchors_per_contour": 12},
        "groups": {"straight": {"sidebearing": {"straight": 0.1}}},
    }
    with pytest.raises(ValueError, match="sidebearing"):
        parse_style(raw, name="modern")


def test_style_hash_changes_when_a_number_changes():
    first = load_style(styles_dir() / "modern.yaml")
    again = load_style(styles_dir() / "modern.yaml")
    assert first.content_hash == again.content_hash
    assert first.style_id == "modern_v2"
    text = (styles_dir() / "modern.yaml").read_text(encoding="utf-8")
    assert "0.13" in text
    other = load_style(ROOT / "src" / "engine" / "latin" / "styles" / "pop.yaml")
    assert other.content_hash != first.content_hash
