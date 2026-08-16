"""P-Q3 濁点計測と端物シート。合否ゲートではない。"""

from __future__ import annotations

import importlib.util
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


def test_dakuten_picks_upper_right_small_pair():
    from ufoLib2 import Font
    from ufoLib2.objects import Contour, Point

    font = Font()
    g = font.newGlyph("uni304C")
    g.width = 1000
    _square(g, (100, 100), 400)
    _square(g, (520, 520), 80)
    _square(g, (780, 720), 50)
    _square(g, (850, 680), 45)
    hole = Contour()
    hole.append(Point(200, 200, type="line"))
    hole.append(Point(200, 280, type="line"))
    hole.append(Point(280, 280, type="line"))
    hole.append(Point(280, 200, type="line"))
    g.appendContour(hole)

    mod = _load("make_q3_sheet")
    marks = mod.pick_dakuten(g)
    assert len(marks) == 2
    xs = sorted(m["cx"] for m in marks)
    assert xs[0] > 750
    assert all(m["area"] > 0 for m in marks)
    assert marks[0]["area"] <= marks[1]["area"]


def test_dakuten_two_small_on_one_body():
    from ufoLib2 import Font

    font = Font()
    g = font.newGlyph("uni3058")
    g.width = 1000
    _square(g, (120, 80), 500)
    _square(g, (700, 700), 40)
    _square(g, (760, 650), 36)
    mod = _load("make_q3_sheet")
    marks = mod.pick_dakuten(g)
    assert len(marks) == 2
    assert all(m["max_dim"] <= 40 + 1e-6 for m in marks)


def test_dakuten_incomplete_when_one_positive():
    from ufoLib2 import Font

    font = Font()
    g = font.newGlyph("uni3042")
    g.width = 1000
    _square(g, (100, 100), 200)
    mod = _load("make_q3_sheet")
    assert mod.pick_dakuten(g) == []


def test_classify_contour_and_size():
    mod = _load("make_q3_sheet")
    row = {
        "char": "が",
        "contours": 3,
        "expected_contours": 5,
        "marks": [
            {"max_dim": 40.0, "area": 1000.0},
            {"max_dim": 42.0, "area": 1100.0},
        ],
        "pair_max_dim": 42.0,
    }
    assert "輪郭数ずれ" in mod.classify_dakuten(row, median_max_dim=41.0)
    row["contours"] = 5
    assert "輪郭数ずれ" not in mod.classify_dakuten(row, median_max_dim=41.0)
    row["pair_max_dim"] = 80.0
    row["marks"][1]["max_dim"] = 80.0
    assert "濁点サイズ外れ" in mod.classify_dakuten(row, median_max_dim=41.0)


def test_render_table_is_not_a_gate():
    mod = _load("make_q3_sheet")
    rows = [
        {
            "char": "が",
            "name": "uni304C",
            "contours": 5,
            "expected_contours": 5,
            "marks": [
                {"area": 1200.0, "w": 40.0, "h": 50.0, "max_dim": 50.0},
                {"area": 1100.0, "w": 38.0, "h": 48.0, "max_dim": 48.0},
            ],
            "pair_area": 2300.0,
            "pair_max_dim": 50.0,
            "groups": [],
        }
    ]
    text = mod.render_table(rows)
    assert "合否ではない" in text
    assert "が" in text
    assert "kana_targets" not in text.lower()
    assert "エンジン端物" in text


def _tiny_png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (2, 2), 200).save(buf, format="PNG")
    return buf.getvalue()


def test_export_copies_outline_keeps_image(tmp_path: Path):
    from ufoLib2 import Font
    from fontTools.misc.transform import Transform
    from ufoLib2.objects.image import Image

    dest = tmp_path / "dest.ufo"
    df = Font()
    dg = df.newGlyph("uni304C")
    dg.width = 1121
    dg.unicodes = [0x304C]
    _square(dg, (126, 100), 200)
    df.save(dest)

    work = tmp_path / "が.ufo"
    wf = Font()
    wg = wf.newGlyph("uni304C")
    wg.width = 1000
    wg.unicodes = [0x304C]
    wf.images["が_guide_ipaex.png"] = _tiny_png()
    wg.image = Image(
        fileName="が_guide_ipaex.png",
        transformation=Transform(1, 0, 0, 1, 0, -120),
    )
    wf.save(work)

    mod = _load("export_manual_work")
    assert mod.export_one(Font.open(dest), work, "が") == "exported"
    out = Font.open(work)
    assert len(out["uni304C"]) == 1
    assert out["uni304C"].width == 1121
    assert out["uni304C"].image is not None
    assert out["uni304C"].image.fileName == "が_guide_ipaex.png"
    assert "が_guide_ipaex.png" in out.images


def test_export_refuses_empty_dest(tmp_path: Path):
    from ufoLib2 import Font

    dest = tmp_path / "dest.ufo"
    df = Font()
    g = df.newGlyph("uni304C")
    g.width = 1000
    df.save(dest)
    work = tmp_path / "が.ufo"
    Font().save(work)
    mod = _load("export_manual_work")
    try:
        mod.export_one(Font.open(dest), work, "が")
    except RuntimeError as e:
        assert "no contours" in str(e)
    else:
        raise AssertionError("expected refuse")
