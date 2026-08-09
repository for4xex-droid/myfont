"""design_param_snapshot 登録・face 紐付け（P0 / 掟16）。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from fontdb.paths import PACKAGE_ROOT


def _engine_params_yaml(snapshot_id: str) -> Path:
    """repo の engine/params/{id}.yaml を優先。"""
    repo = PACKAGE_ROOT.parent / "engine" / "params" / f"{snapshot_id}.yaml"
    if repo.is_file():
        return repo
    pkg = (
        PACKAGE_ROOT.parent
        / "engine"
        / "src"
        / "engine"
        / "snapshots"
        / f"{snapshot_id}.yaml"
    )
    if pkg.is_file():
        return pkg
    raise FileNotFoundError(f"params yaml not found for {snapshot_id}")


def load_params_doc(snapshot_id: str) -> dict[str, Any]:
    if "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise ValueError(f"invalid snapshot id: {snapshot_id!r}")
    path = _engine_params_yaml(snapshot_id)
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict) or "params" not in doc:
        raise ValueError(f"invalid params doc: {path}")
    return doc


def params_sha256_from_doc(doc: dict[str, Any]) -> str:
    payload = json.dumps(doc["params"], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_design_param_snapshot(
    conn: sqlite3.Connection,
    snapshot_id: str,
    *,
    status: str = "frozen",
    frozen_at: str | None = None,
) -> dict[str, Any]:
    """YAML 正本を読み design_param_snapshot に UPSERT。

    掟16: 既に frozen の snapshot_id で params_sha256 が変わったら拒否。
    frozen_at は初回確定値を保持（再実行で書き換えない）。
    """
    if status not in ("candidate", "frozen"):
        raise ValueError(f"invalid status: {status!r}")
    doc = load_params_doc(snapshot_id)
    sid = str(doc.get("snapshot_id") or snapshot_id)
    if sid != snapshot_id:
        raise ValueError(
            f"snapshot_id mismatch: arg={snapshot_id!r} yaml={sid!r}"
        )
    digest = params_sha256_from_doc(doc)

    existing = conn.execute(
        """SELECT status, params_sha256, frozen_at
           FROM design_param_snapshot WHERE snapshot_id=?""",
        (snapshot_id,),
    ).fetchone()

    yaml_status = str(doc.get("status", "")).lower()
    if status == "frozen" and yaml_status and yaml_status != "frozen":
        raise ValueError(
            f"YAML status for {snapshot_id!r} is {yaml_status!r}, "
            "refusing to write DB status=frozen（正本 YAML を先に frozen に）"
        )

    if existing and existing[0] == "frozen" and status == "candidate":
        raise ValueError(
            f"snapshot {snapshot_id!r} is frozen; cannot downgrade to candidate（掟16）"
        )

    if existing and existing[0] == "frozen" and existing[1] != digest:
        raise ValueError(
            f"snapshot {snapshot_id!r} is frozen; params_sha256 changed "
            f"({existing[1][:12]}… → {digest[:12]}…). "
            "Cut a new snapshot_id (e.g. product_r2) per 掟16."
        )

    if status == "candidate":
        when: str | None = None
    elif existing and existing[0] == "frozen" and existing[2]:
        when = existing[2]
    elif frozen_at:
        when = frozen_at
    elif doc.get("frozen_at"):
        when = str(doc["frozen_at"])
    else:
        when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    notes = doc.get("notes")
    if isinstance(notes, str):
        notes = notes.strip()

    conn.execute(
        """INSERT INTO design_param_snapshot
           (snapshot_id, status, params_json, params_sha256, source, profile,
            extractor_version, anchors_json, notes, frozen_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(snapshot_id) DO UPDATE SET
             status=excluded.status,
             params_json=excluded.params_json,
             params_sha256=excluded.params_sha256,
             source=excluded.source,
             profile=excluded.profile,
             extractor_version=excluded.extractor_version,
             anchors_json=excluded.anchors_json,
             notes=excluded.notes,
             frozen_at=excluded.frozen_at
        """,
        (
            snapshot_id,
            status,
            json.dumps(doc["params"], ensure_ascii=False, sort_keys=True),
            digest,
            doc.get("source"),
            doc.get("profile"),
            str(doc.get("extractor_version"))
            if doc.get("extractor_version")
            else None,
            json.dumps(doc.get("anchors") or {}, ensure_ascii=False),
            notes,
            when,
        ),
    )
    return {
        "snapshot_id": snapshot_id,
        "status": status,
        "params_sha256": digest,
        "frozen_at": when,
        "reused_frozen_at": bool(
            existing and existing[0] == "frozen" and existing[2] == when
        ),
    }


def link_face_to_snapshot(
    conn: sqlite3.Connection,
    face_id: str,
    snapshot_id: str,
) -> None:
    """face ↔ design_param_snapshot（掟16）。"""
    conn.execute(
        """INSERT INTO face_param_link (face_id, snapshot_id)
           VALUES (?,?)
           ON CONFLICT(face_id, snapshot_id) DO NOTHING""",
        (face_id, snapshot_id),
    )


def assert_engine_params_match_yaml(snapshot_id: str = "product_r1") -> str:
    """engine.PARAM_SETS と YAML params のハッシュ一致を強制。"""
    import sys

    engine_src = PACKAGE_ROOT.parent / "engine" / "src"
    if engine_src.is_dir() and str(engine_src) not in sys.path:
        sys.path.insert(0, str(engine_src))
    from dataclasses import asdict

    from engine.params import PARAM_SETS

    if snapshot_id not in PARAM_SETS:
        raise KeyError(f"PARAM_SETS missing {snapshot_id!r}")
    doc = load_params_doc(snapshot_id)
    sha_yaml = params_sha256_from_doc(doc)
    eng = asdict(PARAM_SETS[snapshot_id])
    sha_eng = hashlib.sha256(
        json.dumps(eng, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if sha_yaml != sha_eng:
        raise ValueError(
            f"params drift {snapshot_id}: yaml={sha_yaml[:12]}… "
            f"engine={sha_eng[:12]}…（二重正本のズレ）"
        )
    return sha_yaml


def freeze_product_r1(
    conn: sqlite3.Connection,
    *,
    link_face_ids: list[str] | None = None,
    check_engine: bool = True,
) -> dict[str, Any]:
    """P0: product_r1 を frozen 登録し、指定 face に紐付ける。"""
    if check_engine:
        assert_engine_params_match_yaml("product_r1")
    meta = upsert_design_param_snapshot(conn, "product_r1", status="frozen")
    linked: list[str] = []
    for fid in link_face_ids or []:
        row = conn.execute(
            "SELECT 1 FROM face WHERE face_id=?", (fid,)
        ).fetchone()
        if row:
            link_face_to_snapshot(conn, fid, "product_r1")
            linked.append(fid)
    meta["linked_faces"] = linked
    return meta
