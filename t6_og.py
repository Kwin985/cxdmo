# -*- coding: utf-8 -*-
"""Generate only the T6 OG cards (zh + en) without re-rendering all 256."""
import content
import content_en
import make_og_articles as og

slug = "cxdmo-modality-landscape-2026"
a = next(x for x in content.ARTICLES if x["id"] == slug)
zh = og.make_card(a, "zh")
en = og.make_card(a, "en")
print("Generated:")
print(" ", zh)
print(" ", en)
