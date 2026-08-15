# MenuTitle: あガイド画像を載せる
# -*- coding: utf-8 -*-
"""uni3042 に参照ラスタを背景画像として載せる。輪郭は触らない。"""

from GlyphsApp import GSBackgroundImage, Glyphs
from Foundation import NSPoint

PATH = "/Users/motista/Desktop/antigravity/myfont/proofs/review/a/glyphs_bg/a_guide_ipaex.png"

font = Glyphs.font
if font is None:
    raise RuntimeError("フォントが開かれていない")
glyph = font.glyphs["uni3042"]
if glyph is None:
    raise RuntimeError("uni3042 が無い")
layer = glyph.layers[0]
img = GSBackgroundImage(PATH)
img.position = NSPoint(0, -120)
layer.backgroundImage = img
Glyphs.defaults["showBackgroundImage"] = True
print("attached", PATH)
