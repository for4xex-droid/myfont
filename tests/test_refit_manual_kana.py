"""P-Q2 手描き cubic 再フィット。し・く・っは触らない。fail-closed。"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "refit_manual_kana.py"
    spec = importlib.util.spec_from_file_location("refit_manual_kana", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _dense_oval(n: int = 80):
    from ufoLib2 import Font

    font = Font()
    g = font.newGlyph("uni3042")
    g.width = 1000
    g.lib["com.mymincho.manual"] = True
    pen = g.getPen()
    pts = [
        (500 + 220 * math.cos(t), 400 + 160 * math.sin(t))
        for t in [i * 2 * math.pi / n for i in range(n)]
    ]
    pen.moveTo(pts[0])
    for p in pts[1:]:
        pen.lineTo(p)
    pen.closePath()
    return font, g


def test_refuses_protected_chars():
    mod = _load()
    for ch in "しくっ":
        assert mod.main([ch]) == 2


def test_refit_oval_reduces_points_and_passes_gates(tmp_path: Path):
    from ufoLib2 import Font

    font, _g = _dense_oval(80)
    dest = tmp_path / "in.ufo"
    font.save(dest)
    mod = _load()
    report = mod.refit_glyph(Font.open(dest)["uni3042"], char="あ")
    assert report["ok"] is True
    assert report["contours_after"] == 1
    assert report["oncurve_after"] < report["oncurve_before"]
    assert report["hausdorff"] <= 0.5 + 1e-6
    assert report["holes"] == 0


def test_refit_fail_closed_keeps_original(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    font, _g = _dense_oval(24)
    dest = tmp_path / "in.ufo"
    font.save(dest)
    before = Font.open(dest)["uni3042"]
    n_before = len(before[0])
    mod = _load()

    def boom(*_a, **_k):
        raise ValueError("forced gate")

    monkeypatch.setattr(mod, "fit_closed_contour", boom)
    opened = Font.open(dest)
    report = mod.refit_glyph(opened["uni3042"], char="あ")
    assert report["ok"] is False
    assert len(opened["uni3042"][0]) == n_before


def test_missing_dest(tmp_path: Path):
    mod = _load()
    assert mod.main(["あ", "--dest", str(tmp_path / "nope.ufo")]) == 2
