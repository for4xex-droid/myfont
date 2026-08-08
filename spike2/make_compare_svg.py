"""永: prototype 骨格（UPM1000 Y下SVG）と KAGE 骨格を並べて比較。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "prototype"))

from skeletons import char_ei  # noqa: E402

from kage_parser import flatten_glyph, load_dump_index, sample_curve_points  # noqa: E402

OUT = ROOT / "output"


def main() -> None:
    index = load_dump_index(ROOT / "data" / "dump_newest_only.txt")
    flat, _, _ = flatten_glyph("u6c38", index)

    scale_k = 2.5
    pad = 40
    panel = 200 * scale_k
    ox = pad + panel + 40
    w = ox + pad + panel + pad
    h = pad + 40 + panel + 40

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}">',
        '<rect width="100%" height="100%" fill="#f7f3ea"/>',
        f'<text x="{pad}" y="28" font-size="16" font-family="Hiragino Mincho ProN,serif">'
        "永 — KAGE flattened vs prototype skeleton</text>",
        f'<text x="{pad}" y="48" font-size="12" font-family="sans-serif">'
        "Left: GlyphWiki u6c38→u6c38-j | Right: prototype/skeletons.char_ei()</text>",
        f'<rect x="{pad}" y="{pad+30}" width="{panel}" height="{panel}" fill="#fff" stroke="#ccc"/>',
        f'<rect x="{ox}" y="{pad+30}" width="{panel}" height="{panel}" fill="#fff" stroke="#ccc"/>',
        f'<text x="{pad}" y="{pad+24}" font-size="12">KAGE</text>',
        f'<text x="{ox}" y="{pad+24}" font-size="12">prototype</text>',
    ]
    y0 = pad + 30
    for s in flat:
        pts = sample_curve_points(s.points, 16)
        d = "M " + " L ".join(
            f"{pad + x * scale_k:.1f},{y0 + y * scale_k:.1f}" for x, y in pts
        )
        col = "#0b5fff" if s.stroke_type != 1 else "#222"
        parts.append(
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linecap="round"/>'
        )

    def ppt(x: float, y: float) -> tuple[float, float]:
        return ox + x * panel / 1000.0, y0 + y * panel / 1000.0

    for s in char_ei():
        pts = [(p.x, p.y) for p in s.points]
        d = "M " + " L ".join(f"{ppt(x, y)[0]:.1f},{ppt(x, y)[1]:.1f}" for x, y in pts)
        parts.append(
            f'<path d="{d}" fill="none" stroke="#b00020" stroke-width="2.5" stroke-linecap="round"/>'
        )

    parts.append(
        f'<text x="{pad}" y="{h - 12}" font-size="11">'
        "写像可能性: 点列＋type/tag は対応可能。座標系は KAGE200(Y↓)→UPM1000(Y↑) 変換が必須。"
        "</text>"
    )
    parts.append("</svg>")
    path = OUT / "compare_ei_kage_vs_prototype.svg"
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
