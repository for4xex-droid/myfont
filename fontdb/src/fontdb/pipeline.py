"""計測パイプライン（T3〜T5α）。"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Sequence
from typing import Any

import yaml
from PIL import Image

from fontdb.config_load import (
    corpus_glyphs,
    juu_kwargs,
    load_probe_defs,
    load_render_profile,
    san_kwargs,
)
from fontdb.ingest.db import connect, init_db
from fontdb.metrics.ink import ink_metrics
from fontdb.paths import (
    CORPUS_YAML,
    DB_PATH,
    DEFAULT_PROFILE_ID,
    EXTRACTOR_VERSION,
    PACKAGE_ROOT,
    RENDERS_DIR,
)
from fontdb.probes.juu_contrast import measure_juu_contrast
from fontdb.probes.san_uroko import measure_san_uroko
from fontdb.render.freetype_raster import (
    load_face,
    place_on_em_canvas,
    render_glyph_gray,
)
from fontdb.util.paths_safe import resolve_under

logger = logging.getLogger(__name__)


def codepoint(ch: str) -> str:
    return f"U+{ord(ch):04X}"


def probe_for_char(
    canvases: dict[str, Any],
    *,
    target: str,
    fallback: str | None,
    measure_fn,
    kwargs: dict[str, Any],
    threshold: int,
) -> dict[str, Any]:
    """target で測り、fail/low_confidence なら fallback_char を試す（掟6/7）。"""
    if target not in canvases:
        return {
            "status": "fail",
            "reason": f"missing canvas for {target!r}",
            "value": None,
        }
    res = measure_fn(canvases[target], threshold=threshold, **kwargs)
    res["measured_char"] = target
    if res.get("status") in ("ok",) or not fallback or fallback not in canvases:
        return res
    if res.get("status") in ("fail", "low_confidence"):
        fb = measure_fn(canvases[fallback], threshold=threshold, **kwargs)
        fb["measured_char"] = fallback
        fb["fallback_from"] = target
        fb["primary_status"] = res.get("status")
        fb["primary_reason"] = res.get("reason")
        if fb.get("status") == "ok":
            return fb
        res["fallback_attempted"] = fallback
        res["fallback_status"] = fb.get("status")
    return res


def resolve_probe_protocol(
    defs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """probe_defs.yaml から juu/san の代表字と kwargs を解決（掟7）。"""
    defs = defs if defs is not None else load_probe_defs()
    juu_probe = (defs.get("probes") or {}).get("juu_contrast") or {}
    juu_target = juu_probe.get("target_char")
    if not juu_target:
        raise ValueError("probe_defs juu_contrast.target_char 未定義（掟7）")

    j_kw = juu_kwargs(defs)
    san_probe = (defs.get("probes") or {}).get("san_uroko") or {}
    san_target = san_probe.get("target_char")
    san_fallback = san_probe.get("fallback_char")
    if not san_target or not san_fallback:
        raise ValueError(
            "probe_defs san_uroko.target_char/fallback_char 未定義（掟7）"
        )
    s_kw_full = san_kwargs(defs)
    s_kw = {
        k: v
        for k, v in s_kw_full.items()
        if k not in ("fallback_char", "target_char")
    }
    return {
        "juu_target": str(juu_target),
        "san_target": str(san_target),
        "san_fallback": str(san_fallback),
        "j_kw": j_kw,
        "s_kw": s_kw,
    }


def ensure_glyphs_for_probes(
    glyphs: Sequence[str],
    *,
    juu_target: str,
    san_target: str,
    san_fallback: str,
) -> list[str]:
    out = list(glyphs)
    for ch in (juu_target, san_target, san_fallback):
        if ch not in out:
            out.append(ch)
    return out


def measure_face_metrics(
    conn: sqlite3.Connection,
    face_ft,
    *,
    face_id: str,
    log_label: str,
    glyphs: Sequence[str],
    profile_id: str,
    em_px: int,
    threshold: int,
    hinting: bool,
    juu_target: str,
    san_target: str,
    san_fallback: str,
    j_kw: dict[str, Any],
    s_kw: dict[str, Any],
    save_rasters: bool = True,
    raster_prefix: str | None = None,
) -> dict[str, Any]:
    """1 face の glyph_metric + probe_metric を書き込み、report 断片を返す。"""
    raster_chars = {juu_target, san_target}
    prefix = raster_prefix or log_label
    face_report: dict[str, Any] = {"glyphs": {}, "probes": {}}
    canvases: dict[str, Any] = {}

    for ch in glyphs:
        gray, meta = render_glyph_gray(face_ft, ch, hinting=hinting)
        gid = meta.get("glyph_index", face_ft.get_char_index(ord(ch)))
        canvas = place_on_em_canvas(gray, meta, em_px=em_px)
        canvases[ch] = canvas
        m = ink_metrics(canvas, threshold=threshold, em_px=em_px)
        if gid == 0:
            m = {"status": "missing", "reason": "cmap missing (gid=0)"}
        status = m["status"]
        bbox = m.get("ink_bbox")
        # 掟2: カラムは EM 正規化のみ
        if bbox:
            bbox_em = [v / em_px for v in bbox]
        else:
            bbox_em = [None, None, None, None]
        advance_em = (
            float(meta["advance_x"]) / em_px
            if meta.get("advance_x") is not None
            else None
        )
        conn.execute(
            """INSERT OR REPLACE INTO glyph_metric VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                face_id,
                codepoint(ch),
                ch,
                profile_id,
                EXTRACTOR_VERSION,
                status,
                bbox_em[0],
                bbox_em[1],
                bbox_em[2],
                bbox_em[3],
                m.get("face_ratio"),
                m.get("black_density"),
                m.get("centroid_x_em"),
                m.get("centroid_y_em"),
                advance_em,
            ),
        )
        face_report["glyphs"][ch] = {
            "status": status,
            "face_ratio": m.get("face_ratio"),
            "black_density": m.get("black_density"),
        }
        if save_rasters and ch in raster_chars:
            RENDERS_DIR.mkdir(parents=True, exist_ok=True)
            Image.fromarray(canvas, mode="L").save(
                RENDERS_DIR / f"{prefix}_{ch}.png"
            )

    if juu_target not in canvases:
        raise ValueError(f"missing canvas for juu target {juu_target!r}")
    juu = measure_juu_contrast(
        canvases[juu_target],
        threshold=threshold,
        em_px=em_px,
        **j_kw,
    )
    juu_for_db = dict(juu)
    if juu.get("vert_thickness_px") is not None:
        juu_for_db["vert_thickness_em"] = juu["vert_thickness_px"] / em_px
        juu_for_db["horiz_thickness_em"] = juu["horiz_thickness_px"] / em_px
        # カラム value_secondary も EM（掟2）。px は detail_json に残す
        juu_for_db["value_secondary"] = juu_for_db["horiz_thickness_em"]

    san = probe_for_char(
        canvases,
        target=san_target,
        fallback=san_fallback,
        measure_fn=measure_san_uroko,
        kwargs=s_kw,
        threshold=threshold,
    )

    for probe_id, res in (("juu_contrast", juu_for_db), ("san_uroko", san)):
        row = dict(res)
        if probe_id == "san_uroko" and row.get("value_secondary") is not None:
            row["uroko_protrusion_px"] = row["value_secondary"]
            row["value_secondary"] = float(row["value_secondary"]) / em_px
        conn.execute(
            """INSERT OR REPLACE INTO probe_metric VALUES
            (?,?,?,?,?,?,?,?,?)""",
            (
                face_id,
                probe_id,
                profile_id,
                EXTRACTOR_VERSION,
                row["status"],
                row.get("value"),
                row.get("value_secondary"),
                json.dumps(
                    {k: v for k, v in row.items() if k not in ("status",)},
                    ensure_ascii=False,
                    default=str,
                ),
                row.get("reason"),
            ),
        )
        face_report["probes"][probe_id] = {
            "status": row["status"],
            "value": row.get("value"),
            "reason": row.get("reason"),
            "measured_char": row.get("measured_char"),
        }
        logger.info(
            "%s %s: %s value=%s",
            log_label,
            probe_id,
            row["status"],
            row.get("value"),
        )

    face_report["_juu"] = juu
    face_report["_san"] = san
    return face_report


