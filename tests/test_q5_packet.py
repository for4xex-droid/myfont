"""P-Q5 内部再確認パック。P1黄金(before)と現行(after)。合否は人が書く。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "make_q5_packet.py"
    spec = importlib.util.spec_from_file_location("make_q5_packet", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _png(path: Path, shade: int) -> None:
    from PIL import Image

    Image.new("L", (8, 8), shade).save(path)


def test_pair_order_is_deterministic():
    mod = _load()
    a = mod.pair_order(1, "ui_kana")
    b = mod.pair_order(1, "ui_kana")
    c = mod.pair_order(2, "ui_kana")
    assert a == b
    assert set(a.values()) == {"before", "after"}
    assert a["A"] != a["B"]
    assert set(c.values()) == {"before", "after"}


def test_write_pair_copies_bytes(tmp_path: Path):
    mod = _load()
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _png(before, 10)
    _png(after, 200)
    dest = tmp_path / "ui_kana"
    order = {"A": "after", "B": "before"}
    mod.write_pair(before, after, dest, order)
    assert (dest / "A.png").read_bytes() == after.read_bytes()
    assert (dest / "B.png").read_bytes() == before.read_bytes()


def test_build_packet_seals_before_after(tmp_path: Path):
    mod = _load()
    golden = tmp_path / "golden"
    after_dir = tmp_path / "after"
    out = tmp_path / "q5"
    golden.mkdir()
    after_dir.mkdir()
    for face in ("ui_kana", "hud_kana"):
        _png(golden / f"{face}.png", 30)
        _png(after_dir / f"{face}.png", 180)
    sealed = mod.build_packet(golden, after_dir, out, seed=20260817)
    assert sealed["seed"] == 20260817
    assert set(sealed["faces"]) == {"ui", "hud"}
    for face, order in sealed["faces"].items():
        assert set(order.values()) == {"before", "after"}
        assert (out / face / "A.png").is_file()
    text = json.dumps(sealed)
    assert "MyMincho" not in text
    assert "IPAex" not in text
    assert "ipaex" not in text


def test_evaluator_copy_has_no_font_names():
    ev = (ROOT / "proofs" / "q5" / "EVALUATOR.txt").read_text(encoding="utf-8")
    sheet = (ROOT / "proofs" / "q5" / "SHEET.txt").read_text(encoding="utf-8")
    blob = ev + sheet
    assert "MyMincho" not in blob
    assert "IPAex" not in blob
    assert "SEALED" in ev
    assert "使える" in sheet
    assert "粗い" in sheet
