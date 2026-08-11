"""リポジトリ直下の .env を安全に読み込む（追加依存なし）。

方針:
- 読むのは repo root の `.env` / `.env.local` のみ（パス固定）
- 許可キー以外は無視（任意変数の process 注入を防ぐ）
- 既に os.environ にあるキーは上書きしない
- 値をログに出さない（呼び出し側の責任も含む）
"""

from __future__ import annotations

import os
from pathlib import Path

# vision 等で使うキーだけ許可
ALLOWED_KEYS = frozenset({"GEMINI_API_KEY"})


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_dotenv_text(text: str, *, allowed: frozenset[str] = ALLOWED_KEYS) -> dict[str, str]:
    """KEY=VALUE 行をパース。許可キーのみ返す。"""
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in allowed:
            continue
        value = _strip_quotes(value.strip())
        if value:
            out[key] = value
    return out


def load_repo_dotenv(
    root: Path,
    *,
    allowed: frozenset[str] = ALLOWED_KEYS,
    override: bool = False,
) -> list[str]:
    """`.env` と `.env.local` を読み、environ にセット。

    Returns:
        新たにセットしたキー名のリスト（値は返さない）。
    """
    loaded: list[str] = []
    for name in (".env", ".env.local"):
        path = root / name
        if not path.is_file():
            continue
        # シンボリックリンク経由の予期せぬパスは拒否
        try:
            resolved = path.resolve()
            if resolved.parent != root.resolve():
                continue
        except OSError:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for key, value in parse_dotenv_text(text, allowed=allowed).items():
            if not override and key in os.environ and os.environ.get(key, "").strip():
                continue
            os.environ[key] = value
            if key not in loaded:
                loaded.append(key)
    return loaded


def redact_secrets(text: str, *secrets: str) -> str:
    """ログ用に秘密値を伏せる。"""
    out = text
    for secret in secrets:
        if secret and secret in out:
            out = out.replace(secret, "***")
    return out
