"""G-SEP: 凍結した4様式の距離を下回ると失敗する。"""

from __future__ import annotations

import copy

import pytest

from engine.latin.gate import assert_separated, load_separation


def test_frozen_pilot_meets_its_own_threshold():
    spec = load_separation()
    assert spec["nearest_distance"] == pytest.approx(1.030593912763502)
    assert spec["min_distance"] == pytest.approx(1.023287944059543)
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
