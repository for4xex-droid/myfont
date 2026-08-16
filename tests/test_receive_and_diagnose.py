"""P-R1 receive と P-Q0 診断の単体。"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _square(glyph, origin: tuple[float, float], size: float) -> None:
    x, y = origin
    pen = glyph.getPen()
    pen.moveTo((x, y))
    pen.lineTo((x + size, y))
    pen.lineTo((x + size, y + size))
    pen.lineTo((x, y + size))
    pen.closePath()


def test_remove_junk_keeps_ink_and_holes():
    from ufoLib2 import Font
    from ufoLib2.objects import Contour, Point

    font = Font()
    g = font.newGlyph("uni305B")
    g.width = 1000
    _square(g, (100, 100), 400)
    hole = Contour()
    hole.append(Point(200, 200, type="line"))
    hole.append(Point(200, 300, type="line"))
    hole.append(Point(300, 300, type="line"))
    hole.append(Point(300, 200, type="line"))
    g.appendContour(hole)
    junk = Contour()
    junk.append(Point(10, 10, type="line"))
    g.appendContour(junk)

    mod = _load("receive_manual")
    removed = mod.remove_junk_contours(g)
    assert len(removed) == 1
    assert removed[0] == 0.0
    assert len(g) == 2
    areas = [mod.signed_area(c) for c in g]
    assert any(a > 0 for a in areas)
    assert any(a < 0 for a in areas)


def test_ensure_manual_uncomments_and_appends(tmp_path: Path):
    mod = _load("receive_manual")
    path = tmp_path / "manual_glyphs.txt"
    path.write_text("# uni305B\nuni3042\n", encoding="utf-8")
    assert mod.ensure_manual_listed(path, "uni305B") == "uncommented"
    assert "uni305B\n" in path.read_text(encoding="utf-8")
    assert "# uni305B" not in path.read_text(encoding="utf-8")
    assert mod.ensure_manual_listed(path, "uni3066") == "appended"
    assert "uni3066" in path.read_text(encoding="utf-8")
    assert mod.ensure_manual_listed(path, "uni3042") == "already"


def test_restore_other_from_head_skips_keep_and_untracked(tmp_path: Path, monkeypatch):
    repo = tmp_path
    (repo / ".git").mkdir()
    ufo = repo / "ufo"
    ufo.mkdir()
    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=(
                    " M ufo/glyphs/uni3042.glif\n"
                    " M ufo/glyphs/uni305B.glif\n"
                    "?? ufo/images/new.png\n"
                ),
                stderr="",
            )
        if cmd[:3] == ["git", "restore", "--source=HEAD"]:
            calls.append(cmd[-1])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    mod = _load("receive_manual")
    restored = mod.restore_other_from_head(
        repo, ufo, {"glyphs/uni305B.glif", "contents.plist"}
    )
    assert calls == ["ufo/glyphs/uni3042.glif"]
    assert restored == ["ufo/glyphs/uni3042.glif"]


def test_receive_restores_other_glifs(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    dest = tmp_path / "MyMincho.ufo"
    font = Font()
    a = font.newGlyph("uni3042")
    a.width = 1000
    a.lib["com.mymincho.manual"] = True
    _square(a, (126, 100), 200)
    se = font.newGlyph("uni305B")
    se.width = 1000
    se.lib["com.mymincho.manual"] = True
    _square(se, (50, 50), 100)
    font.save(dest)

    a_glif = dest / "glyphs" / "uni3042.glif"
    a_head = a_glif.read_text(encoding="utf-8")
    a_glif.write_text(a_head + "<!-- dirty -->\n", encoding="utf-8")

    src_root = tmp_path / "manual_kana"
    src_root.mkdir()
    work = Font()
    wg = work.newGlyph("uni305B")
    wg.width = 1000
    _square(wg, (200, 80), 300)
    work.save(src_root / "せ.ufo")

    manual = tmp_path / "manual_glyphs.txt"
    manual.write_text("# uni305B\n", encoding="utf-8")

    mod = _load("receive_manual")
    seen: dict[str, set[str]] = {}

    def fake_restore(repo, ufo, keep):
        seen["keep"] = set(keep)
        a_glif.write_text(a_head, encoding="utf-8")
        return ["glyphs/uni3042.glif"]

    monkeypatch.setattr(mod, "restore_other_from_head", fake_restore)
    rc = mod.main(
        [
            "せ",
            "--dest",
            str(dest),
            "--src-root",
            str(src_root),
            "--manual",
            str(manual),
            "--force",
            "--no-compile",
            "--no-proofs",
        ]
    )
    assert rc == 0
    assert any("uni305B" in p for p in seen["keep"])
    assert a_glif.read_text(encoding="utf-8") == a_head
    out = Font.open(dest)
    pts = [(p.x, p.y) for p in out["uni305B"][0]]
    assert pts[0][0] == 126.0
    assert out["uni305B"].lib.get("com.mymincho.manual") is True
    assert "uni305B\n" in manual.read_text(encoding="utf-8")


def test_receive_missing_char():
    mod = _load("receive_manual")
    assert mod.main(["せせ"]) == 2


def test_receive_keeps_all_named_chars(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    dest = tmp_path / "MyMincho.ufo"
    font = Font()
    for name, origin in (("uni3065", (50, 50)), ("uni3093", (80, 80))):
        g = font.newGlyph(name)
        g.width = 1000
        g.lib["com.mymincho.manual"] = True
        _square(g, origin, 100)
    font.save(dest)
    manual = tmp_path / "manual_glyphs.txt"
    manual.write_text("uni3065\nuni3093\n", encoding="utf-8")
    mod = _load("receive_manual")
    seen: dict[str, set[str]] = {}

    def fake_restore(repo, ufo, keep):
        seen["keep"] = set(keep)
        return []

    monkeypatch.setattr(mod, "restore_other_from_head", fake_restore)
    assert (
        mod.main(
            [
                "づ",
                "ん",
                "--dest",
                str(dest),
                "--src-root",
                str(tmp_path / "none"),
                "--manual",
                str(manual),
                "--no-compile",
                "--no-proofs",
            ]
        )
        == 0
    )
    assert any("uni3065" in p for p in seen["keep"])
    assert any("uni3093" in p for p in seen["keep"])


def test_receive_refuses_non_ufo(tmp_path: Path):
    dest = tmp_path / "not_ufo"
    dest.mkdir()
    mod = _load("receive_manual")
    assert mod.main(["せ", "--dest", str(dest), "--no-compile", "--no-proofs"]) == 2


def test_receive_skips_work_when_dest_drawn(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    dest = tmp_path / "MyMincho.ufo"
    font = Font()
    se = font.newGlyph("uni305B")
    se.width = 1000
    se.lib["com.mymincho.manual"] = True
    _square(se, (50, 50), 100)
    font.save(dest)

    src_root = tmp_path / "manual_kana"
    src_root.mkdir()
    work = Font()
    wg = work.newGlyph("uni305B")
    wg.width = 1000
    _square(wg, (200, 80), 300)
    work.save(src_root / "せ.ufo")
    manual = tmp_path / "manual_glyphs.txt"
    manual.write_text("uni305B\n", encoding="utf-8")

    mod = _load("receive_manual")
    monkeypatch.setattr(mod, "restore_other_from_head", lambda *a, **k: [])
    assert (
        mod.main(
            [
                "せ",
                "--dest",
                str(dest),
                "--src-root",
                str(src_root),
                "--manual",
                str(manual),
                "--no-compile",
                "--no-proofs",
            ]
        )
        == 0
    )
    out = Font.open(dest)
    ink = max(p.x for p in out["uni305B"][0]) - min(p.x for p in out["uni305B"][0])
    assert ink == 100


def test_receive_force_replaces_dest(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    dest = tmp_path / "MyMincho.ufo"
    font = Font()
    se = font.newGlyph("uni305B")
    se.width = 1000
    se.lib["com.mymincho.manual"] = True
    _square(se, (50, 50), 100)
    font.save(dest)

    src_root = tmp_path / "manual_kana"
    src_root.mkdir()
    work = Font()
    wg = work.newGlyph("uni305B")
    wg.width = 1000
    _square(wg, (200, 80), 300)
    work.save(src_root / "せ.ufo")
    manual = tmp_path / "manual_glyphs.txt"
    manual.write_text("uni305B\n", encoding="utf-8")

    mod = _load("receive_manual")
    monkeypatch.setattr(mod, "restore_other_from_head", lambda *a, **k: [])
    assert (
        mod.main(
            [
                "せ",
                "--dest",
                str(dest),
                "--src-root",
                str(src_root),
                "--manual",
                str(manual),
                "--force",
                "--no-compile",
                "--no-proofs",
            ]
        )
        == 0
    )
    out = Font.open(dest)
    ink = max(p.x for p in out["uni305B"][0]) - min(p.x for p in out["uni305B"][0])
    assert ink == 300


def test_diagnose_groups_band_and_points(tmp_path: Path):
    from ufoLib2 import Font

    dest = tmp_path / "in.ufo"
    font = Font()
    a = font.newGlyph("uni3042")
    a.width = 400
    a.lib["com.mymincho.manual"] = True
    _square(a, (10, 10), 50)
    se = font.newGlyph("uni305B")
    se.width = 874
    se.lib["com.mymincho.manual"] = True
    _square(se, (126, 100), 630)
    font.save(dest)

    mod = _load("diagnose_manual_kana")
    rows = mod.ufo_rows(dest, chars="あせ")
    by_ch = {r["char"]: r for r in rows}
    assert "帯外" in by_ch["あ"]["groups"]
    assert "帯外" not in by_ch["せ"]["groups"]
    assert by_ch["せ"]["oncurve"] == 4
    assert by_ch["せ"]["contours"] == 1

    out = tmp_path / "q0.md"
    text = mod.render_table(rows)
    out.write_text(text, encoding="utf-8")
    assert "あ" in text
    assert "帯外" in text
    assert "kana_targets" not in text.lower() or "未凍結" in text
    assert "low_confidence" in text
    assert "stemVem" in text


def test_diagnose_ru_is_known_exception():
    mod = _load("diagnose_manual_kana")
    row = {
        "char": "る",
        "oncurve": 65,
        "contours": 1,
        "in_band": True,
        "small_flag": False,
    }
    assert mod.classify(row) == ["既知例外"]
    row["char"] = "そ"
    row["oncurve"] = 57
    assert mod.classify(row) == ["既知例外"]
    row["char"] = "ん"
    row["oncurve"] = 50
    assert "節点過多" in mod.classify(row)
