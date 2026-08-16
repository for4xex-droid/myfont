"""P-E1 残りひらがなの集合。ゐゑゔは含めない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "prepare_e1_kana.py"
    spec = importlib.util.spec_from_file_location("prepare_e1_kana", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_e1_list_excludes_drawn_and_historic():
    mod = _load()
    chars = mod.e1_chars()
    assert "だ" in chars
    assert "わ" in chars
    assert "ぽ" in chars
    assert "ぁ" in chars
    for ch in "あいうえおかきくけこさしすせそたちつてとのはひほまめやるりをんっがじづぞぼ":
        assert ch not in chars
    for ch in "ゐゑゔゕゖ":
        assert ch not in chars
    assert len(chars) == 44
    assert len(set(chars)) == 44


def test_write_ufo_refuses_existing(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    mod = _load()
    monkeypatch.setattr(mod, "UFO_ROOT", tmp_path)
    dest = tmp_path / "だ.ufo"
    Font().save(dest)
    try:
        mod.write_ufo("だ", b"", "x.png")
    except FileExistsError:
        return
    raise AssertionError("expected refuse overwrite")
