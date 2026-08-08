-- fontdb MVP schema (PLAN §2.2) — spike4 縮小実装
-- family → face → glyph_metric / probe_metric
-- + render_profile / extractor / probe_def

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS family (
    family_id       TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    license         TEXT NOT NULL,
    vendor          TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS face (
    face_id         TEXT PRIMARY KEY,
    family_id       TEXT NOT NULL REFERENCES family(family_id),
    face_kind       TEXT NOT NULL CHECK (face_kind IN ('opentype','ufo','svg_set','synthetic')),
    style_name      TEXT NOT NULL,
    weight_class    INTEGER,
    is_variable     INTEGER NOT NULL DEFAULT 0,
    instance_coords TEXT,          -- JSON e.g. {"wght":400} if instantiated
    path_rel        TEXT NOT NULL, -- relative to spike4/
    sha256          TEXT NOT NULL,
    source_url      TEXT,
    units_per_em    INTEGER
);

CREATE TABLE IF NOT EXISTS render_profile (
    render_profile_id TEXT PRIMARY KEY,
    em_px             INTEGER NOT NULL,
    hinting           TEXT NOT NULL,  -- off / on
    aa_mode           TEXT NOT NULL,  -- gray
    threshold         INTEGER NOT NULL,
    y_axis            TEXT NOT NULL,  -- image_down
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS extractor (
    extractor_version TEXT PRIMARY KEY,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS glyph_metric (
    face_id             TEXT NOT NULL REFERENCES face(face_id),
    codepoint           TEXT NOT NULL,  -- U+XXXX
    char_label          TEXT NOT NULL,
    render_profile_id   TEXT NOT NULL REFERENCES render_profile(render_profile_id),
    extractor_version   TEXT NOT NULL REFERENCES extractor(extractor_version),
    status              TEXT NOT NULL CHECK (status IN ('ok','missing','fail','low_confidence')),
    ink_bbox_x0         REAL,
    ink_bbox_y0         REAL,
    ink_bbox_x1         REAL,
    ink_bbox_y1         REAL,
    face_ratio          REAL,   -- ink_bbox area / EM^2
    black_density       REAL,   -- ink pixels / ink_bbox area
    centroid_x_em       REAL,
    centroid_y_em       REAL,
    advance_x_px        REAL,
    UNIQUE (face_id, codepoint, render_profile_id, extractor_version)
);

CREATE TABLE IF NOT EXISTS probe_def (
    probe_id    TEXT PRIMARY KEY,
    target_char TEXT NOT NULL,
    phase       TEXT NOT NULL,  -- alpha / beta
    description TEXT
);

CREATE TABLE IF NOT EXISTS probe_metric (
    face_id             TEXT NOT NULL REFERENCES face(face_id),
    probe_id            TEXT NOT NULL REFERENCES probe_def(probe_id),
    render_profile_id   TEXT NOT NULL REFERENCES render_profile(render_profile_id),
    extractor_version   TEXT NOT NULL REFERENCES extractor(extractor_version),
    status              TEXT NOT NULL CHECK (status IN ('ok','fail','low_confidence','skipped')),
    value               REAL,
    value_secondary     REAL,
    detail_json         TEXT,
    reason              TEXT,
    UNIQUE (face_id, probe_id, render_profile_id, extractor_version)
);
