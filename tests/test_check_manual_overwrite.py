"""掟13 check_manual_overwrite の fail-open 防止。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "check_manual_overwrite.py"
    spec = importlib.util.spec_from_file_location("check_manual_overwrite", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_requires_a_mode():
    mod = _load()
    assert mod.main([]) == 2


def test_detects_engine_overlap(tmp_path: Path):
    mod = _load()
    manual = tmp_path / "m.txt"
    manual.write_text("uni3042\nuni3044\n", encoding="utf-8")
    engine = tmp_path / "e.txt"
    engine.write_text("uni3042\nuni4E00\n", encoding="utf-8")
    assert mod.main(["--manual", str(manual), "--engine-glyphs", str(engine)]) == 1


def test_no_overlap_ok(tmp_path: Path):
    mod = _load()
    manual = tmp_path / "m.txt"
    manual.write_text("uni3042\n", encoding="utf-8")
    engine = tmp_path / "e.txt"
    engine.write_text("uni4E00\n", encoding="utf-8")
    assert mod.main(["--manual", str(manual), "--engine-glyphs", str(engine)]) == 0
