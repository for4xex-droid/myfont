#!/usr/bin/env python3
"""T7: prototype bridge（一時フォント化経路）。MVP ではプレースホルダ。"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "TODO T7: union→一時OTF化→freetype計測で classic/modern を face 登録"
        "（spike3 の経路を bridge/ に昇格）",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
