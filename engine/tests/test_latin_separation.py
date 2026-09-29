"""G-SEP: 凍結した4様式の距離を下回ると失敗する。"""

from __future__ import annotations

import copy

import pytest

from engine.latin.gate import assert_separated, load_separation


def test_frozen_pilot_meets_its_own_threshold():
    spec = load_separation()
    assert spec["min_distance"] == pytest.approx(1.0338284145138559)
    assert_separated(spec["styles"], spec)
    assert ("modern", "classic") in spec["distances"]


def test_collapsed_classic_fails():
    spec = load_separation()
    measured = copy.deepcopy(spec["styles"])
    measured["classic"] = copy.deepcopy(measured["modern"])
    with pytest.raises(ValueError, match="G-SEP"):
        assert_separated(measured, spec)
