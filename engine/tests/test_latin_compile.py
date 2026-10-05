"""G-TT。OTF と TTF の差。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from engine.latin.compile import build_style, otf_ttf_gap

_PAIRS = (("modern", "H"), ("modern", "O"), ("pop", "H"), ("pop", "O"))


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return {style: build_style(style, glyphs=("H", "O"), out_dir=root) for style in ("modern", "pop")}


@pytest.mark.parametrize(("style", "glyph"), _PAIRS)
def test_ttf_stays_close_to_the_otf(compiled, style, glyph):
    iou, hausdorff = otf_ttf_gap(compiled[style]["otf"], compiled[style]["ttf"], glyph)
    assert iou >= 0.999
    assert hausdorff <= 1.0
