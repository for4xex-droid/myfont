#!/usr/bin/env python3
"""C: fontmake / fontbakery / uharfbuzz のビルドチェーン確認。"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SPIKE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SPIKE, "output")
VENV_BIN = os.path.join(SPIKE, ".venv", "bin")
PIP = os.path.join(VENV_BIN, "pip")
PYTHON = os.path.join(VENV_BIN, "python")
FONT = os.path.join(SPIKE, "fonts", "NotoSerifJP-Regular.otf")


def run(cmd, timeout=120):
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout_tail": (p.stdout or "")[-2000:],
            "stderr_tail": (p.stderr or "")[-2000:],
            "ok": p.returncode == 0,
        }
    except Exception as e:
        return {"cmd": cmd, "ok": False, "error": repr(e)}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    report = {"fontmake": {}, "fontbakery": {}, "uharfbuzz": {}, "verdict": {}}

    # 1. fontmake
    print("=== pip install fontmake ===")
    inst = run([PIP, "install", "fontmake"], timeout=300)
    report["fontmake"]["install"] = {
        "ok": inst["ok"],
        "returncode": inst.get("returncode"),
        "stderr_tail": inst.get("stderr_tail", "")[-800:],
        "error": inst.get("error"),
    }
    if inst["ok"]:
        help_r = run([os.path.join(VENV_BIN, "fontmake"), "--help"], timeout=30)
        report["fontmake"]["help"] = {
            "ok": help_r["ok"],
            "stdout_head": (help_r.get("stdout_tail") or "")[:500],
        }
    else:
        report["fontmake"]["help"] = {"ok": False, "skipped": True}

    # 2. fontbakery — 重ければ pip download のみ
    print("=== fontbakery: try pip install, fallback pip download ===")
    fb_inst = run([PIP, "install", "fontbakery"], timeout=300)
    report["fontbakery"]["install"] = {
        "ok": fb_inst["ok"],
        "returncode": fb_inst.get("returncode"),
        "stderr_tail": (fb_inst.get("stderr_tail") or "")[-800:],
        "error": fb_inst.get("error"),
    }
    if not fb_inst["ok"]:
        dl = run(
            [PIP, "download", "fontbakery", "-d", os.path.join(SPIKE, "wheelhouse")],
            timeout=300,
        )
        report["fontbakery"]["download"] = {
            "ok": dl["ok"],
            "returncode": dl.get("returncode"),
            "stderr_tail": (dl.get("stderr_tail") or "")[-500:],
            "error": dl.get("error"),
        }
    else:
        report["fontbakery"]["download"] = {"skipped": True, "reason": "install succeeded"}

    # 3. uharfbuzz shaping 「あ」
    print("=== uharfbuzz shape あ ===")
    shape_script = r"""
import json, sys
import uharfbuzz as hb

path = sys.argv[1]
with open(path, "rb") as f:
    data = f.read()
face = hb.Face(data)
font = hb.Font(face)
# uharfbuzz 0.56: Font.size は無い。upem 単位のまま shape すれば十分。
buf = hb.Buffer()
buf.add_str("あ")
buf.guess_segment_properties()
hb.shape(font, buf)
infos = buf.glyph_infos
positions = buf.glyph_positions
out = []
for info, pos in zip(infos, positions):
    out.append({
        "gid": int(info.codepoint),
        "cluster": int(info.cluster),
        "ax": int(pos.x_advance),
        "ay": int(pos.y_advance),
        "dx": int(pos.x_offset),
        "dy": int(pos.y_offset),
    })
try:
    name = font.get_glyph_name(out[0]["gid"]) if out else None
except Exception:
    name = None
ok = len(out) > 0 and out[0]["gid"] != 0
print(json.dumps({"ok": ok, "upem": face.upem, "glyphs": out, "name": name}, ensure_ascii=False))
"""
    font_for_shape = FONT
    instanced = os.path.join(SPIKE, "fonts", "NotoSerifJP-Regular-wght400.ttf")
    if os.path.isfile(instanced):
        font_for_shape = instanced
    if os.path.isfile(font_for_shape):
        shape_r = run([PYTHON, "-c", shape_script, font_for_shape], timeout=30)
        # parse stdout last line
        try:
            lines = [ln for ln in (shape_r.get("stdout_tail") or "").splitlines() if ln.strip()]
            payload = json.loads(lines[-1]) if lines else {"ok": False, "parse": "empty"}
        except Exception as e:
            payload = {"ok": False, "parse_error": repr(e), "raw": shape_r.get("stdout_tail")}
        report["uharfbuzz"] = {
            "run_ok": shape_r.get("ok"),
            "shape": payload,
            "stderr_tail": (shape_r.get("stderr_tail") or "")[-400:],
        }
    else:
        report["uharfbuzz"] = {"ok": False, "error": "font missing"}

    fm_ok = report["fontmake"].get("help", {}).get("ok", False)
    fb_ok = report["fontbakery"]["install"].get("ok") or report["fontbakery"].get("download", {}).get("ok")
    hb_ok = bool(report["uharfbuzz"].get("shape", {}).get("ok"))

    report["verdict"] = {
        "fontmake": "成立" if fm_ok else "不成立",
        "fontbakery": "成立" if report["fontbakery"]["install"].get("ok") else (
            "条件付き（downloadのみ可）" if report["fontbakery"].get("download", {}).get("ok") else "不成立"
        ),
        "uharfbuzz_proof": "成立" if hb_ok else "不成立",
        "overall": "成立" if (fm_ok and hb_ok) else ("条件付き" if (fm_ok or hb_ok or fb_ok) else "不成立"),
    }

    out_json = os.path.join(OUT, "verify_c_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report["verdict"], ensure_ascii=False, indent=2))
    print("wrote", out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
