"""回帰用の追加骨格（join20 用）。SVG Y下 legacy（掟1 / T7 で移行）。"""

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


def char_ichi() -> list[SkeletonStroke]:
    """一: 横画1本。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(180, 500), Vec2(820, 500)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
    ]


def char_san() -> list[SkeletonStroke]:
    """三: 非接触の横画3本。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(240, 280), Vec2(760, 280)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=42.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(220, 500), Vec2(780, 500)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(180, 720), Vec2(820, 720)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=48.0,
        ),
    ]


def char_jin() -> list[SkeletonStroke]:
    """人: 左はらい + 右はらい。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.LEFT_HARA,
            points=[
                Vec2(520, 200),
                Vec2(420, 380),
                Vec2(300, 580),
                Vec2(180, 820),
            ],
        ),
        SkeletonStroke(
            kind=StrokeKind.RIGHT_HARA,
            points=[
                Vec2(520, 200),
                Vec2(600, 380),
                Vec2(720, 580),
                Vec2(860, 820),
            ],
        ),
    ]


def char_dai() -> list[SkeletonStroke]:
    """大: 横 + 左はらい + 右はらい。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(220, 380), Vec2(780, 380)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.LEFT_HARA,
            points=[
                Vec2(500, 250),
                Vec2(400, 420),
                Vec2(280, 620),
                Vec2(160, 840),
            ],
        ),
        SkeletonStroke(
            kind=StrokeKind.RIGHT_HARA,
            points=[
                Vec2(500, 250),
                Vec2(600, 420),
                Vec2(720, 620),
                Vec2(860, 840),
            ],
        ),
    ]


def char_do() -> list[SkeletonStroke]:
    """土: 上横 + 縦 + 下横。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(280, 340), Vec2(720, 340)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=42.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 220), Vec2(500, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(180, 780), Vec2(820, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.NONE,
            thickness=48.0,
        ),
    ]


def char_ou() -> list[SkeletonStroke]:
    """王: 上横 + 中横 + 下横 + 縦。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(240, 260), Vec2(760, 260)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=42.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(260, 500), Vec2(740, 500)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.NONE,
            thickness=40.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(200, 780), Vec2(800, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.NONE,
            thickness=48.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 260), Vec2(500, 780)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.TOME,
        ),
    ]


def char_yama() -> list[SkeletonStroke]:
    """山: 左縦 + 中縦（高） + 右縦 + 上横（接続）。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(260, 360), Vec2(260, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 200), Vec2(500, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(740, 360), Vec2(740, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(260, 360), Vec2(740, 360)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.NONE,
            thickness=42.0,
        ),
    ]


def char_kawa() -> list[SkeletonStroke]:
    """川: 非接触の縦画3本。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(300, 220), Vec2(300, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 260), Vec2(500, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
            thickness=90.0,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(700, 220), Vec2(700, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
    ]


def char_kou() -> list[SkeletonStroke]:
    """工: 上横 + 縦 + 下横。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(220, 280), Vec2(780, 280)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 280), Vec2(500, 780)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(220, 780), Vec2(780, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.NONE,
        ),
    ]


def char_ue() -> list[SkeletonStroke]:
    """上: 縦 + 下横 + 短い右横。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(420, 200), Vec2(420, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(200, 780), Vec2(800, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.NONE,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(420, 420), Vec2(720, 420)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.UROKO,
            thickness=40.0,
        ),
    ]


def char_shita() -> list[SkeletonStroke]:
    """下: 上横 + 縦 + 右向き短い横。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(200, 260), Vec2(800, 260)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 260), Vec2(500, 820)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.TOME,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(500, 520), Vec2(760, 520)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.UROKO,
            thickness=40.0,
        ),
    ]


def char_naka() -> list[SkeletonStroke]:
    """中: 口 + 中央縦（外1+穴2 → 3）。"""
    strokes = char_kuchi()
    strokes.append(
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 260), Vec2(500, 780)],
            start_tag=EndTag.NONE,
            end_tag=EndTag.TOME,
        )
    )
    return strokes


EXTRA_CHARACTERS: dict[str, list[SkeletonStroke]] = {
    "ki": char_ki(),
    "hon": char_hon(),
    "nichi": char_nichi(),
    "ta": char_ta(),
    "kuchi": char_kuchi(),
    "ichi": char_ichi(),
    "san": char_san(),
    "jin": char_jin(),
    "dai": char_dai(),
    "do": char_do(),
    "ou": char_ou(),
    "yama": char_yama(),
    "kawa": char_kawa(),
    "kou": char_kou(),
    "ue": char_ue(),
    "shita": char_shita(),
    "naka": char_naka(),
}

EXTRA_LABELS = {
    "ki": "木",
    "hon": "本",
    "nichi": "日",
    "ta": "田",
    "kuchi": "口",
    "ichi": "一",
    "san": "三",
    "jin": "人",
    "dai": "大",
    "do": "土",
    "ou": "王",
    "yama": "山",
    "kawa": "川",
    "kou": "工",
    "ue": "上",
    "shita": "下",
    "naka": "中",
}


def all_characters() -> dict[str, list[SkeletonStroke]]:
    """回帰用骨格。呼び出しごとにコピーを返し共有破壊を防ぐ。"""
    import copy

    merged = {k: copy.deepcopy(v) for k, v in PROTO_CHARS.items()}
    merged.update({k: copy.deepcopy(v) for k, v in EXTRA_CHARACTERS.items()})
    return merged


def all_labels() -> dict[str, str]:
    merged = dict(PROTO_LABELS)
    merged.update(EXTRA_LABELS)
    return merged
