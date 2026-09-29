"""工程2 G-S: 壊れた骨格は拒否し、語彙内だけ通す。"""

from __future__ import annotations

import pytest

from engine.latin.schema import SCALAR_MAX, parse_skeleton


def _skeleton(**overrides):
    raw = {
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
    }
    raw.update(overrides)
    return raw


def test_valid_skeleton_loads():
    sk = parse_skeleton(_skeleton())
    assert sk.glyph == "H"
    assert sk.unicode == 0x48
    assert sk.strokes[0].knots[0].kind == "line"


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_skeleton(_skeleton(extra=1))


def test_empty_knots_are_rejected():
    raw = _skeleton()
    raw["strokes"][0]["knots"] = []
    with pytest.raises(ValueError, match="knots"):
        parse_skeleton(raw)


def test_duplicate_stroke_id_is_rejected():
    raw = _skeleton()
    raw["strokes"].append(dict(raw["strokes"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        parse_skeleton(raw)


def test_closed_stroke_needs_three_knots():
    raw = _skeleton()
    raw["strokes"][0]["closed"] = True
    with pytest.raises(ValueError, match="closed"):
        parse_skeleton(raw)


def test_coordinate_outside_unit_square_is_rejected():
    raw = _skeleton()
    raw["strokes"][0]["knots"][0] = [1.1, 0.0, "line"]
    with pytest.raises(ValueError, match="coordinate"):
        parse_skeleton(raw)


def test_tension_outside_range_is_rejected():
    raw = _skeleton()
    raw["strokes"][0]["tension"] = 0.5
    with pytest.raises(ValueError, match="tension"):
        parse_skeleton(raw)


def test_line_knot_cannot_take_an_angle():
    raw = _skeleton()
    raw["strokes"][0]["knots"][0] = [0.1, 0.0, "line", 90]
    with pytest.raises(ValueError, match="angle"):
        parse_skeleton(raw)


def test_tensions_length_must_match_segments():
    raw = _skeleton()
    raw["strokes"][0]["tensions"] = [1.0, 1.0]
    with pytest.raises(ValueError, match="tensions"):
        parse_skeleton(raw)


def test_free_scalar_cap():
    knots = [[i / 13.0, 0.0, "smooth"] for i in range(14)]
    raw = _skeleton()
    raw["strokes"][0]["knots"] = knots
    raw["strokes"][0]["tensions"] = [1.0] * 13
    with pytest.raises(ValueError, match="free scalars"):
        parse_skeleton(raw)
    raw["strokes"][0]["tensions"] = [1.0] * (SCALAR_MAX)
    # 14 knots → 13 segments, so 12 tensions is still a length mismatch.
    raw["strokes"][0]["knots"] = [[i / 12.0, 0.2, "smooth"] for i in range(13)]
    raw["strokes"][0]["tensions"] = [1.0] * SCALAR_MAX
    assert parse_skeleton(raw).glyph == "H"


def test_variant_sidebearing_is_an_unknown_key():
    raw = _skeleton(variants={"modern": {"sidebearing": {"straight": 0.1}}})
    with pytest.raises(ValueError, match="unknown keys"):
        parse_skeleton(raw)
