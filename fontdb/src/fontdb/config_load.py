"""config/*.yaml の読み込み（掟7: プロトコル正本は YAML）。"""

from __future__ import annotations

from typing import Any

import yaml

from fontdb.paths import (
    DEFAULT_PROFILE_ID,
    PROBE_DEFS_YAML,
    RENDER_PROFILES_YAML,
)


def load_yaml(path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_render_profile(profile_id: str = DEFAULT_PROFILE_ID) -> dict[str, Any]:
    doc = load_yaml(RENDER_PROFILES_YAML)
    profiles = doc.get("profiles") or {}
    if profile_id not in profiles:
        raise KeyError(f"unknown render_profile: {profile_id}")
    p = dict(profiles[profile_id])
    p["render_profile_id"] = profile_id
    return p


def load_probe_defs() -> dict[str, Any]:
    return load_yaml(PROBE_DEFS_YAML)


def corpus_glyphs(defs: dict[str, Any] | None = None) -> list[str]:
    defs = defs if defs is not None else load_probe_defs()
    common = defs.get("common") or {}
    glyphs = common.get("corpus_glyphs")
    if not glyphs:
        raise ValueError("probe_defs.yaml common.corpus_glyphs が未定義（掟7）")
    return list(glyphs)


def juu_kwargs(defs: dict[str, Any] | None = None) -> dict[str, Any]:
    defs = defs if defs is not None else load_probe_defs()
    juu = (defs.get("probes") or {}).get("juu_contrast") or {}
    proto = juu.get("protocol") or {}
    fracs = proto.get("scan_offsets_face_frac") or [0.15, 0.22]
    max_run = proto.get("max_run_frac") or {}
    return {
        "scan_fracs": tuple(float(x) for x in fracs),
        "max_run_frac": float(max_run.get("vertical", 0.35)),
    }


def san_kwargs(defs: dict[str, Any] | None = None) -> dict[str, Any]:
    defs = defs if defs is not None else load_probe_defs()
    san = (defs.get("probes") or {}).get("san_uroko") or {}
    thr = san.get("thresholds") or {}
    proto = san.get("protocol") or {}
    kwargs: dict[str, Any] = {
        "fallback_char": san.get("fallback_char") or "二",
        "target_char": san.get("target_char") or "三",
    }
    mapping = {
        "clear_protrusion_px": thr.get("clear_protrusion_px"),
        "clear_relative_min": thr.get("clear_relative_min"),
        "stylistic_zero_px": thr.get("stylistic_zero_px"),
        "stylistic_zero_relative_max": thr.get("stylistic_zero_relative_max"),
        "height_boost_px": thr.get("height_boost_px"),
        "height_boost_relative_min": thr.get("height_boost_relative_min"),
        "top_region_frac": proto.get("top_region_frac"),
        "projection_peak_frac": proto.get("projection_peak_frac"),
        "fallback_top_frac": proto.get("fallback_top_frac"),
        "right_roi_frac": proto.get("right_roi_frac"),
        "smooth_kernel": proto.get("smooth_kernel"),
    }
    if proto.get("body_column_frac"):
        kwargs["body_column_frac"] = tuple(proto["body_column_frac"])
    for k, v in mapping.items():
        if v is not None:
            kwargs[k] = v
    return kwargs
