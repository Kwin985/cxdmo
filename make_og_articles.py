# -*- coding: utf-8 -*-
"""为每篇文章生成 OG 社交分享卡（1200x630 PNG）：assets/img/<id>.png / <id>-en.png。
沿用 make_og.py 的品牌视觉，叠加文章标题、公司·分类胶囊、日期。
中文卡：msyh 字体；英文卡：segoe/segoe bold；标题过长时自适应缩小字号。

用法: python make_og_articles.py
依赖: Pillow (venv)
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import content
import content_en

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
ASSET_DIR = os.path.join(BASE, "assets", "img")
os.makedirs(ASSET_DIR, exist_ok=True)

C_NAVY = (10, 92, 140)
C_TEAL = (13, 138, 110)
C_INK = (14, 36, 51)
C_WHITE = (255, 255, 255)
C_MUTED = (174, 188, 203)

FONT_REG = "C:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT_ZH = "C:/Windows/Fonts/msyh.ttc"
if not os.path.exists(FONT_BOLD):
    FONT_BOLD = FONT_REG

CO_EN = {
    "药明康德": "WuXi AppTec",
    "药明生物": "WuXi Biologics",
    "药明合联": "WuXi XDC",
    "康龙化成": "Pharmaron",
    "凯莱英": "Asymchem",
    "博腾股份": "Porton Pharma",
    "博腾生物": "Porton Bio",
    "博腾股份 / 博腾生物": "Porton",
    "三星生物": "Samsung Biologics",
    "Lonza": "Lonza",
    "Lonza 龙沙": "Lonza",
    "东曜药业 / BioDlink": "BioDlink (TOT Biopharm)",
    "英矽智能": "Insilico Medicine",
    "行业观察": "Industry Insight",
    "新药动态": "New Drugs",
}
CAT_EN = {
    "财报": "Results", "公告": "Announcement", "产能": "Capacity",
    "并购": "M&A", "里程碑": "Milestone", "行业观察": "Insight",
}


def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_bg(img):
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = (x / W + y / H) / 2
            px[x, y] = lerp(C_NAVY, C_TEAL, t)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(440):
        od.rectangle([0, H - 440 + i, 540, H], fill=(0, 0, 0, 72 - i // 8))
    img.alpha_composite(overlay)


def draw_motif(img):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = 985, 195
    for r in (55, 115, 185, 265, 355):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 26), width=2)
    import random
    random.seed(7)
    pts = [(random.randint(660, 1175), random.randint(50, 350)) for _ in range(14)]
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            if abs(p[0] - q[0]) + abs(p[1] - q[1]) < 220:
                d.line([p, q], fill=(255, 255, 255, 30), width=1)
    for p in pts:
        d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=(255, 255, 255, 70))
    img.alpha_composite(layer)


def wrap_chars(d, text, fnt, max_w):
    """按字符宽度折行（中文）。"""
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if d.textlength(test, font=fnt) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def wrap_words(d, text, fnt, max_w):
    """按英文单词折行，必要时在 '/' 处断行。"""
    parts = re.split(r'(/)', text.strip())
    parts = [p for p in parts if p]
    lines, cur = [], ""
    for p in parts:
        if p == " ":
            continue
        if p == "/":
            test = cur + "/" if cur else ""
            if cur and d.textlength(test, font=fnt) <= max_w:
                cur += "/"
            continue
        test = (cur + " " + p) if cur else p
        if d.textlength(test, font=fnt) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = p
    if cur:
        lines.append(cur)
    return lines


def fit_title(d, title, lang):
    """返回适配后的 (font, lines)。"""
    sizes = [54, 50, 46, 42, 38] if lang == "en" else [54, 50, 46]
    for size in sizes:
        f = font(FONT_BOLD if lang == "en" else FONT_ZH, size, index=1 if lang != "en" else 0)
        if lang == "en":
            lines = wrap_words(d, title, f, 1010)
        else:
            lines = wrap_chars(d, title, f, 1010)
        if len(lines) <= 3:
            return f, lines
    # 兜底：截断到 3 行
    f = font(FONT_BOLD if lang == "en" else FONT_ZH, sizes[-1], index=1 if lang != "en" else 0)
    lines = (wrap_words if lang == "en" else wrap_chars)(d, title, f, 1010)[:3]
    return f, lines


def make_card(a, lang="zh"):
    slug = a["id"]
    date = a.get("date", "")

    if lang == "en":
        en = content_en.ARTICLES_EN.get(slug, {})
        title = en.get("title", a.get("title", ""))
        company = CO_EN.get(a.get("company", ""), a.get("company", ""))
        category = CAT_EN.get(a.get("category", ""), a.get("category", ""))
        kicker = " · ".join(x for x in (company, category) if x)
        footer = "cxdmo.com — Global CXDMO Industry News Portal"
        suffix = "-en"
        f_kick = font(FONT_REG, 26)
        f_date = font(FONT_REG, 24)
        f_foot = font(FONT_REG, 22)
    else:
        title = a.get("title", "")
        company = a.get("company", "")
        category = a.get("category", "")
        kicker = " · ".join(x for x in (company, category) if x)
        footer = "cxdmo.com — 全球 CXDMO 产业资讯门户"
        suffix = ""
        f_kick = font(FONT_ZH, 26)
        f_date = font(FONT_ZH, 24)
        f_foot = font(FONT_ZH, 22)

    img = Image.new("RGBA", (W, H), C_NAVY).convert("RGBA")
    gradient_bg(img)
    draw_motif(img)
    d = ImageDraw.Draw(img)

    bx, by = 80, 84
    box = 64
    d.rounded_rectangle([bx, by, bx + box, by + box], radius=16, fill=(255, 255, 255, 245))
    d.text((bx, by), "CX", font=font(FONT_BOLD, 36), fill=C_INK)
    d.text((bx + box + 16, by + 14), "CXDMO INDUSTRY NEWS",
           font=font(FONT_REG, 22), fill=(255, 255, 255, 235))

    # 公司·分类 白底深色胶囊
    ky = 188
    if kicker:
        kw = d.textlength(kicker, font=f_kick)
        d.rounded_rectangle([bx, ky, bx + kw + 36, ky + 46], radius=23,
                            fill=(255, 255, 255, 245), outline=(255, 255, 255, 180))
        d.text((bx + 18, ky + 9), kicker, font=f_kick, fill=C_INK)

    # 主标题（自适应字号，最多 3 行）
    f_title, lines = fit_title(d, title, lang)
    ty = 270
    lh = 66 if f_title.size >= 46 else 58
    for ln in lines:
        d.text((bx, ty), ln, font=f_title, fill=C_WHITE)
        ty += lh

    if date:
        d.text((bx, H - 96), date, font=f_date, fill=(210, 226, 238, 255))
    d.line([bx, H - 64, W - 80, H - 64], fill=(255, 255, 255, 40), width=1)
    d.text((bx, H - 52), footer, font=f_foot, fill=C_MUTED)

    out = os.path.join(ASSET_DIR, f"{slug}{suffix}.png")
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def main():
    n_zh = n_en = 0
    for a in content.ARTICLES:
        make_card(a, "zh")
        n_zh += 1
        if a["id"] in content_en.ARTICLES_EN:
            make_card(a, "en")
            n_en += 1
    print(f"Generated {n_zh} Chinese and {n_en} English OG cards in {ASSET_DIR}")


if __name__ == "__main__":
    main()
