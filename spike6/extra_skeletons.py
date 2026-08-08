"""回帰用の追加骨格（木・本・日・田・口）。prototype 形式。"""

from __future__ import annotations

import os
import sys
from typing import Dict, List

PROTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prototype")
sys.path.insert(0, os.path.abspath(PROTO))

from geometry import Vec2  # noqa: E402
from skeletons import CHARACTERS as PROTO_CHARS  # noqa: E402
from skeletons import CHAR_LABELS as PROTO_LABELS  # noqa: E402
from strokes import EndTag, SkeletonStroke, StrokeKind  # noqa: E402


def char_ki() -> List[SkeletonStroke]:
    """木: 横 + 縦 + 左はらい + 右はらい。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(220, 420), Vec2(780, 420)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 180), Vec2(500, 860)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.LEFT_HARA,
            points=[
                Vec2(490, 430),
                Vec2(400, 560),
                Vec2(280, 700),
                Vec2(160, 820),
            ],
        ),
        SkeletonStroke(
            kind=StrokeKind.RIGHT_HARA,
            points=[
                Vec2(510, 430),
                Vec2(600, 560),
                Vec2(720, 700),
                Vec2(860, 820),
            ],
        ),
    ]


def char_hon() -> List[SkeletonStroke]:
    """本: 木 + 下部の短い横画。"""
    strokes = char_ki()
    strokes.append(
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(300, 720), Vec2(700, 720)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=40.0,
        )
    )
    return strokes


def char_nichi() -> List[SkeletonStroke]:
    """日: 左縦・上横・右縦・中横・下横（囲み）。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(280, 220), Vec2(280, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(280, 220), Vec2(720, 220)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(720, 220), Vec2(720, 820)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(280, 500), Vec2(720, 500)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=40.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(280, 820), Vec2(720, 820)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.UROKO,
        ),
    ]


def char_ta() -> List[SkeletonStroke]:
    """田: 日 + 中央縦。"""
    strokes = char_nichi()
    strokes.append(
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 220), Vec2(500, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        )
    )
    return strokes


def char_kuchi() -> List[SkeletonStroke]:
    """口: 左縦・上横・右縦・下横。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(260, 260), Vec2(260, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(260, 260), Vec2(740, 260)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(740, 260), Vec2(740, 780)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(260, 780), Vec2(740, 780)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.UROKO,
        ),
    ]


EXTRA_CHARACTERS: Dict[str, List[SkeletonStroke]] = {
    "ki": char_ki(),
    "hon": char_hon(),
    "nichi": char_nichi(),
    "ta": char_ta(),
    "kuchi": char_kuchi(),
}

EXTRA_LABELS = {
    "ki": "木",
    "hon": "本",
    "nichi": "日",
    "ta": "田",
    "kuchi": "口",
}


def all_characters() -> Dict[str, List[SkeletonStroke]]:
    merged = dict(PROTO_CHARS)
    merged.update(EXTRA_CHARACTERS)
    return merged


def all_labels() -> Dict[str, str]:
    merged = dict(PROTO_LABELS)
    merged.update(EXTRA_LABELS)
    return merged
