# -*- coding: utf-8 -*-
"""Generate only the T4 OG cards (zh + en) without re-rendering all 250."""
import content
import content_en
import make_og_articles as og

slug = "cxdmo-global-vs-china-2026"
a = next(x for x in content.ARTICLES if x["id"] == slug)
zh = og.make_card(a, "zh")
en = og.make_card(a, "en")
print("Generated:")
print(" ", zh)
print(" ", en)
