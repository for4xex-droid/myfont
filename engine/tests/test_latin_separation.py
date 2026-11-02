"""G-SEP: 凍結した4様式の距離を下回ると失敗する。"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pytest
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from engine.latin.compile import build_style
from engine.latin.gate import assert_separated, load_separation
from engine.latin.measure import measure_otf

_STYLES = ("modern", "classic", "chic", "pop")


@pytest.fixture(scope="module")
def pilot_otfs():
    root = Path(tempfile.mkdtemp())
    return {
        style: build_style(style, glyphs=("H", "O"), out_dir=root / style)["otf"]
        for style in _STYLES
    }


def test_frozen_pilot_meets_its_own_threshold():
    spec = load_separation()
    assert spec["nearest_distance"] == pytest.approx(1.0361423548057718)
    assert spec["min_distance"] == pytest.approx(1.0246593482190323)
    assert spec["min_distance"] <= spec["nearest_distance"]
    assert_separated(spec["styles"], spec)
    assert ("modern", "classic") in spec["distances"]


def test_threshold_above_the_frozen_nearest_is_rejected(tmp_path):
    import yaml

    from engine.latin.gate import separation_path

    raw = yaml.safe_load(separation_path().read_text(encoding="utf-8"))
    raw["min_distance"] = raw["nearest_distance"] + 0.01
    path = tmp_path / "separation.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="threshold"):
        load_separation(path)


def test_collapsed_classic_fails():
    spec = load_separation()
    measured = copy.deepcopy(spec["styles"])
    measured["classic"] = copy.deepcopy(measured["modern"])
    with pytest.raises(ValueError, match="G-SEP"):
        assert_separated(measured, spec)


@pytest.mark.parametrize("ppem", range(480, 521, 2))
def test_built_pilot_stays_separated(pilot_otfs, ppem):
    measured = {
        style: measure_otf(path, ppem=ppem) for style, path in pilot_otfs.items()
    }
    assert_separated(measured)


def _shifted(path: Path, out: Path, dx: float, dy: float) -> Path:
    font = TTFont(path)
    glyphs = font.getGlyphSet()
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    strings = top.CharStrings
    for name in ("H", "O"):
        pen = T2CharStringPen(glyphs[name].width, glyphs)
        glyphs[name].draw(TransformPen(pen, (1, 0, 0, 1, dx, dy)))
        charstring = pen.getCharString(private=top.Private, globalSubrs=cff.GlobalSubrs)
        strings[name] = charstring
    font.save(out)
    return out


@pytest.mark.parametrize(("dx", "dy"), ((1.0, 0.0), (0.0, 1.0)))
def test_one_unit_shift_barely_moves_the_serif(pilot_otfs, tmp_path, dx, dy):
    # ppem 500 では 1 UPM が半ピクセルちょうどで、1/4 刻みの 16 位相の並べ替えになる。
    # 平均は恒等なので、測り方の残りは見えない。ppem 480 では 0.48 ピクセルで、位相の間に落ちる。
    # 横へ 1 UPM ずらした 1 回のラスタは、コントラストが 0.034、幹が 0.003 動いた。平均の閾値はそれより厳しい。
    path = pilot_otfs["classic"]
    moved = _shifted(path, tmp_path / "moved.otf", dx, dy)
    before = measure_otf(path, ppem=480)
    after = measure_otf(moved, ppem=480)
    for axis in ("serif_over_cap", "stem_over_cap"):
        assert abs(after[axis] - before[axis]) <= 0.001
    assert abs(after["contrast"] - before["contrast"]) <= 0.01
