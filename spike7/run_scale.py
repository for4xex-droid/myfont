#!/usr/bin/env python3
"""C. 常用漢字ランダム100字のスケール検証。"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "spike2"))

from pipeline import expand_and_map, fatten_to_paths, load_index, write_svg  # noqa: E402
from kage_mapper import FallbackKind  # noqa: E402
from params import CLASSIC  # noqa: E402

OUT = ROOT / "output"
JOYO_PATH = ROOT.parent / "spike2" / "output" / "glyphset_joyo2136.txt"
SEED = 20260809
N = 100
JOYO_TOTAL = 2136


def load_joyo() -> list[str]:
    chars = []
    for line in JOYO_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 1文字/行 or カンマ区切り等に耐性
        for ch in line:
            if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
                chars.append(ch)
            elif len(line) == 1:
                chars.append(ch)
    # 重複除去・順序保持
    seen = set()
    out = []
    for c in chars:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    joyo = load_joyo()
    if len(joyo) < N:
        print(f"joyo list too small: {len(joyo)}", file=sys.stderr)
        return 2
    rng = random.Random(SEED)
    sample = rng.sample(joyo, N)

    index = load_index()
    out_dir = OUT / "scale100"
    out_dir.mkdir(parents=True, exist_ok=True)

    # フォールバックを筆画タイプ別に集計するため、警告の kage_type を使う
    fb_by_type: Counter = Counter()
    fb_kind: Counter = Counter()
    type_stroke_total: Counter = Counter()
    ok = 0
    errors = []
    t0 = time.perf_counter()

    for i, ch in enumerate(sample):
        mapped, meta = expand_and_map(ch, index)
        # タイプ別出現（展開後）
        gname = meta.get("glyph_name")
        if gname:
            from kage_parser import flatten_glyph

            flat, _, _ = flatten_glyph(gname, index)
            for fs in flat:
                type_stroke_total[fs.stroke_type] += 1

        for w in mapped.warnings:
            fb_by_type[w.kage_type] += 1
            fb_kind[w.fallback.value] += 1

        try:
            if not mapped.strokes:
                raise RuntimeError(meta.get("error") or "no_strokes")
            d, _parts = fatten_to_paths(mapped, CLASSIC)
            stem = f"{i:03d}_u{ord(ch):04x}_{ch}"
            issues = write_svg(
                out_dir / f"{stem}.svg",
                d,
                f"{ch} / scale sample",
            )
            if issues or not d.strip():
                raise RuntimeError("; ".join(issues) or "empty path")
            ok += 1
        except Exception as e:
            errors.append({"char": ch, "cp": f"U+{ord(ch):04X}", "error": str(e)})

    elapsed = time.perf_counter() - t0
    success_rate = ok / N
    # フォールバック発生率: 警告数 / 展開筆画総数
    n_strokes = sum(type_stroke_total.values()) or 1
    hard_kinds = {
        "bend_split",
        "complex_curve_as_cubic",
        "vertical_sweep_as_left_hara",
        "special_skip",
        "otsu_split",
        "unknown_as_polyline",
    }
    soft_kinds = {"short_curve_as_ten", "quad_to_cubic"}
    hard_events = sum(n for k, n in fb_kind.items() if k in hard_kinds)
    soft_events = sum(n for k, n in fb_kind.items() if k in soft_kinds)
    fb_rate_overall = sum(fb_kind.values()) / n_strokes
    fb_rate_hard = hard_events / n_strokes
    fb_rate_by_type = {
        f"type{t}": {
            "strokes": type_stroke_total.get(t, 0),
            "fallback_events": fb_by_type.get(t, 0),
            "rate": (fb_by_type.get(t, 0) / type_stroke_total[t])
            if type_stroke_total.get(t)
            else 0.0,
        }
        for t in sorted(set(type_stroke_total) | set(fb_by_type))
    }

    # 2,136字外挿
    per_char_ms = (elapsed / N) * 1000
    extrap = {
        "joyo_total": JOYO_TOTAL,
        "est_seconds": elapsed * (JOYO_TOTAL / N),
        "est_minutes": elapsed * (JOYO_TOTAL / N) / 60,
        "assumptions": "同一成功率・同一平均処理時間の線形外挿（I/O・品質ゲート除く）",
    }

    report = {
        "seed": SEED,
        "n": N,
        "sample_chars": "".join(sample),
        "success_count": ok,
        "success_rate": success_rate,
        "elapsed_sec": elapsed,
        "per_char_ms": per_char_ms,
        "n_flat_strokes_total": n_strokes,
        "fallback_events_total": sum(fb_kind.values()),
        "fallback_rate_overall": fb_rate_overall,
        "fallback_rate_hard": fb_rate_hard,
        "fallback_hard_events": hard_events,
        "fallback_soft_events": soft_events,
        "fallback_by_kind": dict(fb_kind),
        "fallback_rate_by_kage_type": fb_rate_by_type,
        "errors": errors,
        "extrapolation_2136": extrap,
        "note": (
            "hard= type3/4/6/7/0 等の構造フォールバック。"
            "soft= short_curve→ten（ヒューリスティック、品質上は正常寄り）。"
            "type2 の通常 quad→cubic は警告に含めない。"
        ),
    }
    (OUT / "scale100_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({k: report[k] for k in (
        "success_count", "success_rate", "elapsed_sec", "per_char_ms",
        "fallback_rate_overall", "fallback_rate_hard", "fallback_by_kind",
        "extrapolation_2136",
    )}, ensure_ascii=False, indent=2))
    print(f"errors: {len(errors)}")
    return 0 if ok == N else 1


if __name__ == "__main__":
    raise SystemExit(main())
