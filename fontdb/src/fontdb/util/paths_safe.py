"""パス安全性（corpus 改ざん時の traversal 防止）。"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_under(root: Path, rel: str) -> Path:
    """root 配下の相対パスのみ許可。

    最終要素のシンボリックリンク先が root 外でも、
    *リンクパス自体* が root 内なら許可する（data/fonts → 外部実体の運用を許容）。
    `..` や絶対パスによる脱出は拒否する。
    """
    root = root.resolve()
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"path escapes package root: {rel!r}")
    candidate = root / rel_path
    # symlink を辿らず正規化して所属を判定
    normalized = Path(os.path.normpath(candidate))
    try:
        normalized.relative_to(root)
    except ValueError as e:
        raise ValueError(f"path escapes package root: {rel!r}") from e
    return candidate
