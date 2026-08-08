"""path traversal 防止。"""

from __future__ import annotations

import pytest

from fontdb.paths import PACKAGE_ROOT
from fontdb.util.paths_safe import resolve_under


def test_resolve_under_ok():
    p = resolve_under(PACKAGE_ROOT, "data/fonts/.gitkeep")
    assert p.is_relative_to(PACKAGE_ROOT.resolve())


def test_resolve_under_blocks_escape():
    with pytest.raises(ValueError, match="escapes"):
        resolve_under(PACKAGE_ROOT, "../PLAN.md")
