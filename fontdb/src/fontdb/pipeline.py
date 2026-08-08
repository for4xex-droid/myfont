"""計測パイプライン（T3〜T5α）。"""

from __future__ import annotations

import json
import logging
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


def _probe_for_char(
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
        return {"status": "fail", "reason": f"missing canvas for {target!r}", "value": None}
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
        # どちらもダメなら primary を返す
        res["fallback_attempted"] = fallback
        res["fallback_status"] = fb.get("status")
    return res


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
    glyphs = glyphs or corpus_glyphs(defs)
    # probe 対象字が欠けていれば追加
    for ch in ("十", "三", "二"):
        if ch not in glyphs:
            glyphs.append(ch)

    j_kw = juu_kwargs(defs)
    s_kw_full = san_kwargs(defs)
    san_fallback = s_kw_full.pop("fallback_char", "二")
    san_target = s_kw_full.pop("target_char", "三")
    # measure_san_uroko に渡さないキーを除去
    s_kw = {k: v for k, v in s_kw_full.items() if k not in ("fallback_char", "target_char")}

    with open(CORPUS_YAML, encoding="utf-8") as f:
        corpus = yaml.safe_load(f)
    families = [x for x in corpus["families"] if x.get("acquired")]
    if not families:
        raise SystemExit("acquired fonts がありません。scripts/01_fetch.py を先に実行してください")

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
            (fid, fam["display_name"], fam["license"], fam.get("vendor"), fam.get("notes")),
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
                json.dumps(fam.get("instance_coords")) if fam.get("instance_coords") else None,
                fam["path_rel"],
                fam["sha256_measured"],
                fam.get("source_url"),
                fam.get("units_per_em") or face_ft.units_per_EM,
            ),
        )

        face_report: dict[str, Any] = {"path": fam["path_rel"], "glyphs": {}, "probes": {}}
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
                float(meta["advance_x"]) / em_px if meta.get("advance_x") is not None else None
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
            if save_rasters and ch in ("十", "三"):
                Image.fromarray(canvas, mode="L").save(RENDERS_DIR / f"{fid}_{ch}.png")

        juu = measure_juu_contrast(
            canvases["十"],
            threshold=threshold,
            em_px=em_px,
            **j_kw,
        )
        # value_secondary 等の px は detail_json のみ（掟2）
        juu_for_db = dict(juu)
        if juu.get("vert_thickness_px") is not None:
            juu_for_db["vert_thickness_em"] = juu["vert_thickness_px"] / em_px
            juu_for_db["horiz_thickness_em"] = juu["horiz_thickness_px"] / em_px
            # カラム value_secondary も EM（掟2）。px は detail_json に残す
            juu_for_db["value_secondary"] = juu_for_db["horiz_thickness_em"]

        san = _probe_for_char(
            canvases,
            target=san_target,
            fallback=san_fallback,
            measure_fn=measure_san_uroko,
            kwargs=s_kw,
            threshold=threshold,
        )

        for probe_id, res in (("juu_contrast", juu_for_db), ("san_uroko", san)):
            row = dict(res)
            # san の value_secondary は突起 px → EM（掟2）
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
            res = row  # for face_report below
            face_report["probes"][probe_id] = {
                "status": res["status"],
                "value": res.get("value"),
                "reason": res.get("reason"),
                "measured_char": res.get("measured_char"),
            }
            logger.info(
                "%s %s: %s value=%s",
                fid,
                probe_id,
                res["status"],
                res.get("value"),
            )

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
