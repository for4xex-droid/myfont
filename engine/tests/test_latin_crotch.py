"""股の細めは、脚の全長で一次。端の 22% だけを細くしない。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.geometry import Vec2
from engine.latin.build import _widths
from engine.latin.load import load_resolved, load_style, styles_dir
from engine.latin.schema import Join, Knot, Stroke

_DECIDED = {"modern": 0.90, "pop": 0.85, "classic": 0.82, "chic": 1.0}


def _crotch_widths(
    factor: float, ends: tuple[str, str] = ("none", "foot")
) -> list[float]:
    """足が太く、股の端が細い直線。"""
    base = load_resolved("H", "classic")
    stroke = Stroke(
        "leg",
        (Knot(0.0, 0.5, "line"), Knot(1.0, 0.5, "line")),
        False,
        "thick",
        ends,
        None,
        None,
    )
    skeleton = replace(
        base.skeleton,
        glyph="probe",
        strokes=(stroke,),
        joins=(Join("leg", "stem", "crotch"),),
    )
    style = replace(base.style, joins={**base.style.joins, "crotch_thin": factor})
    resolved = replace(base, skeleton=skeleton, style=style)
    samples = [(Vec2(float(i), 0.0), Vec2(1.0, 0.0)) for i in range(21)]
    return _widths(samples, resolved, stroke)


def test_crotch_tapers_along_the_whole_leg():
    """細い端は股。途中は一次で、端の 22% だけが細くならない。"""
    factor = 0.82
    widths = _crotch_widths(factor)
    thick = widths[-1]
    assert widths[0] == pytest.approx(thick * factor, rel=0.02)
    mid = widths[len(widths) // 2]
    expect = thick * (1.0 - (1.0 - factor) * 0.5)
    assert mid == pytest.approx(expect, rel=0.02)
    early = widths[2]
    assert early == pytest.approx(
        thick * (factor + (1.0 - factor) * (2 / 20)), rel=0.02
    )


def test_both_ends_keep_a_constant_thin_width():
    """両端を細くする画は、全長が crotch_thin 倍。中央で折り返して縁を折らない。"""
    factor = 0.90
    widths = _crotch_widths(factor, ("foot", "foot"))
    assert widths[0] == pytest.approx(widths[-1], rel=0.01)
    assert max(widths) == pytest.approx(min(widths), rel=0.01)
    thick = _crotch_widths(1.0, ("foot", "foot"))[0]
    assert widths[len(widths) // 2] == pytest.approx(thick * factor, rel=0.01)


def test_partner_stem_is_not_thinned():
    """細めるのは接合の a 側だけ。幹（b）は全長で同じ太さ。"""
    base = load_resolved("H", "classic")
    stem = Stroke(
        "stem",
        (Knot(0.2, 0.0, "line"), Knot(0.2, 1.0, "line")),
        False,
        "thick",
        ("foot", "foot"),
        None,
        None,
    )
    leg = Stroke(
        "leg",
        (Knot(0.2, 0.5, "line"), Knot(1.0, 0.0, "line")),
        False,
        "thick",
        ("none", "foot"),
        None,
        None,
    )
    skeleton = replace(
        base.skeleton,
        glyph="probe",
        strokes=(stem, leg),
        joins=(Join("leg", "stem", "crotch"),),
    )
    style = replace(base.style, joins={**base.style.joins, "crotch_thin": 0.82})
    resolved = replace(base, skeleton=skeleton, style=style)
    samples = [(Vec2(0.0, float(i)), Vec2(0.0, 1.0)) for i in range(21)]
    widths = _widths(samples, resolved, stem)
    assert max(widths) == pytest.approx(min(widths))


@pytest.mark.parametrize("style", tuple(_DECIDED))
def test_crotch_thin_matches_the_decision(style):
    """組見本の MNWK で確かめるまでの暫定値。"""
    loaded = load_style(styles_dir() / f"{style}.yaml")
    assert loaded.joins["crotch_thin"] == _DECIDED[style]
    assert loaded.style_id.endswith("_v2")
