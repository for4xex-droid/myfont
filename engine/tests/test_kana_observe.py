"""Phase 0b: 観測メトリクス（合否非接続）。"""

from __future__ import annotations

from engine.kana.gate import run_gate
from engine.kana.observe import observe_glyph, spine_curvature_stats
from engine.kana.load import kana_characters


def test_observe_does_not_change_gate_ok():
    before = run_gate("shi", "product_r1")
    obs = observe_glyph("shi", "product_r1")
    after = run_gate("shi", "product_r1")
    assert before.ok == after.ok
    assert obs.get("observation_only") is True
    assert "curvature_p95" in (obs.get("curvature") or {})
    assert (obs.get("outline") or {}).get("points_after", 0) > 0


def test_observe_all_registered_kana():
    chars = kana_characters()
    assert chars, "expected registered kana"
    for gid in chars:
        obs = observe_glyph(gid, "product_r1")
        assert obs.get("error") is None, gid
        curv = obs["curvature"]
        outline = obs["outline"]
        assert curv.get("n_curvature_samples", 0) > 0, gid
        assert outline.get("points_after", 0) >= 3, gid
        assert outline.get("anchor_count") == outline.get("points_after")


def test_spine_curvature_stats_on_loaded_strokes():
    strokes = kana_characters()["ku"]
    stats = spine_curvature_stats(list(strokes))
    assert stats["curvature_p95"] is not None
    assert stats["curvature_p95"] > 0
    assert stats["min_radius_upm"] is not None
