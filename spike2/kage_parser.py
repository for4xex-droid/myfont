"""GlyphWiki KAGE dump / stroke-line parser (spike verification).

Dump 行形式: name | related | data
data 内の筆画は $ 区切り、各筆画は : 区切り。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


# 筆画タイプ（KAGE仕様の主要値）
STROKE_TYPE_NAMES = {
    0: "special",
    1: "straight",  # 直線
    2: "curve",  # 曲線（制御点3）
    3: "bend",  # 折れ
    4: "otsu",  # 乙線
    6: "complex_curve",  # 複曲線（制御点4）
    7: "vertical_sweep",  # 縦払い
    9: "dotish",
    99: "ref",  # 部品参照
}

# 端点形状タグ（列2=始点 / 列3=終点）の代表値。完全列挙ではない。
ENDPOINT_TAG_HINTS = {
    0: "open/none",
    2: "connect_h/uroko-ish",
    4: "hane",
    5: "left_hara_end",
    7: "tome/taper",
    8: "ten_end",
    12: "corner_ur",
    13: "corner_ulish",
    22: "connect_v",
    23: "connect_v_alt",
    24: "hane_alt",
    32: "corner_ul",
}


@dataclass
class DumpEntry:
    name: str
    related: str
    data: str


@dataclass
class KageStroke:
    """1行分の筆画（部品参照含む）。"""

    stroke_type: int
    start_tag: int
    end_tag: int
    coords: List[float] = field(default_factory=list)
    ref_name: Optional[str] = None
    # 部品参照の追加パラメータ（sx, sy, sv 等）
    ref_extra: List[str] = field(default_factory=list)
    raw: str = ""

    @property
    def type_name(self) -> str:
        return STROKE_TYPE_NAMES.get(self.stroke_type, f"unknown_{self.stroke_type}")


def parse_dump_line(line: str) -> Optional[DumpEntry]:
    """1行の dump を name|related|data に分解。ヘッダ・空行は None。"""
    line = line.rstrip("\n")
    if not line or line.startswith("-") or line.startswith("name"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 3:
        return None
    name, related, data = parts[0], parts[1], parts[2]
    if not name:
        return None
    return DumpEntry(name=name, related=related, data=data)


def iter_dump(path: Path) -> Iterator[DumpEntry]:
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            entry = parse_dump_line(line)
            if entry is not None:
                yield entry


def load_dump_index(path: Path) -> Dict[str, DumpEntry]:
    """name → DumpEntry の辞書を構築（同一名は後勝ち）。"""
    index: Dict[str, DumpEntry] = {}
    for entry in iter_dump(path):
        index[entry.name] = entry
    return index


def parse_kage_data(data: str) -> List[KageStroke]:
    """KAGE data 文字列を筆画リストにパース。"""
    strokes: List[KageStroke] = []
    if not data:
        return strokes
    for raw in data.split("$"):
        raw = raw.strip()
        if not raw:
            continue
        cols = raw.split(":")
        if not cols:
            continue
        try:
            stype = int(float(cols[0]))
        except ValueError:
            continue
        start_tag = _to_int(cols[1]) if len(cols) > 1 else 0
        end_tag = _to_int(cols[2]) if len(cols) > 2 else 0

        if stype == 99:
            # 99:a:b:x1:y1:x2:y2:name[:extra...]
            coords: List[float] = []
            for c in cols[3:7]:
                coords.append(_to_float(c))
            ref_name = cols[7] if len(cols) > 7 else None
            # バージョン付き参照 uXXXX@N → ベース名も保持したいのでそのまま
            ref_extra = cols[8:] if len(cols) > 8 else []
            strokes.append(
                KageStroke(
                    stroke_type=stype,
                    start_tag=start_tag,
                    end_tag=end_tag,
                    coords=coords,
                    ref_name=ref_name,
                    ref_extra=ref_extra,
                    raw=raw,
                )
            )
        else:
            coords = [_to_float(c) for c in cols[3:]]
            strokes.append(
                KageStroke(
                    stroke_type=stype,
                    start_tag=start_tag,
                    end_tag=end_tag,
                    coords=coords,
                    raw=raw,
                )
            )
    return strokes


def is_alias(strokes: Sequence[KageStroke]) -> bool:
    """単一の部品参照で 0,0,200,200 に近い配置ならエイリアスとみなす。"""
    if len(strokes) != 1 or strokes[0].stroke_type != 99:
        return False
    s = strokes[0]
    if len(s.coords) < 4:
        return False
    x1, y1, x2, y2 = s.coords[:4]
    return abs(x1) <= 2 and abs(y1) <= 2 and abs(x2 - 200) <= 2 and abs(y2 - 200) <= 2


def resolve_alias_chain(
    name: str, index: Dict[str, DumpEntry], max_depth: int = 16
) -> Tuple[str, List[str], List[KageStroke]]:
    """エイリアスを辿り、(最終名, チェーン, 展開前ストローク) を返す。"""
    chain = [name]
    cur = name
    for _ in range(max_depth):
        entry = index.get(cur)
        if entry is None:
            return cur, chain, []
        strokes = parse_kage_data(entry.data)
        if is_alias(strokes) and strokes[0].ref_name:
            nxt = _strip_version(strokes[0].ref_name)
            chain.append(nxt)
            cur = nxt
            continue
        return cur, chain, strokes
    return cur, chain, parse_kage_data(index[cur].data) if cur in index else []


@dataclass
class FlattenedStroke:
    stroke_type: int
    start_tag: int
    end_tag: int
    points: List[Tuple[float, float]]  # KAGE 200x200 空間
    source_path: str


def flatten_glyph(
    name: str,
    index: Dict[str, DumpEntry],
    *,
    max_depth: int = 24,
) -> Tuple[List[FlattenedStroke], int, List[str]]:
    """部品参照を再帰展開し、素の筆画のみ返す。

    Returns: (strokes, max_depth_seen, missing_refs)
    """
    out: List[FlattenedStroke] = []
    missing: List[str] = []
    max_seen = 0

    def walk(gname: str, depth: int, xform: Tuple[float, float, float, float]) -> None:
        nonlocal max_seen
        max_seen = max(max_seen, depth)
        if depth > max_depth:
            missing.append(f"MAXDEPTH:{gname}")
            return
        entry = index.get(gname)
        if entry is None:
            # @version や未収録
            base = _strip_version(gname)
            entry = index.get(base)
            if entry is None:
                missing.append(gname)
                return
            gname = base
        strokes = parse_kage_data(entry.data)
        # エイリアスなら追跡
        if is_alias(strokes) and strokes[0].ref_name:
            walk(_strip_version(strokes[0].ref_name), depth + 1, xform)
            return
        for s in strokes:
            if s.stroke_type == 99 and s.ref_name:
                if len(s.coords) < 4:
                    missing.append(s.ref_name)
                    continue
                nx1, ny1, nx2, ny2 = s.coords[:4]
                # 親矩形 xform=(X1,Y1,X2,Y2) に子矩形を写像
                child_box = _compose_box(xform, (nx1, ny1, nx2, ny2))
                walk(_strip_version(s.ref_name), depth + 1, child_box)
            else:
                pts = _coords_to_points(s.stroke_type, s.coords)
                mapped = [_map_point(p, xform) for p in pts]
                out.append(
                    FlattenedStroke(
                        stroke_type=s.stroke_type,
                        start_tag=s.start_tag,
                        end_tag=s.end_tag,
                        points=mapped,
                        source_path=gname,
                    )
                )

    walk(name, 0, (0.0, 0.0, 200.0, 200.0))
    return out, max_seen, missing


def _compose_box(
    parent: Tuple[float, float, float, float],
    child: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    """親配置矩形内に、子が参照する 0..200 空間の矩形 child を写像した新矩形。"""
    px1, py1, px2, py2 = parent
    cx1, cy1, cx2, cy2 = child
    pw = px2 - px1
    ph = py2 - py1
    return (
        px1 + pw * (cx1 / 200.0),
        py1 + ph * (cy1 / 200.0),
        px1 + pw * (cx2 / 200.0),
        py1 + ph * (cy2 / 200.0),
    )


def _map_point(
    p: Tuple[float, float], box: Tuple[float, float, float, float]
) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + (x2 - x1) * (p[0] / 200.0), y1 + (y2 - y1) * (p[1] / 200.0))


def _coords_to_points(stype: int, coords: Sequence[float]) -> List[Tuple[float, float]]:
    """タイプ別の座標列を点列へ。"""
    pts: List[Tuple[float, float]] = []
    # 座標は x,y のペア列
    pairs = list(zip(coords[0::2], coords[1::2]))
    if stype == 1:
        # 直線: x0 y0 x1 y1
        pts = pairs[:2]
    elif stype in (2, 3, 4, 7):
        # 曲線/折れ/乙/縦払い: 3点
        pts = pairs[:3]
    elif stype == 6:
        # 複曲線: 4点
        pts = pairs[:4]
    else:
        pts = pairs
    return [(float(x), float(y)) for x, y in pts]


def _strip_version(name: str) -> str:
    # uXXXX@2 → uXXXX （dump_newest_only は最新のみ）
    if "@" in name:
        return name.split("@", 1)[0]
    return name


def _to_int(s: str) -> int:
    try:
        return int(float(s))
    except ValueError:
        return 0


def _to_float(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return 0.0


def sample_curve_points(points: Sequence[Tuple[float, float]], n: int = 12) -> List[Tuple[float, float]]:
    """制御点列を折れ線サンプルに（2次/3次の簡易分割）。"""
    if len(points) <= 2:
        return list(points)
    if len(points) == 3:
        p0, p1, p2 = points
        return [_quad(p0, p1, p2, i / (n - 1)) for i in range(n)]
    if len(points) >= 4:
        # 複曲線は 2 つの 2 次として近似（KAGEの描画とは厳密一致しないが可視化用）
        p0, p1, p2, p3 = points[:4]
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        a = [_quad(p0, p1, mid, i / (n // 2)) for i in range(n // 2)]
        b = [_quad(mid, p2, p3, i / (n - n // 2 - 1 or 1)) for i in range(n - n // 2)]
        return a + b[1:]
    return list(points)


def _quad(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    u = 1 - t
    x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
    y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
    return (x, y)
