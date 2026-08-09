"""SQLite 初期化・シード（PLAN T2）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from fontdb.config_load import load_render_profile
from fontdb.paths import (
    DEFAULT_PROFILE_ID,
    EXTRACTOR_VERSION,
    PROBE_DEFS_YAML,
    SCHEMA_SQL,
)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, *, reset: bool = False) -> None:
    if reset:
        conn.executescript(
            """
            DROP TABLE IF EXISTS face_param_link;
            DROP TABLE IF EXISTS design_param_snapshot;
            DROP TABLE IF EXISTS probe_metric;
            DROP TABLE IF EXISTS glyph_metric;
            DROP TABLE IF EXISTS probe_def;
            DROP TABLE IF EXISTS face;
            DROP TABLE IF EXISTS family;
            DROP TABLE IF EXISTS extractor;
            DROP TABLE IF EXISTS render_profile;
            """
        )
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    profile = load_render_profile(DEFAULT_PROFILE_ID)
    conn.execute(
        "INSERT OR REPLACE INTO render_profile VALUES (?,?,?,?,?,?,?)",
        (
            DEFAULT_PROFILE_ID,
            int(profile["em_px"]),
            str(profile.get("hinting", "off")),
            str(profile.get("aa_mode", "gray")),
            int(profile["threshold"]),
            str(profile.get("y_axis", "image_down")),
            str(profile.get("notes", "PLAN §2.3")),
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO extractor VALUES (?,?)",
        (EXTRACTOR_VERSION, "fontdb MVP: glyph ink + juu_contrast + san_uroko"),
    )
    if PROBE_DEFS_YAML.exists():
        with open(PROBE_DEFS_YAML, encoding="utf-8") as f:
            defs = yaml.safe_load(f) or {}
        for probe in (defs.get("probes") or {}).values():
            conn.execute(
                "INSERT OR REPLACE INTO probe_def VALUES (?,?,?,?)",
                (
                    probe["probe_id"],
                    probe["target_char"],
                    probe["phase"],
                    probe.get("description", ""),
                ),
            )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO probe_def VALUES (?,?,?,?)",
            ("juu_contrast", "十", "alpha", "縦/横コントラスト（交点回避走査）"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO probe_def VALUES (?,?,?,?)",
            ("san_uroko", "三", "alpha", "三の上横画右端うろこ相対サイズ"),
        )
    conn.commit()
