"""内部 UFO は version 0.001 で、ライセンス URL を持たない。"""

from __future__ import annotations

from pathlib import Path

import ufoLib2

from engine.latin.build import build_glyph
from engine.latin.load import load_resolved, load_style, styles_dir
from engine.latin.outline import fit_outline
from engine.latin.ufo import VERSION, write_ufo


def test_fitted_h_uses_axis_aligned_lines(tmp_path: Path):
    resolved = load_resolved("H", "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    assert paths
    axis = False
    for path in paths:
        cur = path.start
        for seg in path.segs:
            end = (seg[1], seg[2]) if seg[0] == "L" else (seg[5], seg[6])
            if seg[0] == "L" and (end[0] == cur[0] or end[1] == cur[1]):
                axis = True
            cur = end
    assert axis


def test_ufo_is_wip_without_a_license_url(tmp_path: Path):
    style = load_style(styles_dir() / "modern.yaml")
    resolved = load_resolved("O", "modern")
    outline = build_glyph(resolved)
    out = write_ufo(
        style,
        [(resolved.skeleton.glyph, resolved.skeleton.unicode, outline.advance, fit_outline(outline, style))],
        tmp_path / "SomeiroModern-Regular.ufo",
    )
    font = ufoLib2.Font.open(out)
    assert font.info.openTypeNameVersion == VERSION
    assert font.info.versionMajor == 0
    assert font.info.openTypeNameLicense is None
    assert font.info.openTypeNameLicenseURL is None
    assert font.lib["myfont.latin.wip"] is True
    glyph = font["O"]
    assert glyph.unicodes == [0x4F]
    assert glyph.width > 0
    assert len(glyph) >= 2
