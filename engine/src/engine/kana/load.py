"""仮名骨格 YAML ローダ（P1-B DSL）。

正本: engine/kana/skeletons/*.yaml（cubic spine + 弧長幅キー + joins/gate）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.geometry import Vec2, parse_cubic_chain
from engine.kana.schema import (
    GateSpec,
    JoinSpec,
    parse_gate,
    parse_joins,
    parse_loop_closure,
    validate_element_keys,
    validate_top_level,
)
from engine.strokes import (
    KANA_MAX_SPINE_POINTS,
    EndTag,
    SkeletonStroke,
    StrokeKind,
)

_SKELETONS = Path(__file__).resolve().parent / "skeletons"

# glyph_id → UFO メタ（bridge / gate が参照）
KANA_GLYPH_META: dict[str, dict[str, Any]] = {}


def skeletons_dir() -> Path:
    return _SKELETONS


def _as_vec2(pt: Any) -> Vec2:
    if not isinstance(pt, (list, tuple)) or len(pt) != 2:
        raise ValueError(f"spine point must be [x, y], got {pt!r}")
    return Vec2(float(pt[0]), float(pt[1]))


def _parse_width_keys(raw: Any) -> list[tuple[float, float]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise ValueError("width must be a non-empty list of {s, hw}")
    keys: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"width key must be mapping, got {item!r}")
        if "s" not in item or "hw" not in item:
            raise ValueError(f"width key needs s and hw: {item!r}")
        s = float(item["s"])
        hw = float(item["hw"])
        if s < 0.0 or s > 1.0:
            raise ValueError(f"width s must be in [0,1], got {s}")
        if hw < 0.0:
            raise ValueError(f"width hw must be ≥0, got {hw}")
        keys.append((s, hw))
    return keys


def _end_tag_from_template(name: str | None) -> EndTag:
    """端物テンプレ名 → 既存 EndTag（スパイク段階は近似マッピング）。"""
    if not name or name in ("none", "flat"):
        return EndTag.NONE
    mapping = {
        "karui_uchikomi": EndTag.UCHIKOMI,
        "tome_maru": EndTag.TOME,
        "nuki": EndTag.TAPER,
        "sori": EndTag.NONE,
        "kado_tome": EndTag.TOME,
        "hane_kana": EndTag.HANE,
        "taper": EndTag.TAPER,
        "uchikomi": EndTag.UCHIKOMI,
    }
    return mapping.get(str(name), EndTag.NONE)


def load_kana_skeleton(path: Path) -> tuple[str, list[SkeletonStroke], dict[str, Any]]:
    """YAML 1字を読み、(glyph_id, strokes, meta) を返す。

    meta には joins / gate（GateSpec）と element_ids を含む。
    必須キー欠落・未知キーは ValueError。
    """
    label = str(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"kana skeleton root must be mapping: {path}")
    validate_top_level(label, raw)

    glyph_id = str(raw.get("glyph_id") or path.stem)
    char = str(raw.get("char") or "")
    unicode_val = raw.get("unicode")
    if unicode_val is None and char:
        unicode_val = ord(char)
    if unicode_val is None:
        raise ValueError(f"{path}: unicode or char required")
    unicode_i = int(unicode_val, 0) if isinstance(unicode_val, str) else int(unicode_val)

    elements = raw.get("elements")
    if not isinstance(elements, list) or not elements:
        raise ValueError(f"{path}: elements[] required")

    strokes: list[SkeletonStroke] = []
    element_ids: list[str] = []
    seen_ids: set[str] = set()
    for i, el in enumerate(elements):
        ep = f"{label}:elements[{i}]"
        if not isinstance(el, dict):
            raise ValueError(f"{ep}: element must be mapping")
        validate_element_keys(ep, el)
        if "id" not in el:
            raise ValueError(f"{ep}: missing required key 'id'")
        eid = str(el["id"])
        if not eid:
            raise ValueError(f"{ep}: id must be non-empty")
        if eid in seen_ids:
            raise ValueError(f"{ep}: duplicate element id {eid!r}")
        seen_ids.add(eid)
        element_ids.append(eid)

        spine = el.get("spine")
        if not isinstance(spine, list):
            raise ValueError(f"{ep}: element.spine required")
        points = [_as_vec2(p) for p in spine]
        if len(points) > KANA_MAX_SPINE_POINTS:
            raise ValueError(
                f"{ep}: spine points {len(points)} > {KANA_MAX_SPINE_POINTS}"
            )
        parse_cubic_chain(points)  # 構文検証
        width_keys = _parse_width_keys(el.get("width"))
        ends = el.get("ends") or {}
        if not isinstance(ends, dict):
            raise ValueError(f"{ep}: ends must be mapping")
        start_tag = _end_tag_from_template(ends.get("entry"))
        end_tag = _end_tag_from_template(ends.get("exit"))
        loop = parse_loop_closure(f"{ep}.loop_closure", el.get("loop_closure"))
        strokes.append(
            SkeletonStroke(
                kind=StrokeKind.KANA_CURVE,
                points=points,
                start_tag=start_tag,
                end_tag=end_tag,
                width_keys=width_keys or None,
                element_id=eid,
                loop_closed=loop is not None,
                loop_overlap_upm=float(loop.overlap_upm) if loop else 0.0,
                loop_join_angle_deg=loop.join_angle if loop else None,
            )
        )

    joins = parse_joins(label, raw.get("joins"))
    gate = parse_gate(label, raw.get("gate"))
    id_set = set(element_ids)
    for j in joins:
        if j.from_id not in id_set:
            raise ValueError(f"{label}:joins from unknown element {j.from_id!r}")
        if j.to_id not in id_set:
            raise ValueError(f"{label}:joins to unknown element {j.to_id!r}")
    if gate is not None:
        for tip in gate.tips:
            if tip.element not in id_set:
                raise ValueError(
                    f"{label}:gate.tips element unknown {tip.element!r}"
                )
        for gap in gate.gaps:
            if gap.a not in id_set or gap.b not in id_set:
                raise ValueError(
                    f"{label}:gate.gaps references unknown element "
                    f"{gap.a!r}/{gap.b!r}"
                )

    meta: dict[str, Any] = {
        "name": str(raw.get("name") or f"uni{unicode_i:04X}"),
        "unicode": unicode_i,
        "char": char or chr(unicode_i),
        "motif": raw.get("motif"),
        "source": str(path.name),
        "element_ids": element_ids,
        "joins": joins,
        "gate": gate,
        "coordinate_space": "svg_y_down_legacy",
    }
    return glyph_id, strokes, meta


def _discover_skeletons() -> dict[str, Path]:
    if not _SKELETONS.is_dir():
        return {}
    return {p.stem: p for p in sorted(_SKELETONS.glob("*.yaml"))}


def kana_characters() -> dict[str, list[SkeletonStroke]]:
    """登録済み仮名骨格。呼び出しごとに YAML を読み直す（編集即反映）。"""
    out: dict[str, list[SkeletonStroke]] = {}
    KANA_GLYPH_META.clear()
    for stem, path in _discover_skeletons().items():
        gid, strokes, meta = load_kana_skeleton(path)
        if gid != stem:
            # ファイル名と glyph_id の食い違いは許すが、両方で引けるようにする
            pass
        out[gid] = strokes
        KANA_GLYPH_META[gid] = meta
    return out


def kana_labels() -> dict[str, str]:
    chars = kana_characters()
    return {gid: str(KANA_GLYPH_META[gid]["char"]) for gid in chars}


def get_joins(glyph_id: str) -> tuple[JoinSpec, ...]:
    if glyph_id not in KANA_GLYPH_META:
        kana_characters()
    meta = KANA_GLYPH_META.get(glyph_id) or {}
    return tuple(meta.get("joins") or ())


def get_gate(glyph_id: str) -> GateSpec | None:
    if glyph_id not in KANA_GLYPH_META:
        kana_characters()
    meta = KANA_GLYPH_META.get(glyph_id) or {}
    gate = meta.get("gate")
    return gate if isinstance(gate, GateSpec) else None
