"""工程5。フィット誤差、極値、丸め後の自己交差、開始点。"""

from __future__ import annotations

import pytest

from engine.latin.build import build_glyph
from engine.latin.load import load_resolved
from engine.latin.outline import _missing_extrema, fit_outline

_GATES = (("modern", "H"), ("modern", "O"), ("pop", "H"), ("pop", "O"))


def _area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    n = len(points)
    for index in range(n):
        nxt = points[(index + 1) % n]
        total += points[index][0] * nxt[1] - nxt[0] * points[index][1]
    return 0.5 * total


@pytest.mark.parametrize(("style", "glyph"), _GATES)
def test_fit_stays_within_the_error_and_keeps_extrema(style, glyph):
    resolved = load_resolved(glyph, style)
    paths = fit_outline(build_glyph(resolved), resolved.style)
    assert paths
    assert all(_missing_extrema(path) == 0 for path in paths)


@pytest.mark.parametrize(("style", "glyph"), _GATES)
def test_fitted_contours_start_at_the_lowest_point_and_wind(style, glyph):
    resolved = load_resolved(glyph, style)
    paths = fit_outline(build_glyph(resolved), resolved.style)
    origins = []
    areas = []
    for path in paths:
        points = path.on_curve_points()
        lowest = min(points, key=lambda point: (point[1], point[0]))
        assert points[0] == lowest
        origins.append(lowest)
        areas.append(_area(points))
    assert origins == sorted(origins, key=lambda point: (point[1], point[0]))
    outer = max(range(len(areas)), key=lambda index: abs(areas[index]))
    assert areas[outer] > 0.0
    assert all(area < 0.0 for index, area in enumerate(areas) if index != outer)
