"""P0: design_param_snapshot 正式固定。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fontdb.ingest.db import connect, init_db
from fontdb.ingest.snapshots import (
    assert_engine_params_match_yaml,
    freeze_product_r1,
    load_params_doc,
    params_sha256_from_doc,
    upsert_design_param_snapshot,
)


def test_product_r1_yaml_is_frozen():
    doc = load_params_doc("product_r1")
    assert doc.get("status") == "frozen"
    assert doc.get("snapshot_id") == "product_r1"
    assert "params" in doc
    assert float(doc["params"]["v_thickness"]) == 110.0
    assert doc.get("frozen_at")


def test_engine_params_match_yaml():
    sha = assert_engine_params_match_yaml("product_r1")
    assert len(sha) == 64


def test_freeze_product_r1_into_db(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    meta = freeze_product_r1(conn, link_face_ids=["missing_face"])
    conn.commit()
    assert meta["status"] == "frozen"
    assert meta["params_sha256"] == params_sha256_from_doc(
        load_params_doc("product_r1")
    )
    # YAML frozen_at を採用
    assert meta["frozen_at"] == str(load_params_doc("product_r1")["frozen_at"])
    row = conn.execute(
        "SELECT status, params_sha256 FROM design_param_snapshot WHERE snapshot_id='product_r1'"
    ).fetchone()
    assert row[0] == "frozen"
    assert row[1] == meta["params_sha256"]
    n = conn.execute(
        "SELECT COUNT(*) FROM face_param_link WHERE snapshot_id='product_r1'"
    ).fetchone()[0]
    assert n == 0
    conn.close()


def test_refreeze_preserves_frozen_at(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    m1 = freeze_product_r1(conn)
    conn.commit()
    m2 = freeze_product_r1(conn)
    conn.commit()
    assert m1["frozen_at"] == m2["frozen_at"]
    assert m2.get("reused_frozen_at") is True
    conn.close()


def test_frozen_params_mutation_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    freeze_product_r1(conn, check_engine=False)
    conn.commit()

    doc = load_params_doc("product_r1")
    doc = dict(doc)
    params = dict(doc["params"])
    params["v_thickness"] = 999.0
    doc["params"] = params

    monkeypatch.setattr(
        "fontdb.ingest.snapshots.load_params_doc",
        lambda snapshot_id: doc,
    )
    with pytest.raises(ValueError, match="params_sha256 changed"):
        upsert_design_param_snapshot(conn, "product_r1", status="frozen")
    conn.close()


def test_frozen_cannot_downgrade_to_candidate(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    freeze_product_r1(conn, check_engine=False)
    conn.commit()
    with pytest.raises(ValueError, match="cannot downgrade"):
        upsert_design_param_snapshot(conn, "product_r1", status="candidate")
    conn.close()


def test_refuse_db_frozen_when_yaml_not_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    doc = load_params_doc("product_r1")
    doc = dict(doc)
    doc["status"] = "candidate"
    monkeypatch.setattr(
        "fontdb.ingest.snapshots.load_params_doc",
        lambda snapshot_id: doc,
    )
    with pytest.raises(ValueError, match="refusing to write DB status=frozen"):
        upsert_design_param_snapshot(conn, "product_r1", status="frozen")
    conn.close()


def test_link_existing_face(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_db(conn, reset=True)
    conn.execute(
        "INSERT INTO family VALUES (?,?,?,?,?)",
        ("mymincho_t7_product_r1", "t", "proprietary-self", None, None),
    )
    conn.execute(
        "INSERT INTO face VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "mymincho_t7_product_r1_regular",
            "mymincho_t7_product_r1",
            "synthetic",
            "Regular",
            400,
            0,
            None,
            "data/synthetic/x.otf",
            "a" * 64,
            None,
            1000,
        ),
    )
    upsert_design_param_snapshot(conn, "product_r1", status="frozen")
    freeze_product_r1(
        conn, link_face_ids=["mymincho_t7_product_r1_regular"]
    )
    conn.commit()
    link = conn.execute(
        "SELECT snapshot_id FROM face_param_link WHERE face_id=?",
        ("mymincho_t7_product_r1_regular",),
    ).fetchone()
    assert link[0] == "product_r1"
    conn.close()
