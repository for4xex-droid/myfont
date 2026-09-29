"""生成書体の仕様。未決定の項目でフォントファイルを作らない。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "生成書体の仕様.md"

DECIDED = """
### ファイル形式
OTF

### 収録する字の範囲
- 大文字 A〜Z
- 数字 0〜9
- スラッシュ `/`

小文字は足さない。

### 太さの数
1

### 等幅かどうか
プロポーショナル

### 命名の規則
- ファミリー名: Example
- スタイル名（太さごとの名前）: Regular
- ファイル名の付け方: Example-Regular.otf
"""


def _load():
    path = ROOT / "scripts" / "generated_face_spec.py"
    spec = importlib.util.spec_from_file_location("generated_face_spec", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_live_spec_requires_upper_digits_slash_only():
    mod = _load()
    spec = mod.load_spec(SPEC)
    assert spec.required == tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/")
    assert "a" not in spec.required
    assert "あ" not in spec.required
    assert "," not in spec.required


def test_live_spec_blocks_undecided_handoff_fields():
    mod = _load()
    spec = mod.load_spec(SPEC)
    assert spec.blockers == ("太さの数", "命名の規則")


def test_block_handoff_does_not_create_a_font(tmp_path: Path):
    mod = _load()
    spec = mod.load_spec(SPEC)
    dest = tmp_path / "out.otf"
    try:
        mod.block_handoff(spec, dest)
    except mod.HandoffBlocked as e:
        assert "太さの数" in e.reasons
    else:
        raise AssertionError("expected handoff block")
    assert not dest.exists()


def test_unknown_repertoire_bullet_is_refused():
    mod = _load()
    text = DECIDED.replace("- 数字 0〜9", "- 小文字 a〜z")
    try:
        mod.parse_spec(text)
    except ValueError as e:
        assert "unknown repertoire bullet" in str(e)
        return
    raise AssertionError("expected unknown bullet to fail")


def test_decided_spec_still_rejects_extras_and_writes_nothing(tmp_path: Path):
    mod = _load()
    spec = mod.parse_spec(DECIDED)
    assert spec.blockers == ()
    dest = tmp_path / "Example-Regular.otf"
    got = mod.block_handoff(spec, dest)
    assert got == spec.required
    assert not dest.exists()
    try:
        mod.reject_extras(spec, ["A", "a"])
    except mod.HandoffBlocked as e:
        assert any("a" in reason for reason in e.reasons)
        return
    raise AssertionError("expected extra glyph to fail")


def test_cli_exits_while_spec_is_open():
    mod = _load()
    assert mod.main(["--spec", str(SPEC)]) == 2
