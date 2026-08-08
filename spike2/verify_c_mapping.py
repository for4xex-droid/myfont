"""C. KAGE→内部形式（prototype StrokeKind/EndTag）写像の難易度実測。"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "prototype"))

from strokes import EndTag, StrokeKind  # noqa: E402

from kage_parser import (  # noqa: E402
    STROKE_TYPE_NAMES,
    flatten_glyph,
    load_dump_index,
)

OUT = ROOT / "output"
DUMP = ROOT / "data" / "dump_newest_only.txt"

# verify_b と同じサンプル（レポートから読む。なければデフォルト）
DEFAULT_SAMPLE = list("一二三十木人本大山口国囲園図回海詩村時話永職議論鬱漢雨電食鳥")


def map_stroke_kind(stype: int, points) -> tuple[str, str]:
    """(mapped_kind or None, note)。"""
    if stype == 1:
        if len(points) >= 2:
            dx = abs(points[1][0] - points[0][0])
            dy = abs(points[1][1] - points[0][1])
            if dx >= dy:
                return StrokeKind.HORIZONTAL.value, "straight→H/V by slope"
            return StrokeKind.VERTICAL.value, "straight→H/V by slope"
        return StrokeKind.HORIZONTAL.value, "straight fallback"
    if stype == 2:
        # 曲線は方向で left/right/ten をヒューリスティック
        if len(points) >= 3:
            dx = points[-1][0] - points[0][0]
            dy = points[-1][1] - points[0][1]
            if abs(dx) < 25 and abs(dy) < 40:
                return StrokeKind.TEN.value, "short curve→ten (heuristic)"
            if dx < 0:
                return StrokeKind.LEFT_HARA.value, "curve dx<0→left_hara"
            return StrokeKind.RIGHT_HARA.value, "curve dx>=0→right_hara"
        return StrokeKind.LEFT_HARA.value, "curve fallback"
    if stype == 3:
        return "SPLIT:bend→2 segments", "折れは2直線に分割が必要（内部に bend kind なし）"
    if stype == 4:
        return "SPLIT:otsu→2-3 segments", "乙線は複数セグメント化が必要"
    if stype == 6:
        return "APPROX:complex_curve→polyline/cubic", "複曲線は4制御点→3次ベジェor分割"
    if stype == 7:
        return StrokeKind.LEFT_HARA.value, "縦払い→left_hara 近似（専用kindなし）"
    if stype == 0:
        return "UNSUPPORTED:special", "特殊行"
    if stype == 99:
        return "RESOLVE:ref", "部品展開後に再写像"
    return f"UNKNOWN:{stype}", "未対応タイプ"


def map_end_tag(tag: int, which: str) -> tuple[str, str]:
    """端点タグ写像。"""
    # 経験的対応（kage-engine 描画仕様の要約。完全ではない）
    table = {
        0: (EndTag.NONE.value, "open"),
        2: (EndTag.UROKO.value if which == "end" else EndTag.UCHIKOMI.value, "connect_h / uroko-ish"),
        4: (EndTag.HANE.value, "hane"),
        5: (EndTag.TAPER.value, "hara taper-ish"),
        7: (EndTag.TOME.value if which == "end" else EndTag.NONE.value, "tome/open"),
        8: (EndTag.NONE.value, "ten-ish end"),
        12: (EndTag.UCHIKOMI.value, "corner_ur→uchikomi approx"),
        13: (EndTag.NONE.value, "corner"),
        22: (EndTag.UCHIKOMI.value if which == "start" else EndTag.TOME.value, "connect_v"),
        23: (EndTag.TOME.value, "connect_v_alt"),
        24: (EndTag.HANE.value, "hane_alt"),
        32: (EndTag.UCHIKOMI.value, "corner_ul"),
    }
    if tag in table:
        return table[tag]
    return (EndTag.NONE.value, f"unmapped tag {tag}→NONE (lossy)")


def main() -> None:
    b_report_path = OUT / "verify_b_report.json"
    if b_report_path.exists():
        b = json.loads(b_report_path.read_text(encoding="utf-8"))
        sample = b.get("sample_chars") or DEFAULT_SAMPLE
        type_tag = b.get("type_tag_pair_counts") or {}
    else:
        sample = DEFAULT_SAMPLE
        type_tag = {}

    index = load_dump_index(DUMP)

    combo_rows = []
    kind_map_stats = Counter()
    unmapped_tags = Counter()
    hard_cases = []

    # type_tag が空なら再集計
    if not type_tag:
        c = Counter()
        for ch in sample:
            name = f"u{ord(ch):x}"
            if name not in index and f"{name}-j" not in index:
                continue
            flat, _, _ = flatten_glyph(name if name in index else f"{name}-j", index)
            for s in flat:
                c[(s.stroke_type, s.start_tag, s.end_tag)] += 1
        type_tag = {f"t{a}_s{b}_e{c}": n for (a, b, c), n in c.most_common()}

    for key, count in sorted(type_tag.items(), key=lambda kv: -kv[1]):
        # t1_s0_e2
        parts = key.split("_")
        stype = int(parts[0][1:])
        start = int(parts[1][1:])
        end = int(parts[2][1:])
        kind, kind_note = map_stroke_kind(stype, [(0, 0), (100, 0), (100, 100)])
        st, st_note = map_end_tag(start, "start")
        et, et_note = map_end_tag(end, "end")
        status = "ok"
        if kind.startswith(("SPLIT", "APPROX", "UNSUPPORTED", "UNKNOWN", "RESOLVE")):
            status = "needs_work"
            hard_cases.append(
                {
                    "combo": key,
                    "count": count,
                    "issue": kind,
                    "note": kind_note,
                }
            )
        if "unmapped" in st_note or "unmapped" in et_note:
            status = "lossy_tag"
            unmapped_tags[start] += count
            unmapped_tags[end] += count
        kind_map_stats[status] += count
        combo_rows.append(
            {
                "combo": key,
                "kage_type": stype,
                "type_name": STROKE_TYPE_NAMES.get(stype, "?"),
                "start_tag": start,
                "end_tag": end,
                "count": count,
                "map_kind": kind,
                "map_start": st,
                "map_end": et,
                "kind_note": kind_note,
                "start_note": st_note,
                "end_note": et_note,
                "status": status,
            }
        )

    # 内部形式の列挙（prototype）
    internal = {
        "StrokeKind": [k.value for k in StrokeKind],
        "EndTag": [e.value for e in EndTag],
        "SkeletonStroke_fields": ["kind", "points", "start_tag", "end_tag", "thickness"],
        "notes": [
            "points: 直線=[start,end], 曲線=[p0,p1,p2,p3] 三次ベジェ想定",
            "KAGE曲線(type2)は3点（2次）→ cubic への次数上げ or polyline 化が必要",
            "prototype に bend/otsu/vertical_sweep 専用 kind はない",
        ],
    }

    # 工数判定
    n_combos = len(combo_rows)
    n_hard = len({h["combo"] for h in hard_cases})
    verdict_effort = {
        "plan_p4a": "KAGE→内部形式の変換器＋100字品質レポート",
        "observed_unique_type_tag_combos_in_sample": n_combos,
        "combos_needing_geometry_split_or_approx": n_hard,
        "assessment": (
            "条件付き妥当: ダンプ行パース自体は軽いが、"
            "部品再帰展開・エイリアス解決・折れ/複曲線の分割・端点タグ写像表が本体。"
            "変換器骨格は数日〜1週間、100字品質レポート（目視＋スコア）が主コスト。"
            "PLANのP4aを「写像仕様書＋100字ゲート」と置いているのは妥当。"
            "ただし『パース数十行で常用2,136字の骨格が得られる』は"
            "『展開後polylineが得られる』意味では条件付き成立、"
            "『製品品質の内部形式』意味では不成立（層A〜Cが必要）。"
        ),
        "recommended_estimate": {
            "converter_mvp_hours": "16–40h（展開＋写像表＋SVG差分）",
            "100_glyph_quality_report_hours": "20–40h",
            "total_p4a_hours": "40–80h（写像仕様書 docs/kage_mapping.md 含む）",
        },
    }

    report = {
        "internal_form": internal,
        "combo_table": combo_rows,
        "status_counts_by_stroke_occurrence": dict(kind_map_stats),
        "hard_cases": hard_cases,
        "unmapped_tag_ids": dict(unmapped_tags),
        "effort": verdict_effort,
        "verdict": "条件付き",
        "plan_citations": {
            "§3.4": "ダンプパースは数十行→自前実装 / 写像は既存なしで自作正当",
            "§5": "KAGEダンプパース=自作（数十行） / KAGE→内部形式写像=自作",
            "dump_parse": "前提成立（行分解は数十行）",
            "full_skeleton_pipeline": "条件付き（部品展開必須・写像は別工数）",
            "joyo_skeletons_available": "条件付き成立（カバー率高だが alias+部品解決が前提）",
        },
    }
    (OUT / "verify_c_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Markdown 表
    lines = [
        "# KAGE type × endpoint tag → internal mapping (sample)",
        "",
        "| combo | type | start | end | count | → kind | → start_tag | → end_tag | status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in combo_rows:
        lines.append(
            f"| `{r['combo']}` | {r['type_name']} | {r['start_tag']} | {r['end_tag']} | {r['count']} | {r['map_kind']} | {r['map_start']} | {r['map_end']} | {r['status']} |"
        )
    lines += ["", "## Hard cases", ""]
    for h in hard_cases:
        lines.append(f"- `{h['combo']}` (n={h['count']}): {h['issue']} — {h['note']}")
    lines += ["", "## Effort verdict", "", verdict_effort["assessment"], ""]
    (OUT / "kage_mapping_table.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("verdict", "effort", "status_counts_by_stroke_occurrence", "plan_citations")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
