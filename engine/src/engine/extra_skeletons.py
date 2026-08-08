"""回帰用の追加骨格（木・本・日・田・口）。SVG Y下 legacy（掟1 / T7 で移行）。"""

from __future__ import annotations

from engine.geometry import Vec2
from engine.skeletons import CHAR_LABELS as PROTO_LABELS
from engine.skeletons import CHARACTERS as PROTO_CHARS
from engine.strokes import EndTag, SkeletonStroke, StrokeKind


def char_ki() -> list[SkeletonStroke]:
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


def char_hon() -> list[SkeletonStroke]:
    """本: 木 + 下部の短い横画。

    長くうろこ付きの横ははらいと干渉して中サイズ島が残る。
    400–600・右端うろこ無しなら classic/modern/product_r1 で単一輪郭になる。
    """
    strokes = char_ki()
    strokes.append(
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(400, 720), Vec2(600, 720)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.NONE,
            thickness=40.0,
        )
    )
    return strokes


def char_nichi() -> list[SkeletonStroke]:
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


def char_ta() -> list[SkeletonStroke]:
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


def char_kuchi() -> list[SkeletonStroke]:
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


EXTRA_CHARACTERS: dict[str, list[SkeletonStroke]] = {
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


def all_characters() -> dict[str, list[SkeletonStroke]]:
    merged = dict(PROTO_CHARS)
    merged.update(EXTRA_CHARACTERS)
    return merged


def all_labels() -> dict[str, str]:
    merged = dict(PROTO_LABELS)
    merged.update(EXTRA_LABELS)
    return merged
