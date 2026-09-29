"""工程3: mono の半幅、nib の最細方向、role 優先。"""

from __future__ import annotations

import math

import pytest

from engine.latin.pens import Pen, half_width

MONO = Pen("mono", stem=0.13, bar_ratio=0.90, hairline=0.13, theta_deg=0.0)
NIB = Pen("nib", stem=0.16, bar_ratio=0.10, hairline=0.015, theta_deg=0.0)


def test_mono_half_width_ignores_angle_and_thins_bars():
    assert half_width(MONO, "thick", 0.0) == pytest.approx(0.065)
    assert half_width(MONO, "bowl", 1.2) == pytest.approx(0.065)
    assert half_width(MONO, "bar", math.pi / 2) == pytest.approx(0.13 * 0.90 / 2)


def test_nib_is_thinnest_parallel_to_theta_and_thickest_perpendicular():
    thin = half_width(NIB, "bowl", 0.0)
    thick = half_width(NIB, "bowl", math.pi / 2)
    assert thin == pytest.approx(0.015 / 2)
    assert thick == pytest.approx(0.16 / 2)
    assert thin < thick


def test_role_overrides_the_nib_angle():
    along_thin_axis = 0.0
    assert half_width(NIB, "thick", along_thin_axis) == pytest.approx(0.08)
    assert half_width(NIB, "thin", math.pi / 2) == pytest.approx(0.015 / 2)
    assert half_width(NIB, "bar", math.pi / 2) == pytest.approx(0.16 * 0.10 / 2)
