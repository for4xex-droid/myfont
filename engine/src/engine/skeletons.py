"""字形骨格データ（座標＋ストローク種別＋端点タグ）。

UPM=1000。現行は SVG Y下（legacy）。UFO 前に to_font_y（GOLDENRULES 掟1 / T7）。
"""

from __future__ import annotations

from engine.geometry import Vec2
from engine.strokes import EndTag, SkeletonStroke, StrokeKind


def char_ni() -> list[SkeletonStroke]:
    """二: 横画2本。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(220, 340), Vec2(780, 340)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(180, 700), Vec2(820, 700)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=48.0,
        ),
    ]


def char_juu() -> list[SkeletonStroke]:
    """十: 横画＋縦画（止め）。"""
    return [
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(200, 480), Vec2(800, 480)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(500, 200), Vec2(500, 820)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.TOME,
        ),
    ]


def char_ei() -> list[SkeletonStroke]:
    """
    永（永字八法の試験字形）:
      1. 側 = 点
      2. 勒 = 横画
      3. 努 = 縦画
      4. 趯 = はね（縦画下端）
      5. 策 = 短い右上がり横画（挑）
      6. 掠 = 長い左はらい
      7. 啄 = 短い左はらい
      8. 磔 = 右はらい
    """
    return [
        # 1. 側（点）— 上部中央やや右
        SkeletonStroke(
            kind=StrokeKind.TEN,
            points=[Vec2(520, 165), Vec2(595, 245)],
        ),
        # 2. 勒（横画）
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(260, 300), Vec2(760, 300)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
        ),
        # 3+4. 努＋趯（縦画＋はね）
        SkeletonStroke(
            kind=StrokeKind.VERTICAL,
            points=[Vec2(470, 300), Vec2(470, 780)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.HANE,
        ),
        # 5. 策（短い挑 = 右上がりの短い横）
        SkeletonStroke(
            kind=StrokeKind.HORIZONTAL,
            points=[Vec2(470, 455), Vec2(640, 430)],
            start_tag=EndTag.UCHIKOMI,
            end_tag=EndTag.UROKO,
            thickness=40.0,
        ),
        # 6. 掠（長い左はらい）
        SkeletonStroke(
            kind=StrokeKind.LEFT_HARA,
            points=[
                Vec2(455, 310),
                Vec2(360, 480),
                Vec2(250, 650),
                Vec2(140, 820),
            ],
        ),
        # 7. 啄（短い左はらい）— 点の左下あたりから
        SkeletonStroke(
            kind=StrokeKind.LEFT_HARA,
            points=[
                Vec2(500, 210),
                Vec2(455, 250),
                Vec2(400, 290),
                Vec2(340, 330),
            ],
            thickness=70.0,
        ),
        # 8. 磔（右はらい）
        SkeletonStroke(
            kind=StrokeKind.RIGHT_HARA,
            points=[
                Vec2(480, 520),
                Vec2(560, 600),
                Vec2(700, 720),
                Vec2(860, 820),
            ],
        ),
    ]


CHARACTERS: dict[str, list[SkeletonStroke]] = {
    "ni": char_ni(),
    "juu": char_juu(),
    "ei": char_ei(),
}

# 表示用グリフ名
CHAR_LABELS = {
    "ni": "二",
    "juu": "十",
    "ei": "永",
}