def run_measure(
    *,
    glyphs: list[str] | None = None,
    reset_db: bool = True,
    save_rasters: bool = True,
    profile_id: str = DEFAULT_PROFILE_ID,
) -> dict[str, Any]:
    profile = load_render_profile(profile_id)
    em_px = int(profile["em_px"])
    threshold = int(profile["threshold"])
    hinting = str(profile.get("hinting", "off")) == "on"

    defs = load_probe_defs()
    proto = resolve_probe_protocol(defs)
    glyphs = ensure_glyphs_for_probes(
        glyphs or corpus_glyphs(defs),
        juu_target=proto["juu_target"],
        san_target=proto["san_target"],
        san_fallback=proto["san_fallback"],
    )

    with open(CORPUS_YAML, encoding="utf-8") as f:
        corpus = yaml.safe_load(f)
    families = [x for x in corpus["families"] if x.get("acquired")]
    if not families:
        raise SystemExit(
            "acquired fonts がありません。scripts/01_fetch.py を先に実行してください"
        )

    conn = connect(DB_PATH)
    init_db(conn, reset=reset_db)
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "profile": profile_id,
        "extractor": EXTRACTOR_VERSION,
        "glyphs": glyphs,
        "faces": {},
        "probe_summary": [],
    }

    for fam in families:
        fid = fam["family_id"]
        path = resolve_under(PACKAGE_ROOT, fam["path_rel"])
        if not path.is_file():
            raise FileNotFoundError(f"font missing: {path}")
        logger.info("measure %s", fid)
        face_ft = load_face(str(path), em_px=em_px)
        style_name = face_ft.style_name
        if isinstance(style_name, bytes):
            style_name = style_name.decode("utf-8", "replace")

        conn.execute(
            "INSERT OR REPLACE INTO family VALUES (?,?,?,?,?)",
            (
                fid,
                fam["display_name"],
                fam["license"],
                fam.get("vendor"),
                fam.get("notes"),
            ),
        )
        face_id = f"{fid}_regular"
        conn.execute(
            "INSERT OR REPLACE INTO face VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                face_id,
                fid,
                "opentype",
                style_name or "Regular",
                400,
                1 if fam.get("is_variable") else 0,
                json.dumps(fam.get("instance_coords"))
                if fam.get("instance_coords")
                else None,
                fam["path_rel"],
                fam["sha256_measured"],
                fam.get("source_url"),
                fam.get("units_per_em") or face_ft.units_per_EM,
            ),
        )

        face_report = measure_face_metrics(
            conn,
            face_ft,
            face_id=face_id,
            log_label=fid,
            glyphs=glyphs,
            profile_id=profile_id,
            em_px=em_px,
            threshold=threshold,
            hinting=hinting,
            juu_target=proto["juu_target"],
            san_target=proto["san_target"],
            san_fallback=proto["san_fallback"],
            j_kw=proto["j_kw"],
            s_kw=proto["s_kw"],
            save_rasters=save_rasters,
            raster_prefix=fid,
        )
        juu = face_report.pop("_juu")
        san = face_report.pop("_san")
        face_report["path"] = fam["path_rel"]
        report["faces"][fid] = face_report
        report["probe_summary"].append(
            {
                "family_id": fid,
                "display_name": fam["display_name"],
                "contrast": juu.get("value"),
                "uroko_rel": san.get("value"),
                "juu_status": juu["status"],
                "san_status": san["status"],
            }
        )

    conn.commit()
    conn.close()
    return report
