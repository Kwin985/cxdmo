# -*- coding: utf-8 -*-
"""生成 cxmdo.com 的 OG 社交分享图（1200x630 PNG）。确定性绘制，文字清晰无失真。
用法: python make_og.py   输出: assets/og-image.png
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "og-image.png")

# 品牌色：海军蓝 → 青绿 渐变
C_NAVY = (10, 92, 140)      # #0a5c8c
C_TEAL = (13, 138, 110)     # #0d8a6e
C_INK = (14, 36, 51)        # #0e2433 (深底)
C_WHITE = (255, 255, 255)
C_MUTED = (174, 188, 203)   # #aebccb
C_FAINT = (255, 255, 255, 22)

FONT_REG = "C:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT_ZH = "C:/Windows/Fonts/msyh.ttc"
if not os.path.exists(FONT_BOLD):
    FONT_BOLD = FONT_REG


def font(path, size):
    return ImageFont.truetype(path, size)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_bg(img):
    """对角线渐变 navy -> teal，再叠一层左下深色压暗以提升文字对比。"""
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = (x / W + y / H) / 2  # 对角
            px[x, y] = lerp(C_NAVY, C_TEAL, t)
    # 左下加暗罩，保证左侧文字区对比度
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(420):
        od.rectangle([0, H - 420 + i, 470, H], fill=(0, 0, 0, 70 - i // 8))
    img.alpha_composite(overlay)


def draw_motif(img):
    """右侧装饰：同心圆 + 网络节点，低透明度白色。"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = 980, 200
    for r in (60, 120, 190, 270, 360):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 26), width=2)
    # 节点 + 连线
    import random
    random.seed(7)
    pts = [(random.randint(640, 1170), random.randint(60, 360)) for _ in range(14)]
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            if abs(p[0] - q[0]) + abs(p[1] - q[1]) < 220:
                d.line([p, q], fill=(255, 255, 255, 30), width=1)
    for p in pts:
        d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=(255, 255, 255, 70))
    img.alpha_composite(layer)


def main():
    base = Image.new("RGBA", (W, H), C_NAVY)
    bg = base.convert("RGBA")
    gradient_bg(bg)
    bg = bg.convert("RGBA")
    draw_motif(bg)

    d = ImageDraw.Draw(bg)

    # Logo 方块 + CX
    box = 74
    bx, by = 80, 88
    d.rounded_rectangle([bx, by, bx + box, by + box], radius=18, fill=(255, 255, 255, 245))
    f_cx = font(FONT_BOLD, 40)
    d.text((bx, by), "CX", font=f_cx, fill=C_INK)

    # 副标识
    f_kicker = font(FONT_REG, 26)
    d.text((bx + box + 18, by + 6), "CXDMO INDUSTRY NEWS", font=f_kicker, fill=(255, 255, 255, 235))

    # 主标题
    f_word = font(FONT_BOLD, 118)
    d.text((bx, by + box + 50), "CXDMO", font=f_word, fill=C_WHITE)
    # .com
    f_com = font(FONT_REG, 64)
    cw = d.textlength("CXDMO", font=f_word)
    d.text((bx + cw + 10, by + box + 50 + 30), ".com", font=f_com, fill=(200, 226, 238, 255))

    # Tagline（英文，默认语言）
    f_tag = font(FONT_BOLD, 40)
    d.text((bx, by + box + 50 + 150), "Tracking the Global CXDMO Pulse", font=f_tag, fill=C_WHITE)

    f_sub = font(FONT_REG, 24)
    d.text((bx, by + box + 50 + 150 + 50),
           "WuXi AppTec · WuXi Biologics · WuXi XDC · Pharmaron · Asymchem · Porton · Samsung Biologics · Lonza",
           font=f_sub, fill=(190, 210, 222, 255))

    # 底部条
    d.line([bx, H - 70, W - 80, H - 70], fill=(255, 255, 255, 40), width=1)
    f_foot = font(FONT_REG, 22)
    d.text((bx, H - 56), "cxmdo.com — the CXDMO industry news portal", font=f_foot, fill=C_MUTED)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bg.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT}  ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()
