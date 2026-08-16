#!/usr/bin/env python3
"""P-D1 黄金をバージョン付きで凍らせる（掟18）。1回限りの運用スクリプト。"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import receive_manual  # noqa: E402
import set_manual_sidebearings as sidebearings  # noqa: E402

VERSION = "d1"
REASON = "P-D1 DNA A。IPAex骨格から離脱。つ系は幅維持×2。"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supersede(old: Path, new_ver: str) -> dict:
    data = json.loads(old.read_text(encoding="utf-8"))
    if data.get("superseded_by"):
        return data
    files = data.pop("files", None)
    if files:
        data["historical_files"] = files
    data["superseded_by"] = new_ver
    data["note"] = f"現行の正は {new_ver}。"
    old.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> int:
    from ufoLib2 import Font
    from engine.bridge import compile_otf

    dest_ufo = ROOT / "fonts_out" / "MyMincho.ufo"
    dest = Font.open(dest_ufo)
    otf = ROOT / "fonts_out" / "build" / "MyMincho.otf"
    if not otf.is_file():
        compile_otf(dest_ufo, otf, remove_overlaps=False)

    spec = __import__("importlib.util").util.spec_from_file_location(
        "kana_render", ROOT / "engine" / "scripts" / "kana_render.py"
    )
    render = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(render)

    frozen_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")

    # per-glyph
    for path in sorted((ROOT / "proofs" / "golden").glob("kana_*/FREEZE_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("superseded_by") or data.get("source") != "manual_ufo":
            continue
        folder = path.parent
        gid = folder.name.removeprefix("kana_")
        new_ver = f"kana_{gid}_{VERSION}"
        files = data.get("files") or {}
        glyph_name = data.get("glyph")
        if not glyph_name:
            # あ
            glyph_name = "uni3042"
        g = dest[glyph_name]
        lsb, rsb, ink = sidebearings.sidebearings(g)
        glif = ROOT / data.get("glif", f"fonts_out/MyMincho.ufo/glyphs/{glyph_name}.glif")
        if not glif.is_file():
            # underscore variants
            alt = glif.with_name(glif.stem + "_.glif")
            if alt.is_file():
                glif = alt
        new_files = {}
        for rel, meta in files.items():
            png = ROOT / rel
            rendered = render.render_text_png(otf, meta["text"], png)
            new_files[rel] = {
                "sha256": rendered["png_sha256"],
                "text": meta["text"],
                "tag": meta["tag"],
            }
        supersede(path, new_ver)
        new = {
            "version": new_ver,
            "frozen_at": frozen_at,
            "reason": REASON,
            "source": "manual_ufo",
            "ufo": "fonts_out/MyMincho.ufo",
            "glyph": glyph_name,
            "glif": str(glif.relative_to(ROOT)),
            "params": "product_r1",
            "glif_sha256": sha256(glif),
            "sidebearings_em1000": {
                "lsb": round(float(lsb), 1),
                "rsb": round(float(rsb), 1),
                "ink": round(float(ink), 1) if ink is not None else None,
                "target_lsb": [106, 146],
                "target_rsb": [98, 138],
                "ci": "engine/tests/test_kana_band.py::test_current_kana_live_render_matches_golden",
                "note": "参照4書体中央±20U。kana_gate には載せない（掟8）。",
            },
            "files": new_files,
        }
        (folder / f"FREEZE_{VERSION}.json").write_text(
            json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{gid} {new_ver}")

    # g3_blind from live proofs/out
    blind_dir = ROOT / "proofs" / "golden" / "g3_blind"
    blind_files = {}
    for tag in ("ui_kana", "hud_kana", "walk_kana"):
        src = ROOT / "proofs" / "out" / f"{tag}.png"
        dst = blind_dir / f"{tag}.png"
        shutil.copy2(src, dst)
        text_file = f"proofs/texts/{tag}.txt"
        blind_files[f"proofs/golden/g3_blind/{tag}.png"] = {
            "sha256": sha256(dst),
            "text_file": text_file,
            "tag": tag,
        }
    supersede(blind_dir / "FREEZE_q5.json", "kana_g3_blind_d1")
    (blind_dir / "FREEZE_d1.json").write_text(
        json.dumps(
            {
                "version": "kana_g3_blind_d1",
                "frozen_at": frozen_at,
                "reason": REASON + " beforeは kana_g3_blind_q5。",
                "source": "shipping_ufo",
                "ufo": "fonts_out/MyMincho.ufo",
                "params": "product_r1",
                "note": "α 本盲検の ui.txt/hud.txt は漢字を含む。この文面は仮名縮小のまま。",
                "files": blind_files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("g3_blind kana_g3_blind_d1")

    # g3_kana
    g3 = ROOT / "proofs" / "golden" / "g3_kana"
    old = json.loads((g3 / "FREEZE_g3.json").read_text(encoding="utf-8"))
    g3_files = {}
    for rel, meta in old["files"].items():
        png = ROOT / rel
        rendered = render.render_text_png(otf, meta["text"], png)
        g3_files[rel] = {
            "sha256": rendered["png_sha256"],
            "text": meta["text"],
            "tag": meta["tag"],
        }
    supersede(g3 / "FREEZE_g3.json", "kana_g3_d1")
    (g3 / "FREEZE_d1.json").write_text(
        json.dumps(
            {
                "version": "kana_g3_d1",
                "frozen_at": frozen_at,
                "reason": REASON,
                "source": "shipping_ufo",
                "ufo": "fonts_out/MyMincho.ufo",
                "params": "product_r1",
                "note": "共有UFOの OTF SHA は字追加で変わるため載せない。正本は PNG SHA。",
                "files": g3_files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("g3_kana kana_g3_d1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
