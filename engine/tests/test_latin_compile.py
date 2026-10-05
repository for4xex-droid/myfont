"""G-TT。書き出した OTF と TTF を、設計の輪郭から UPM で測る。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from engine.latin.build import build_glyph
from engine.latin.compile import build_style, outline_gap, thin_change
from engine.latin.load import load_resolved
from engine.latin.outline import fit_outline

_STYLES = ("modern", "pop", "chic")
_GLYPHS = ("H", "O")
_PAIRS = tuple((style, glyph) for style in _STYLES for glyph in _GLYPHS)


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return {
        style: build_style(style, glyphs=_GLYPHS, out_dir=root / style)
        for style in _STYLES
    }


def _design(style: str, glyph: str):
    resolved = load_resolved(glyph, style)
    return resolved, fit_outline(build_glyph(resolved), resolved.style)


@pytest.mark.parametrize("kind", ("otf", "ttf"))
@pytest.mark.parametrize(("style", "glyph"), _PAIRS)
def test_shipped_outline_stays_on_the_design(compiled, style, glyph, kind):
    _resolved, design = _design(style, glyph)
    worst, mean = outline_gap(design, compiled[style][kind], glyph)
    assert worst <= 1.0
    assert mean <= 0.3


@pytest.mark.parametrize("kind", ("otf", "ttf"))
@pytest.mark.parametrize("glyph", _GLYPHS)
def test_chic_hairlines_keep_their_thickness(compiled, glyph, kind):
    resolved, design = _design("chic", glyph)
    hairline = resolved.style.pen.hairline * resolved.style.cap_height
    assert (
        thin_change(design, compiled["chic"][kind], glyph, limit=2.0 * hairline) <= 0.03
    )


def test_gap_sees_a_shifted_outline(compiled):
    _resolved, design = _design("modern", "O")
    shifted = tuple(path.transform(lambda x, y: (x + 1.0, y)) for path in design)
    worst, mean = outline_gap(shifted, compiled["modern"]["otf"], "O")
    assert worst >= 0.9
    assert mean >= 0.5
