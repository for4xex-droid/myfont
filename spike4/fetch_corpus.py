#!/usr/bin/env python3
"""T1 実証: 5書体を取得し corpus_actual.yaml に記録。可変なら wght=400 にインスタンス化。"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import yaml
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
RAW = FONTS / "_raw"
CORPUS_OUT = ROOT / "corpus_actual.yaml"

# 取得定義（優先URL順）
CORPUS = [
    {
        "family_id": "source_han_serif_jp",
        "display_name": "源ノ明朝 (Source Han Serif JP)",
        "license": "OFL-1.1",
        "vendor": "adobe-fonts/source-han-serif",
        "preferred_name": "SourceHanSerifJP-Regular.otf",
        "urls": [
            "https://github.com/adobe-fonts/source-han-serif/releases/download/2.003R/12_SourceHanSerifJP.zip",
        ],
        "kind": "zip_member",
        "member_globs": ["**/SourceHanSerifJP-Regular.otf", "SourceHanSerifJP-Regular.otf"],
        "notes": "GitHub release 2.003R の JP subset zip から Regular を抽出",
    },
    {
        "family_id": "ipaex_mincho",
        "display_name": "IPAex明朝",
        "license": "IPA Font License",
        "vendor": "moji.or.jp (一般社団法人 文字情報技術促進協議会)",
        "preferred_name": "ipaexm.ttf",
        "urls": [
            "https://moji.or.jp/wp-content/ipafont/IPAexfont/ipaexm00401.zip",
        ],
        "mirrors": [
            "https://ipafont.ipa.go.jp/IPAexfont/ipaexm00401.zip",  # 旧IPA直リンク（生存確認）
        ],
        "kind": "zip_member",
        "member_globs": ["**/ipaexm.ttf", "ipaexm.ttf"],
        "notes": "公式 Ver.004.01。moji.or.jp 配布",
    },
    {
        "family_id": "shippori_mincho",
        "display_name": "しっぽり明朝",
        "license": "OFL-1.1",
        "vendor": "google/fonts",
        "preferred_name": "ShipporiMincho-Regular.ttf",
        "urls": [
            "https://github.com/google/fonts/raw/main/ofl/shipporimincho/ShipporiMincho-Regular.ttf",
        ],
        "kind": "direct",
        "notes": "google/fonts ofl/shipporimincho 静的 Regular",
    },
    {
        "family_id": "zen_old_mincho",
        "display_name": "Zen Old Mincho",
        "license": "OFL-1.1",
        "vendor": "google/fonts",
        "preferred_name": "ZenOldMincho-Regular.ttf",
        "urls": [
            "https://github.com/google/fonts/raw/main/ofl/zenoldmincho/ZenOldMincho-Regular.ttf",
        ],
        "kind": "direct",
        "notes": "google/fonts ofl/zenoldmincho 静的 Regular",
    },
    {
        "family_id": "biz_ud_mincho",
        "display_name": "BIZ UD明朝",
        "license": "OFL-1.1",
        "vendor": "google/fonts",
        "preferred_name": "BIZUDMincho-Regular.ttf",
        "urls": [
            "https://github.com/google/fonts/raw/main/ofl/bizudmincho/BIZUDMincho-Regular.ttf",
        ],
        "kind": "direct",
        "notes": "google/fonts ofl/bizudmincho 静的 Regular",
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "myfont-spike4/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def match_member(names: list[str], globs: list[str]) -> str | None:
    # simple suffix / exact match
    for g in globs:
        g = g.lstrip("*/")
        for n in names:
            if n == g or n.endswith("/" + g) or n.endswith(g):
                return n
    return None


def is_variable_font(path: Path) -> bool:
    try:
        font = TTFont(str(path), lazy=True)
        has = "fvar" in font
        font.close()
        return has
    except Exception:
        return False


def instantiate_wght400(src: Path, dst: Path) -> dict:
    font = TTFont(str(src))
    if "fvar" not in font:
        font.close()
        shutil.copy2(src, dst)
        return {"instanced": False, "coords": None}
    # axes may not all be wght
    axes = {a.axisTag: a for a in font["fvar"].axes}
    coords = {}
    if "wght" in axes:
        coords["wght"] = 400
    partial = instancer.instantiateVariableFont(font, coords, inplace=False)
    dst.parent.mkdir(parents=True, exist_ok=True)
    partial.save(str(dst))
    font.close()
    return {"instanced": True, "coords": coords}


def extract_zip_member(zip_path: Path, globs: list[str], out_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        member = match_member(names, globs)
        if member is None:
            raise FileNotFoundError(f"member not found in {zip_path.name}; sample={names[:8]}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(out_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return member


def try_urls(urls: list[str], dest: Path) -> tuple[str | None, str | None]:
    errors = []
    for url in urls:
        try:
            print(f"  GET {url}")
            download(url, dest)
            if dest.stat().st_size < 1000:
                raise RuntimeError(f"too small: {dest.stat().st_size}")
            return url, None
        except Exception as e:
            errors.append(f"{url}: {e}")
            if dest.exists():
                dest.unlink()
    return None, "; ".join(errors)


def process_entry(entry: dict) -> dict:
    fid = entry["family_id"]
    print(f"\n=== {fid} ===")
    result = {
        "family_id": fid,
        "display_name": entry["display_name"],
        "license": entry["license"],
        "vendor": entry["vendor"],
        "notes": entry.get("notes", ""),
        "acquired": False,
        "source_url": None,
        "sha256_source": None,
        "sha256_measured": None,
        "path_rel": None,
        "is_variable": None,
        "instanced_wght400": False,
        "instance_coords": None,
        "error": None,
        "mirrors_tried": [],
    }

    urls = list(entry["urls"]) + list(entry.get("mirrors", []))
    raw_name = entry["preferred_name"]
    if entry["kind"] == "zip_member":
        raw_dest = RAW / f"{fid}.zip"
    else:
        raw_dest = RAW / raw_name

    url, err = try_urls(urls, raw_dest)
    if url is None:
        result["error"] = err
        # record mirror attempts for IPA
        if entry.get("mirrors"):
            result["mirrors_tried"] = entry["mirrors"]
            result["mirror_note"] = "公式失敗時に旧IPA直リンク等を試行した結果も error に含む"
        print(f"  FAIL: {err}")
        return result

    result["source_url"] = url
    result["sha256_source"] = sha256_file(raw_dest)

    extracted = FONTS / f"{fid}__raw__{raw_name}"
    try:
        if entry["kind"] == "zip_member":
            member = extract_zip_member(raw_dest, entry["member_globs"], extracted)
            result["zip_member"] = member
        else:
            shutil.copy2(raw_dest, extracted)

        variable = is_variable_font(extracted)
        result["is_variable"] = variable
        measured = FONTS / f"{fid}-Regular.ttf" if extracted.suffix.lower() == ".ttf" else FONTS / f"{fid}-Regular.otf"
        # keep original extension
        measured = FONTS / f"{fid}-Regular{extracted.suffix.lower()}"

        if variable:
            info = instantiate_wght400(extracted, measured)
            result["instanced_wght400"] = info["instanced"]
            result["instance_coords"] = info["coords"]
            result["notes"] += " | variable → instancer wght=400"
        else:
            shutil.copy2(extracted, measured)
            result["instanced_wght400"] = False
            result["instance_coords"] = None

        # verify fvar gone / readable
        font = TTFont(str(measured), lazy=True)
        still_var = "fvar" in font
        upem = font["head"].unitsPerEm
        font.close()
        if still_var:
            result["error"] = "still variable after instantiate"
            print("  FAIL: still variable")
            return result

        result["acquired"] = True
        result["path_rel"] = str(measured.relative_to(ROOT))
        result["sha256_measured"] = sha256_file(measured)
        result["units_per_em"] = upem
        result["file_bytes"] = measured.stat().st_size
        print(f"  OK path={result['path_rel']} var={variable} sha={result['sha256_measured'][:16]}…")
    except Exception as e:
        result["error"] = str(e)
        print(f"  FAIL: {e}")
    return result


def main() -> int:
    FONTS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    results = [process_entry(e) for e in CORPUS]
    doc = {
        "protocol": {
            "em_px": 1024,
            "variable_policy": "wght=400 に fontTools.varLib.instancer で固定してから計測（PLAN T1）",
            "profile": "ft_1024_nohint_gray_v1",
        },
        "families": results,
        "summary": {
            "acquired": sum(1 for r in results if r["acquired"]),
            "total": len(results),
            "missing": [r["family_id"] for r in results if not r["acquired"]],
        },
    }
    with open(CORPUS_OUT, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
    print(f"\nwrote {CORPUS_OUT}")
    print("summary:", json.dumps(doc["summary"], ensure_ascii=False))
    return 0 if doc["summary"]["acquired"] >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
