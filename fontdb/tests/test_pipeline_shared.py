"""共有計測ヘルパ（掟7 / 重複排除）。"""

from __future__ import annotations

from fontdb.pipeline import ensure_glyphs_for_probes, resolve_probe_protocol


def test_resolve_probe_protocol_from_yaml():
    proto = resolve_probe_protocol()
    assert proto["juu_target"]
    assert proto["san_target"]
    assert proto["san_fallback"]
    assert proto["juu_target"] != proto["san_target"]


def test_ensure_glyphs_for_probes_appends_missing():
    out = ensure_glyphs_for_probes(
        ["永"],
        juu_target="十",
        san_target="三",
        san_fallback="二",
    )
    assert out == ["永", "十", "三", "二"]
