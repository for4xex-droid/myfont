"""コーパス5書体の取得（PLAN T1）。"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from fontdb.paths import CORPUS_YAML, FONTS_DIR, PACKAGE_ROOT

logger = logging.getLogger(__name__)

# 取得定義（spike4 で確定済み URL）
CORPUS_SPEC: list[dict[str, Any]] = [
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
        "expected_sha256": "e5f502bb193c28829895b098498f0f9dd8f658c760b0f83656ad41c1137a8785",
    },
    {
        "family_id": "ipaex_mincho",
        "display_name": "IPAex明朝",
        "license": "IPA Font License",
        "vendor": "moji.or.jp",
        "preferred_name": "ipaexm.ttf",
        "urls": [
            "https://moji.or.jp/wp-content/ipafont/IPAexfont/ipaexm00401.zip",
        ],
        "mirrors": [
            "https://ipafont.ipa.go.jp/IPAexfont/ipaexm00401.zip",
        ],
        "kind": "zip_member",
        "member_globs": ["**/ipaexm.ttf", "ipaexm.ttf"],
        "notes": "公式 Ver.004.01",
        "expected_sha256": "7a306386f930fee80922f71eebf4ffe0f1ff2817da8e619230953487673d71c7",
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
        "expected_sha256": "769b5269f0f9bc6534b352c0e6bd856a566e03ff788f107191c2d835863570b2",
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
        "expected_sha256": None,  # corpus.yaml 参照
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
        "expected_sha256": None,
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
    req = urllib.request.Request(url, headers={"User-Agent": "myfont-fontdb/0.1"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def match_member(names: list[str], globs: list[str]) -> str | None:
    for g in globs:
        g = g.lstrip("*/")
        for n in names:
            if n == g or n.endswith(("/" + g, g)):
                return n
    return None


def is_variable_font(path: Path) -> bool:
    try:
        font = TTFont(str(path), lazy=True)
        has = "fvar" in font
        font.close()
        return has
    except (OSError, ValueError, KeyError, AssertionError):
        return False


def instantiate_wght400(src: Path, dst: Path) -> dict[str, Any]:
    font = TTFont(str(src))
    if "fvar" not in font:
        font.close()
        shutil.copy2(src, dst)
        return {"instanced": False, "coords": None}
    coords: dict[str, float] = {}
    if any(a.axisTag == "wght" for a in font["fvar"].axes):
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
            logger.info("GET %s", url)
            download(url, dest)
            if dest.stat().st_size < 1000:
                raise RuntimeError(f"too small: {dest.stat().st_size}")
            return url, None
        except (urllib.error.URLError, OSError, RuntimeError, TimeoutError) as e:
            errors.append(f"{url}: {e}")
            if dest.exists():
                dest.unlink()
    return None, "; ".join(errors)


def process_entry(entry: dict[str, Any], *, raw_dir: Path, fonts_dir: Path) -> dict[str, Any]:
    fid = entry["family_id"]
    logger.info("=== %s ===", fid)
    result: dict[str, Any] = {
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
    raw_dest = raw_dir / (f"{fid}.zip" if entry["kind"] == "zip_member" else raw_name)

    # 既に計測済みファイルがあり SHA が一致すればスキップ
    measured_guess = fonts_dir / f"{fid}-Regular.otf"
    if not measured_guess.exists():
        measured_guess = fonts_dir / f"{fid}-Regular.ttf"
    expected = entry.get("expected_sha256")
    if measured_guess.exists() and expected and sha256_file(measured_guess) == expected:
        result["acquired"] = True
        result["path_rel"] = str(measured_guess.relative_to(PACKAGE_ROOT))
        result["sha256_measured"] = expected
        result["is_variable"] = False
        font = TTFont(str(measured_guess), lazy=True)
        result["units_per_em"] = font["head"].unitsPerEm
        font.close()
        result["file_bytes"] = measured_guess.stat().st_size
        result["notes"] += " | reused existing file (sha match)"
        logger.info("REUSE %s", result["path_rel"])
        return result

    url, err = try_urls(urls, raw_dest)
    if url is None:
        result["error"] = err
        if entry.get("mirrors"):
            result["mirrors_tried"] = entry["mirrors"]
        logger.error("FAIL: %s", err)
        return result

    result["source_url"] = url
    result["sha256_source"] = sha256_file(raw_dest)

    extracted = fonts_dir / f"{fid}__raw__{raw_name}"
    try:
        if entry["kind"] == "zip_member":
            member = extract_zip_member(raw_dest, entry["member_globs"], extracted)
            result["zip_member"] = member
        else:
            shutil.copy2(raw_dest, extracted)

        variable = is_variable_font(extracted)
        result["is_variable"] = variable
        measured = fonts_dir / f"{fid}-Regular{extracted.suffix.lower()}"

        if variable:
            info = instantiate_wght400(extracted, measured)
            result["instanced_wght400"] = info["instanced"]
            result["instance_coords"] = info["coords"]
            result["notes"] += " | variable → instancer wght=400"
        else:
            shutil.copy2(extracted, measured)

        font = TTFont(str(measured), lazy=True)
        still_var = "fvar" in font
        upem = font["head"].unitsPerEm
        font.close()
        if still_var:
            result["error"] = "still variable after instantiate"
            return result

        digest = sha256_file(measured)
        if expected and digest != expected:
            result["error"] = f"sha256 mismatch: got {digest}, expected {expected}"
            logger.error("FAIL: %s", result["error"])
            return result

        result["acquired"] = True
        result["path_rel"] = str(measured.relative_to(PACKAGE_ROOT))
        result["sha256_measured"] = digest
        result["units_per_em"] = upem
        result["file_bytes"] = measured.stat().st_size
        logger.info("OK path=%s sha=%s…", result["path_rel"], digest[:16])
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as e:
        result["error"] = str(e)
        logger.error("FAIL: %s", e)
    return result


def fetch_all(*, write_corpus: bool = True) -> dict[str, Any]:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = FONTS_DIR / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # corpus.yaml に expected sha があればマージ
    expected_map: dict[str, str] = {}
    if CORPUS_YAML.exists():
        with open(CORPUS_YAML, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
        for fam in existing.get("families", []):
            if fam.get("sha256_measured"):
                expected_map[fam["family_id"]] = fam["sha256_measured"]

    specs = []
    for e in CORPUS_SPEC:
        e = dict(e)
        if not e.get("expected_sha256") and e["family_id"] in expected_map:
            e["expected_sha256"] = expected_map[e["family_id"]]
        specs.append(e)

    results = [process_entry(e, raw_dir=raw_dir, fonts_dir=FONTS_DIR) for e in specs]
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
    if write_corpus:
        with open(CORPUS_YAML, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        logger.info("wrote %s", CORPUS_YAML)
    logger.info("summary: %s", json.dumps(doc["summary"], ensure_ascii=False))
    return doc
