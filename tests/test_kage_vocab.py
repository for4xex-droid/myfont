"""KAGE 語彙カタログ。座標・輪郭は持たない（掟9・11・12b）。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "kage_vocab.py"
    spec = importlib.util.spec_from_file_location("kage_vocab", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_vocab_has_no_coordinates():
    mod = _load()
    raw = mod.load_vocab()
    blob = str(raw).lower()
    for banned in ("outline", "contour", "points", "x:", "y:", "cubic", "bezier"):
        assert banned not in blob
    assert "start_tags" in raw
    assert "end_tags" in raw
    assert raw["schema"] == "mymincho.kage_vocab.v1"
    assert raw["coordinates"] is False


def test_map_end_tags():
    mod = _load()
    assert mod.map_end_tag(2, "start") == "uchikomi"
    assert mod.map_end_tag(2, "end") == "uroko"
    assert mod.map_end_tag(7, "end") == "tome"
    assert mod.map_end_tag(4, "end") == "hane"
    assert mod.map_end_tag(99, "start") == "none"


def test_agrees_with_spike7_tables():
    mod = _load()
    sys.path.insert(0, str(ROOT / "spike7"))
    import kage_mapper  # noqa: E402

    vocab = mod.load_vocab()
    for tag_s, name in vocab["start_tags"].items():
        assert kage_mapper.map_end_tag(int(tag_s), "start").value == name
    for tag_s, name in vocab["end_tags"].items():
        assert kage_mapper.map_end_tag(int(tag_s), "end").value == name


def test_line_types_are_names_only():
    mod = _load()
    kinds = mod.load_vocab()["line_types"]
    assert kinds["1"] == "straight"
    assert kinds["2"] == "curve"
    assert "99" not in kinds
