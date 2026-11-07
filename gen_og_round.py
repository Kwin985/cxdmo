# -*- coding: utf-8 -*-
"""Generate OG social cards for the 2026-11 round articles only (fast path).
Reuses make_og_articles.make_card so output matches the full-run branding.
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import content
import content_en
import make_og_articles

IDS = [
    "wuxi-apptec-investor-day-2026",
    "pharmaron-q3-2026",
    "lonza-merck-us-cdmo-2026",
]


def main():
    for id_ in IDS:
        a = next(x for x in content.ARTICLES if x["id"] == id_)
        make_og_articles.make_card(a, "zh")
        if id_ in content_en.ARTICLES_EN:
            make_og_articles.make_card(a, "en")
        print("OG done:", id_)


if __name__ == "__main__":
    main()
