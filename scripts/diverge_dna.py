#!/usr/bin/env python3
"""デザインDNAワープ（P-D1）。IPAex骨格から離す。正本は書かない。

既定は dry-run。書くとき --apply（作業 UFO のみ）。
つ・づ・っ は骨格だけ動かし、局所幅を保つ（--stem）。
--stem のとき端物（角・止め）は既定で固定する（Igarashi 2010 の皮膚固定）。

例:
  engine/.venv/bin/python scripts/diverge_dna.py
  engine/.venv/bin/python scripts/diverge_dna.py --apply
  engine/.venv/bin/python scripts/diverge_dna.py つ づ っ --apply --stem
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_SRC_ROOT = ROOT / "fonts_out" / "manual_kana"
P1_DRAWN = "あいうえおかきくけこさしすせそたちつてとのはひほまめやるりをんっがじづぞぼ"
HAND_FIX = frozenset("つづっ")
MANUAL_LIB = "com.mymincho.manual"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import receive_manual  # noqa: E402


class DNA:
    def __init__(self, futokoro: float, gravity: float, balance: float, tension: float) -> None:
        self.futokoro = futokoro
        self.gravity = gravity
        self.balance = balance
        self.tension = tension


# A 上品・締まり（2026-08-17 試作で固定）
DNA_A = DNA(futokoro=0.08, gravity=0.92, balance=1.08, tension=1.06)
# つ系は DNA A を幅維持で2回（1回だと IoU が戻る。強い1回は欠ける）
STEM_PASSES = 2
# 端物ピン: 輪郭周長のこの割合以内を固定。半分以上が種ならピンしない
PIN_RADIUS_FRAC = 0.14
PIN_MIN_SEEDS = 2
PIN_MAX_SEEDS = 8
PIN_SEED_SHARE_MAX = 0.5
PIN_SHARP_RAD = 0.45  # ≈26°。これ以上を端物種にする


def _is_oncurve(point) -> bool:
    return getattr(point, "type", None) not in (None, "offcurve")


def _unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return 0.0, 0.0
    return dx / n, dy / n


def _inward_normal(poly: list[tuple[float, float]], i: int) -> tuple[float, float]:
    n = len(poly)
    ax, ay = poly[(i - 1) % n]
    cx, cy = poly[(i + 1) % n]
    tx, ty = _unit(cx - ax, cy - ay)
    return -ty, tx


def _seg_intersect(ox, oy, dx, dy, ax, ay, bx, by, min_t=1.5):
    vx, vy = bx - ax, by - ay
    det = dx * vy - dy * vx
    if abs(det) < 1e-9:
        return None
    t = ((ax - ox) * vy - (ay - oy) * vx) / det
    u = ((ax - ox) * dy - (ay - oy) * dx) / det
    if t >= min_t and 0.0 <= u <= 1.0:
        return t
    return None


def _opposite_width(poly: list[tuple[float, float]], i: int) -> float | None:
    ox, oy = poly[i]
    nx, ny = _inward_normal(poly, i)
    if nx == 0.0 and ny == 0.0:
        return None
    best = None
    n = len(poly)
    for j in range(n):
        if j in ((i - 1) % n, i):
            continue
        hit = _seg_intersect(ox, oy, nx, ny, *poly[j], *poly[(j + 1) % n])
        if hit is None:
            continue
        if best is None or hit < best:
            best = hit
    return best


def _field_fn(glyph, dna: DNA):
    oncurve = [(p.x, p.y) for c in glyph for p in c if _is_oncurve(p)]
    if not oncurve:
        return None
    xs = [p[0] for p in oncurve]
    ys = [p[1] for p in oncurve]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    ymin, ymax = min(ys), max(ys)
    h = max(ymax - ymin, 1.0)
    w = max(max(abs(x - cx) for x in xs), 1.0)
    rmax = max(math.hypot(x - cx, y - cy) for x, y in oncurve) or 1.0

    def field(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - cx, y - cy
        r = math.hypot(dx, dy)
        t = min(r / rmax, 1.0)
        s = 1.0 + dna.futokoro * math.sin(math.pi * t)
        x, y = cx + dx * s, cy + dy * s
        ty = min(max((y - ymin) / h, 0.0), 1.0)
        y = ymin + h * (ty ** dna.gravity)
        dx = x - cx
        x = cx + math.copysign(w * ((abs(dx) / w) ** dna.balance), dx)
        return x, y

    return field


def _turn_abs(poly: list[tuple[float, float]], i: int) -> float:
    n = len(poly)
    ax, ay = poly[(i - 1) % n]
    bx, by = poly[i]
    cx, cy = poly[(i + 1) % n]
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = cx - bx, cy - by
    n1, n2 = math.hypot(v1x, v1y), math.hypot(v2x, v2y)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    v1x, v1y, v2x, v2y = v1x / n1, v1y / n1, v2x / n2, v2y / n2
    return abs(math.atan2(v1x * v2y - v1y * v2x, v1x * v2x + v1y * v2y))


def _contour_dist(n: int, i: int, j: int) -> int:
    d = abs(i - j)
    return min(d, n - d)


def _terminal_weights(poly: list[tuple[float, float]]) -> list[float]:
    """角・止め付近=0、胴=1。点が少なく種が過半数ならピンしない。"""
    n = len(poly)
    if n < 6:
        return [1.0] * n
    angles = [_turn_abs(poly, i) for i in range(n)]
    ordered = sorted(range(n), key=lambda i: angles[i], reverse=True)
    seeds = [i for i in ordered if angles[i] >= PIN_SHARP_RAD][:PIN_MAX_SEEDS]
    if len(seeds) < PIN_MIN_SEEDS:
        seeds = ordered[:PIN_MIN_SEEDS]
    if len(seeds) / n > PIN_SEED_SHARE_MAX:
        return [1.0] * n
    radius = max(1, int(n * PIN_RADIUS_FRAC))
    out: list[float] = []
    for i in range(n):
        d = min(_contour_dist(n, i, s) for s in seeds)
        t = min(d / radius, 1.0)
        out.append(t * t * (3.0 - 2.0 * t))
    return out


def _lerp_pts(
    src: list[tuple[float, float]],
    dst: list[tuple[float, float]],
    weights: list[float],
) -> list[tuple[float, float]]:
    return [
        (a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1]))
        for a, b, w in zip(src, dst, weights)
    ]


def warp_glyph(glyph, dna: DNA, pin_terminals: bool = False) -> None:
    field = _field_fn(glyph, dna)
    if field is None:
        return
    originals: list[list[tuple[float, float]]] = []
    for contour in glyph:
        originals.append([(p.x, p.y) for p in contour])
        for p in contour:
            p.x, p.y = field(p.x, p.y)

    for contour in glyph:
        pts = list(contour)
        n = len(pts)
        for i, p in enumerate(pts):
            if _is_oncurve(p):
                continue
            nxt, prv = pts[(i + 1) % n], pts[(i - 1) % n]
            anchor = nxt if _is_oncurve(nxt) else prv if _is_oncurve(prv) else None
            if anchor is None:
                continue
            p.x = anchor.x + (p.x - anchor.x) * dna.tension
            p.y = anchor.y + (p.y - anchor.y) * dna.tension

    if not pin_terminals:
        return
    for contour, src in zip(glyph, originals):
        dst = [(p.x, p.y) for p in contour]
        pinned = _lerp_pts(src, dst, _terminal_weights(src))
        for p, (x, y) in zip(contour, pinned):
            p.x, p.y = x, y


def warp_preserve_stem(glyph, dna: DNA, pin_terminals: bool = False) -> None:
    """骨格（反対側との中点）だけ場で動かし、元の局所幅で戻す。"""
    field = _field_fn(glyph, dna)
    if field is None:
        return
    for contour in glyph:
        poly = [(p.x, p.y) for p in contour]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        # 濁点など小さい輪郭は通常ワープ
        if max(xs) - min(xs) < 80 or max(ys) - min(ys) < 80:
            for p in contour:
                p.x, p.y = field(p.x, p.y)
            continue
        raw_w = [_opposite_width(poly, i) for i in range(len(poly))]
        widths = _fill_widths(raw_w)
        planned: list[tuple[float, float]] = []
        for i, (x, y) in enumerate(poly):
            width = widths[i]
            if width is None:
                planned.append(field(x, y))
                continue
            nx, ny = _inward_normal(poly, i)
            mx, my = x + nx * width * 0.5, y + ny * width * 0.5
            mx2, my2 = field(mx, my)
            hx, hy = field(mx + nx, my + ny)
            n2x, n2y = _unit(hx - mx2, hy - my2)
            if n2x == 0.0 and n2y == 0.0:
                n2x, n2y = nx, ny
            planned.append((mx2 - n2x * width * 0.5, my2 - n2y * width * 0.5))
        if pin_terminals:
            planned = _lerp_pts(poly, planned, _terminal_weights(poly))
        for p, (x, y) in zip(contour, planned):
            p.x, p.y = x, y


def _fill_widths(raw: list[float | None]) -> list[float | None]:
    """欠測を輪郭まわりで線形補間。全部欠けるならそのまま。"""
    n = len(raw)
    known = [i for i, w in enumerate(raw) if w is not None and 20.0 <= w <= 220.0]
    if not known:
        return list(raw)
    out: list[float | None] = [None] * n
    for i in range(n):
        if i in set(known):
            out[i] = raw[i]
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is None:
            prev = known[-1]
        if nxt is None:
            nxt = known[0]
        if prev == nxt:
            out[i] = raw[prev]
            continue
        if nxt > prev:
            t = (i - prev) / (nxt - prev)
        else:
            span = (n - prev) + nxt
            t = ((i - prev) % n) / span
        out[i] = raw[prev] * (1.0 - t) + raw[nxt] * t
    return out


def apply_one(
    dest_font,
    work_path: Path,
    char: str,
    dna: DNA,
    preserve_stem: bool = False,
    pin_terminals: bool | None = None,
) -> str:
    from ufoLib2 import Font

    name = receive_manual.uni_name(char)
    if name not in dest_font or len(dest_font[name]) == 0:
        raise RuntimeError(f"{name} has no contours in dest")
    if not receive_manual.is_ufo(work_path):
        raise RuntimeError(f"not a UFO: {work_path}")

    work = Font.open(work_path)
    if name not in work:
        wg = work.newGlyph(name)
        wg.unicodes = [ord(char)]
    else:
        wg = work[name]
    image = wg.image
    wg.clearContours()
    for contour in dest_font[name]:
        wg.appendContour(contour)
    wg.width = dest_font[name].width
    wg.unicodes = [ord(char)]
    wg.lib[MANUAL_LIB] = True
    if image is not None:
        wg.image = image
    if pin_terminals is None:
        pin_terminals = bool(preserve_stem)
    if preserve_stem:
        for _ in range(STEM_PASSES):
            warp_preserve_stem(wg, dna, pin_terminals=pin_terminals)
        action = "warped-stem-pin" if pin_terminals else "warped-stem"
    else:
        warp_glyph(wg, dna, pin_terminals=pin_terminals)
        action = "warped-pin" if pin_terminals else "warped"
    work.save()
    return action


def _parse_chars(raws: list[str]) -> list[str]:
    chars: list[str] = []
    for raw in raws:
        if len(raw) != 1:
            raise ValueError(f"expected one char, got {raw!r}")
        if raw not in chars:
            chars.append(raw)
    return chars


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Warp dest outlines into work UFOs (DNA A)")
    ap.add_argument("chars", nargs="*", help="hiragana; default is P1 37")
    ap.add_argument("--apply", action="store_true", help="write work UFOs (never dest)")
    ap.add_argument(
        "--stem",
        action="store_true",
        help="つ・づ・っ は骨格ワープ＋幅維持。他字は通常ワープ",
    )
    pin = ap.add_mutually_exclusive_group()
    pin.add_argument(
        "--pin-ends",
        dest="pin_ends",
        action="store_true",
        default=None,
        help="角・止めを固定。--stem では既定オン",
    )
    pin.add_argument(
        "--no-pin-ends",
        dest="pin_ends",
        action="store_false",
        help="端物もワープする",
    )
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--src-root", type=Path, default=DEFAULT_SRC_ROOT)
    args = ap.parse_args(argv)

    try:
        chars = _parse_chars(args.chars) if args.chars else list(P1_DRAWN)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not receive_manual.is_ufo(args.dest):
        print(f"error: not a UFO: {args.dest}", file=sys.stderr)
        return 2

    from ufoLib2 import Font

    try:
        dest = Font.open(args.dest)
        for char in chars:
            name = receive_manual.uni_name(char)
            if name not in dest or len(dest[name]) == 0:
                print(f"{char} {name} skip (empty dest)", file=sys.stderr)
                continue
            use_stem = args.stem and char in HAND_FIX
            note = " 幅維持" if use_stem else ""
            if use_stem and args.pin_ends is not False:
                note += " 端物固定"
            if args.apply:
                work = args.src_root / f"{char}.ufo"
                action = apply_one(
                    dest,
                    work,
                    char,
                    DNA_A,
                    preserve_stem=use_stem,
                    pin_terminals=args.pin_ends,
                )
                glyph = Font.open(work)[name]
            else:
                action = "dry-run"
                glyph = dest[name]
            print(
                f"{char} {name} {action}{note} contours={len(glyph)} "
                f"oncurve={receive_manual.oncurve_count(glyph)}"
            )
    except Exception as e:
        print(f"error: diverge failed: {e}", file=sys.stderr)
        return 1

    if args.apply:
        print("dest は未変更。つ系は --stem なら幅維持。確認してから receive。")
    else:
        print("dry-run。書くときは --apply（作業 UFO のみ）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
