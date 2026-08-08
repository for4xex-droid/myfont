"""T7+: engine 一時 OTF を face_kind=synthetic として SQLite へ正式 ingest。

掟4: 接合前 poly を freetype profile で偽らない。
ここでは union→OTF 済みのため ft_1024_nohint_gray_v1 で計測してよい。
face_kind は必ず synthetic（出自の明示）。
掟16: family.notes に params_name + params_sha256 を機械可読で残す。
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from fontdb.config_load import load_render_profile
from fontdb.ingest.db import connect, init_db
from fontdb.paths import (
    DEFAULT_PROFILE_ID,
    EXTRACTOR_VERSION,
    PACKAGE_ROOT,
    SYNTHETIC_DIR,
    SYNTHETIC_FACES_YAML,
)
from fontdb.pipeline import (
    ensure_glyphs_for_probes,
    measure_face_metrics,
    resolve_probe_protocol,
)
from fontdb.render.freetype_raster import load_face
from fontdb.util.paths_safe import resolve_under

logger = logging.getLogger(__name__)


def _ensure_engine_on_path() -> None:
    engine_src = PACKAGE_ROOT.parent / "engine" / "src"
    if engine_src.is_dir() and str(engine_src) not in sys.path:
        sys.path.insert(0, str(engine_src))


def load_synthetic_faces_config(path: Path | None = None) -> dict[str, Any]:
    p = path or SYNTHETIC_FACES_YAML
    with open(p, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    if not doc.get("faces"):
        raise ValueError(f"no faces in {p}")
    return doc


def protocol_glyphs(doc: dict[str, Any]) -> list[str]:
    """synthetic_faces.yaml protocol.glyphs を正とする（掟7）。"""
    protocol = doc.get("protocol") or {}
    glyphs = protocol.get("glyphs")
    if not glyphs:
        raise ValueError(
            "synthetic_faces.yaml protocol.glyphs が未定義（掟7）"
        )
    return [str(g) for g in glyphs]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def params_snapshot_sha256(params_name: str) -> tuple[str, dict[str, Any]]:
    """engine PARAM_SETS の内容ハッシュ（掟16）。"""
    _ensure_engine_on_path()
    from engine.params import PARAM_SETS

    if params_name not in PARAM_SETS:
        raise KeyError(f"unknown params: {params_name}")
    snap = asdict(PARAM_SETS[params_name])
    payload = json.dumps(snap, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), snap


def notes_with_params(
    base_notes: str | None,
    *,
    params_name: str,
    params_sha256: str,
) -> str:
    """人間向け notes ＋機械可読な params 紐付け行。"""
    lines = []
    if base_notes:
        lines.append(str(base_notes).rstrip())
    lines.append(f"params_name={params_name}")
    lines.append(f"params_sha256={params_sha256}")
    return "\n".join(lines)


def build_and_stage_otf(
    params_name: str,
    *,
    dest_otf: Path,
    family_name: str,
    glyph_ids: list[str] | None = None,
    work_root: Path | None = None,
) -> Path:
    """engine.bridge で一時 OTF を作り data/synthetic へ配置。"""
    _ensure_engine_on_path()
    from engine.bridge import CORE_GLYPHS, build_temp_font

    ids = glyph_ids or list(CORE_GLYPHS.keys())
    work = work_root or (dest_otf.parent / "_build" / params_name)
    work.mkdir(parents=True, exist_ok=True)
    result = build_temp_font(
        params_name,
        glyph_ids=ids,
        out_root=work,
        family_name=family_name,
        keep_ufo=False,
    )
    if not result.fill_check.get("ok"):
        raise RuntimeError(
            f"fill check failed for {params_name}: {result.fill_check}"
        )
    dest_otf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(result.otf_path, dest_otf)
    return dest_otf


def measure_otf_into_db(
    conn: sqlite3.Connection,
    *,
    otf_path: Path,
    family_id: str,
    face_id: str,
    display_name: str,
    license: str,
    vendor: str | None,
    notes: str | None,
    style_name: str,
    weight_class: int,
    path_rel: str,
    sha256: str,
    face_kind: str = "synthetic",
    glyphs: list[str] | None = None,
    profile_id: str = DEFAULT_PROFILE_ID,
    save_rasters: bool = True,
) -> dict[str, Any]:
    """1 OTF を family/face/glyph_metric/probe_metric へ書き込む。"""
    if face_kind != "synthetic":
        raise ValueError(
            f"T7+ ingest requires face_kind='synthetic', got {face_kind!r}"
        )
    if not glyphs:
        raise ValueError("glyphs must be provided from synthetic_faces.yaml (掟7)")

    profile = load_render_profile(profile_id)
    em_px = int(profile["em_px"])
    threshold = int(profile["threshold"])
    hinting = str(profile.get("hinting", "off")) == "on"
    proto = resolve_probe_protocol()
    glyphs = ensure_glyphs_for_probes(
        glyphs,
        juu_target=proto["juu_target"],
        san_target=proto["san_target"],
        san_fallback=proto["san_fallback"],
    )

    expected = resolve_under(PACKAGE_ROOT, path_rel).resolve()
    actual = otf_path.resolve()
    if actual != expected:
        raise ValueError(
            f"otf_path/path_rel mismatch: {actual} != {expected}"
        )
    if not actual.is_file():
        raise FileNotFoundError(actual)

    face_ft = load_face(str(actual), em_px=em_px)
    upm = int(face_ft.units_per_EM)

    conn.execute(
        "INSERT OR REPLACE INTO family VALUES (?,?,?,?,?)",
        (family_id, display_name, license, vendor, notes),
    )
    conn.execute(
        "INSERT OR REPLACE INTO face VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            face_id,
            family_id,
            face_kind,
            style_name,
            weight_class,
            0,
            None,
            path_rel,
            sha256,
            None,
            upm,
        ),
    )

    face_report = measure_face_metrics(
        conn,
        face_ft,
        face_id=face_id,
        log_label=face_id,
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
        raster_prefix=family_id,
    )
    face_report.pop("_juu", None)
    face_report.pop("_san", None)
    face_report["face_id"] = face_id
    face_report["path_rel"] = path_rel
    face_report["sha256"] = sha256
    return face_report


def ingest_synthetic_faces(
    *,
    params_filter: list[str] | None = None,
    db_path: Path | None = None,
    reset_db: bool = False,
    work_root: Path | None = None,
    save_rasters: bool = True,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """synthetic_faces.yaml の面をビルド→配置→計測→SQLite 登録。"""
    from fontdb.paths import DB_PATH

    doc = load_synthetic_faces_config(config_path)
    protocol = doc.get("protocol") or {}
    profile_id = str(protocol.get("profile", DEFAULT_PROFILE_ID))
    face_kind = str(protocol.get("face_kind", "synthetic"))
    path_prefix = str(protocol.get("path_prefix", "data/synthetic"))
    glyphs = protocol_glyphs(doc)

    faces_cfg = list(doc["faces"])
    if params_filter:
        wanted = set(params_filter)
        faces_cfg = [f for f in faces_cfg if f["params_name"] in wanted]
    if not faces_cfg:
        raise ValueError("no synthetic faces matched filter")

    db = db_path or DB_PATH
    conn = connect(db)
    init_db(conn, reset=reset_db)

    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "profile": profile_id,
        "extractor": EXTRACTOR_VERSION,
        "faces": {},
        "probe_summary": [],
    }

    for fam in faces_cfg:
        params_name = fam["params_name"]
        family_id = fam["family_id"]
        face_id = fam["face_id"]
        dest_name = f"{family_id}-Regular.otf"
        path_rel = f"{path_prefix}/{dest_name}"
        dest = resolve_under(PACKAGE_ROOT, path_rel)

        params_sha, params_snap = params_snapshot_sha256(params_name)
        fam_notes = notes_with_params(
            fam.get("notes"),
            params_name=params_name,
            params_sha256=params_sha,
        )

        logger.info("T7+ build+ingest %s (%s)", face_id, params_name)
        build_and_stage_otf(
            params_name,
            dest_otf=dest,
            family_name=fam["display_name"].replace(" ", ""),
            work_root=(work_root or SYNTHETIC_DIR / "_build") / params_name,
        )
        digest = sha256_file(dest)
        # 掟16: params snapshot を OTF 横に JSON でも残す（gitignore 配下）
        snap_path = dest.with_suffix(".params.json")
        snap_path.write_text(
            json.dumps(
                {
                    "params_name": params_name,
                    "params_sha256": params_sha,
                    "params": params_snap,
                    "otf_sha256": digest,
                    "face_id": face_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        face_report = measure_otf_into_db(
            conn,
            otf_path=dest,
            family_id=family_id,
            face_id=face_id,
            display_name=fam["display_name"],
            license=fam.get("license", "proprietary-self"),
            vendor=fam.get("vendor"),
            notes=fam_notes,
            style_name=fam.get("style_name", "Regular"),
            weight_class=int(fam.get("weight_class", 400)),
            path_rel=path_rel,
            sha256=digest,
            face_kind=face_kind,
            glyphs=glyphs,
            profile_id=profile_id,
            save_rasters=save_rasters,
        )
        face_report["params_name"] = params_name
        face_report["params_sha256"] = params_sha
        report["faces"][family_id] = face_report
        juu = face_report["probes"].get("juu_contrast", {})
        san = face_report["probes"].get("san_uroko", {})
        report["probe_summary"].append(
            {
                "family_id": family_id,
                "params_name": params_name,
                "params_sha256": params_sha,
                "face_id": face_id,
                "contrast": juu.get("value"),
                "uroko_rel": san.get("value"),
                "juu_status": juu.get("status"),
                "san_status": san.get("status"),
                "sha256": digest,
                "path_rel": path_rel,
            }
        )

    conn.commit()
    conn.close()
    return report
