"""仮名パラメトリック生成（P1-B）。"""

from engine.kana.load import (
    KANA_GLYPH_META,
    kana_characters,
    kana_labels,
    load_kana_skeleton,
    skeletons_dir,
)

__all__ = [
    "KANA_GLYPH_META",
    "kana_characters",
    "kana_labels",
    "load_kana_skeleton",
    "skeletons_dir",
]
