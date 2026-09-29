"""P-D1 デザインDNAワープ。正本は書かない。つ・づ・っは手直し対象。"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "diverge_dna.py"
    spec = importlib.util.spec_from_file_location("diverge_dna", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
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


def _blob(glyph) -> None:
    pen = glyph.getPen()
    pen.moveTo((200, 100))
    pen.curveTo((350, 80), (500, 200), (480, 350))
    pen.curveTo((400, 500), (200, 480), (120, 300))
    pen.curveTo((80, 180), (100, 120), (200, 100))
    pen.closePath()


def _tiny_png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (2, 2), 200).save(buf, format="PNG")
    return buf.getvalue()


def test_dna_a_is_locked():
    mod = _load()
    d = mod.DNA_A
    assert d.futokoro == 0.08
    assert d.gravity == 0.92
    assert d.balance == 1.08
    assert d.tension == 1.06
    assert mod.STEM_PASSES == 2


def test_fill_widths_interpolates_gap():
    mod = _load()
    raw = [80.0, None, None, 100.0]
    out = mod._fill_widths(raw)
    assert out[0] == 80.0
    assert out[3] == 100.0
    assert out[1] is not None and 80.0 < out[1] < 100.0


def test_hand_fix_is_arc_only():
    mod = _load()
    assert mod.HAND_FIX == frozenset("つづっ")


def test_warp_changes_points_keeps_counts():
    from ufoLib2 import Font

    mod = _load()
    font = Font()
    g = font.newGlyph("uni3064")
    _blob(g)
    before = [(p.x, p.y) for c in g for p in c]
    n_contours = len(g)
    n_pts = sum(len(c) for c in g)
    mod.warp_glyph(g, mod.DNA_A)
    after = [(p.x, p.y) for c in g for p in c]
    assert len(g) == n_contours
    assert sum(len(c) for c in g) == n_pts
    assert after != before


def test_warp_is_deterministic():
    from ufoLib2 import Font

    mod = _load()
    a = Font().newGlyph("a")
    b = Font().newGlyph("b")
    _blob(a)
    _blob(b)
    mod.warp_glyph(a, mod.DNA_A)
    mod.warp_glyph(b, mod.DNA_A)
    assert [(p.x, p.y) for c in a for p in c] == [(p.x, p.y) for c in b for p in c]


def test_warp_empty_is_noop():
    from ufoLib2 import Font

    mod = _load()
    g = Font().newGlyph("empty")
    g.width = 1000
    mod.warp_glyph(g, mod.DNA_A)
    assert len(g) == 0


def test_apply_writes_work_not_dest(tmp_path: Path):
    from fontTools.misc.transform import Transform
    from ufoLib2 import Font
    from ufoLib2.objects.image import Image

    dest = tmp_path / "dest.ufo"
    df = Font()
    dg = df.newGlyph("uni3064")
    dg.width = 1037
    dg.unicodes = [0x3064]
    _blob(dg)
    dest_pts = [(p.x, p.y) for c in dg for p in c]
    df.save(dest)

    work = tmp_path / "つ.ufo"
    wf = Font()
    wg = wf.newGlyph("uni3064")
    wg.width = 1000
    wg.unicodes = [0x3064]
    wf.images["つ_guide_ipaex.png"] = _tiny_png()
    wg.image = Image(
        fileName="つ_guide_ipaex.png",
        transformation=Transform(1, 0, 0, 1, 0, -120),
    )
    wf.save(work)

    mod = _load()
    action = mod.apply_one(Font.open(dest), work, "つ", mod.DNA_A)
    assert action == "warped"

    dest_after = Font.open(dest)
    assert [(p.x, p.y) for c in dest_after["uni3064"] for p in c] == dest_pts

    out = Font.open(work)
    work_pts = [(p.x, p.y) for c in out["uni3064"] for p in c]
    assert work_pts != dest_pts
    assert len(out["uni3064"]) == 1
    assert out["uni3064"].width == 1037
    assert out["uni3064"].image is not None
    assert out["uni3064"].image.fileName == "つ_guide_ipaex.png"


def test_apply_refuses_empty_dest(tmp_path: Path):
    from ufoLib2 import Font

    dest = tmp_path / "dest.ufo"
    df = Font()
    g = df.newGlyph("uni3064")
    g.width = 1000
    df.save(dest)
    work = tmp_path / "つ.ufo"
    Font().save(work)
    mod = _load()
    try:
        mod.apply_one(Font.open(dest), work, "つ", mod.DNA_A)
    except RuntimeError as e:
        assert "no contours" in str(e)
    else:
        raise AssertionError("expected refuse")


def _bar(glyph) -> None:
    pen = glyph.getPen()
    pen.moveTo((100, 200))
    pen.lineTo((500, 200))
    pen.lineTo((500, 280))
    pen.lineTo((100, 280))
    pen.closePath()


def test_preserve_stem_moves_and_keeps_width():
    from ufoLib2 import Font

    mod = _load()
    g = Font().newGlyph("bar")
    _bar(g)
    before = [mod._opposite_width([(p.x, p.y) for p in c], i) for c in g for i, _p in enumerate(c)]
    before = [w for w in before if w is not None and 40 < w < 120]
    assert before
    mid = sum(before) / len(before)
    n_pts = sum(len(c) for c in g)
    pts0 = [(p.x, p.y) for c in g for p in c]
    mod.warp_preserve_stem(g, mod.DNA_A)
    assert sum(len(c) for c in g) == n_pts
    assert [(p.x, p.y) for c in g for p in c] != pts0
    after = [mod._opposite_width([(p.x, p.y) for p in c], i) for c in g for i, _p in enumerate(c)]
    after = [w for w in after if w is not None and 20 < w < 160]
    assert after
    assert abs(sum(after) / len(after) - mid) < 12


def test_apply_preserve_stem_flag(tmp_path: Path):
    from ufoLib2 import Font

    dest = tmp_path / "dest.ufo"
    df = Font()
    dg = df.newGlyph("uni3064")
    dg.width = 1000
    dg.unicodes = [0x3064]
    _bar(dg)
    df.save(dest)
    work = tmp_path / "つ.ufo"
    Font().save(work)
    mod = _load()
    action = mod.apply_one(Font.open(dest), work, "つ", mod.DNA_A, preserve_stem=True)
    assert action == "warped-stem-pin"


def _rect_with_mids(glyph, x0: float, y0: float, x1: float, y1: float) -> None:
    """各辺に中点がある矩形。4点だけだと全部が角になりピンが無効になる。"""
    pen = glyph.getPen()
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    pen.moveTo((x0, y0))
    pen.lineTo((mx, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, my))
    pen.lineTo((x1, y1))
    pen.lineTo((mx, y1))
    pen.lineTo((x0, y1))
    pen.lineTo((x0, my))
    pen.closePath()


def test_terminal_weights_pin_corners_not_mids():
    mod = _load()
    poly = [
        (100.0, 80.0),
        (200.0, 80.0),
        (300.0, 80.0),
        (300.0, 180.0),
        (300.0, 280.0),
        (200.0, 280.0),
        (100.0, 280.0),
        (100.0, 180.0),
    ]
    w = mod._terminal_weights(poly)
    assert len(w) == 8
    corners = [w[0], w[2], w[4], w[6]]
    mids = [w[1], w[3], w[5], w[7]]
    assert max(corners) < min(mids)
    assert max(corners) < 0.35
    assert min(mids) > 0.65


def test_four_point_rect_does_not_freeze():
    mod = _load()
    poly = [(100.0, 200.0), (500.0, 200.0), (500.0, 280.0), (100.0, 280.0)]
    w = mod._terminal_weights(poly)
    assert all(x == 1.0 for x in w)


def test_pin_terminals_holds_corners_moves_body():
    from ufoLib2 import Font

    mod = _load()
    g = Font().newGlyph("rect")
    _rect_with_mids(g, 100, 80, 300, 280)
    pts0 = [(p.x, p.y) for c in g for p in c]
    mod.warp_glyph(g, mod.DNA_A, pin_terminals=True)
    pts1 = [(p.x, p.y) for c in g for p in c]
    assert pts1 != pts0
    # 下辺中点は gravity が ymin に貼り付く。右辺中点（index 3）で胴の移動を見る
    corner_d = math.hypot(pts1[0][0] - pts0[0][0], pts1[0][1] - pts0[0][1])
    mid_d = math.hypot(pts1[3][0] - pts0[3][0], pts1[3][1] - pts0[3][1])
    assert mid_d > corner_d * 1.4
    assert mid_d > 1.0


def test_stem_plus_pin_keeps_mid_width():
    from ufoLib2 import Font

    mod = _load()
    g = Font().newGlyph("bar")
    _rect_with_mids(g, 100, 200, 500, 280)
    poly0 = [(p.x, p.y) for c in g for p in c]
    mid_i = 1
    w0 = mod._opposite_width(poly0, mid_i)
    assert w0 is not None and 40 < w0 < 120
    mod.warp_preserve_stem(g, mod.DNA_A, pin_terminals=True)
    poly1 = [(p.x, p.y) for c in g for p in c]
    assert poly1 != poly0
    w1 = mod._opposite_width(poly1, mid_i)
    assert w1 is not None
    assert abs(w1 - w0) < 16


def test_apply_stem_pins_by_default(tmp_path: Path):
    from ufoLib2 import Font

    dest = tmp_path / "dest.ufo"
    df = Font()
    dg = df.newGlyph("uni3064")
    dg.width = 1000
    dg.unicodes = [0x3064]
    _bar(dg)
    df.save(dest)
    work = tmp_path / "つ.ufo"
    Font().save(work)
    mod = _load()
    action = mod.apply_one(Font.open(dest), work, "つ", mod.DNA_A, preserve_stem=True)
    assert action == "warped-stem-pin"


def test_dry_run_does_not_write(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    dest = tmp_path / "dest.ufo"
    df = Font()
    dg = df.newGlyph("uni3064")
    dg.width = 1000
    dg.unicodes = [0x3064]
    _square(dg, (100, 80), 200)
    df.save(dest)
    work = tmp_path / "つ.ufo"
    Font().save(work)
    before = (work / "glyphs" / "contents.plist").read_bytes()

    mod = _load()
    monkeypatch.setattr(mod, "DEFAULT_DEST", dest)
    monkeypatch.setattr(mod, "DEFAULT_SRC_ROOT", tmp_path)
    rc = mod.main(["つ"])
    assert rc == 0
    assert (work / "glyphs" / "contents.plist").read_bytes() == before
    dest_pts = [(p.x, p.y) for c in Font.open(dest)["uni3064"] for p in c]
    assert dest_pts[0] == (100.0, 80.0)
