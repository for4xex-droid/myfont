"""T7+: synthetic face SQLite ingest。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from fontdb.ingest.db import connect, init_db
from fontdb.ingest.synthetic import (
    load_synthetic_faces_config,
    measure_otf_into_db,
    notes_with_params,
    protocol_glyphs,
    sha256_file,
)
from fontdb.paths import PACKAGE_ROOT, SYNTHETIC_FACES_YAML


def test_synthetic_faces_yaml_declares_classic_and_product_r1():
    doc = load_synthetic_faces_config()
    assert doc["protocol"]["face_kind"] == "synthetic"
    assert doc["protocol"]["profile"] == "ft_1024_nohint_gray_v1"
    assert "十" in protocol_glyphs(doc)
    assert "三" in protocol_glyphs(doc)
    names = {f["params_name"] for f in doc["faces"]}
    assert names >= {"classic", "product_r1"}


def test_notes_with_params_embeds_sha():
    n = notes_with_params("hello", params_name="classic", params_sha256="abc")
    assert "params_name=classic" in n
    assert "params_sha256=abc" in n
    assert "hello" in n


def test_face_kind_must_be_synthetic(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    otf = tmp_path / "x.otf"
    otf.write_bytes(b"not-a-font")
    with pytest.raises(ValueError, match="synthetic"):
        measure_otf_into_db(
            conn,
            otf_path=otf,
            family_id="x",
            face_id="x_regular",
            display_name="x",
            license="proprietary-self",
            vendor="t",
            notes=None,
            style_name="Regular",
            weight_class=400,
            path_rel="data/synthetic/x.otf",
            sha256="0" * 64,
            face_kind="opentype",
            glyphs=["十"],
        )
    conn.close()


def test_glyphs_required(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    otf = tmp_path / "x.otf"
    otf.write_bytes(b"x")
    with pytest.raises(ValueError, match="glyphs"):
        measure_otf_into_db(
            conn,
            otf_path=otf,
            family_id="x",
            face_id="x_regular",
            display_name="x",
            license="proprietary-self",
            vendor="t",
            notes=None,
            style_name="Regular",
            weight_class=400,
            path_rel="data/synthetic/x.otf",
            sha256="0" * 64,
            face_kind="synthetic",
            glyphs=None,
        )
    conn.close()


def test_path_rel_must_match_otf(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    otf = tmp_path / "x.otf"
    otf.write_bytes(b"x")
    with pytest.raises(ValueError, match="mismatch"):
        measure_otf_into_db(
            conn,
            otf_path=otf,
            family_id="x",
            face_id="x_regular",
            display_name="x",
            license="proprietary-self",
            vendor="t",
            notes=None,
            style_name="Regular",
            weight_class=400,
            path_rel="data/synthetic/other.otf",
            sha256="0" * 64,
            face_kind="synthetic",
            glyphs=["十", "三", "二"],
        )
    conn.close()


def test_ingest_product_r1_into_tmp_db(tmp_path: Path):
    pytest.importorskip("pathops")
    pytest.importorskip("ufoLib2")
    pytest.importorskip("fontmake")
    engine_src = PACKAGE_ROOT.parent / "engine" / "src"
    assert engine_src.is_dir()

    from fontdb.ingest.synthetic import ingest_synthetic_faces

    db = tmp_path / "fontdb.sqlite"
    report = ingest_synthetic_faces(
        params_filter=["product_r1"],
        db_path=db,
        reset_db=True,
        work_root=tmp_path / "build",
        save_rasters=False,
    )
    assert "mymincho_t7_product_r1" in report["faces"]
    assert report["faces"]["mymincho_t7_product_r1"]["params_sha256"]
    juu = report["faces"]["mymincho_t7_product_r1"]["probes"]["juu_contrast"]
    assert juu["status"] == "ok"
    assert juu["value"] is not None and juu["value"] > 1.5

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT face_kind, sha256 FROM face WHERE face_id=?",
        ("mymincho_t7_product_r1_regular",),
    ).fetchone()
    assert row is not None
    assert row[0] == "synthetic"
    assert len(row[1]) == 64
    notes = conn.execute(
        "SELECT notes FROM family WHERE family_id=?",
        ("mymincho_t7_product_r1",),
    ).fetchone()[0]
    assert "params_name=product_r1" in notes
    assert "params_sha256=" in notes
    probe = conn.execute(
        """SELECT status, value FROM probe_metric
           WHERE face_id=? AND probe_id='juu_contrast'""",
        ("mymincho_t7_product_r1_regular",),
    ).fetchone()
    assert probe[0] == "ok"
    assert probe[1] > 1.5
    conn.close()


def test_sha256_file(tmp_path: Path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_yaml_path_exists():
    assert SYNTHETIC_FACES_YAML.is_file()
    doc = yaml.safe_load(SYNTHETIC_FACES_YAML.read_text(encoding="utf-8"))
    assert len(doc["faces"]) >= 2
