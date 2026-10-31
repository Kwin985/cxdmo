# -*- coding: utf-8 -*-
"""Insert T4 (cxdmo-global-vs-china-2026) into content.py and content_en.py
using bracket-depth scanning (validated on T2/T3). Adds comma-safe trimming
so a trailing comma on the last existing entry never yields ',,'.
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def find_close(src, open_idx, open_ch, close_ch):
    depth = 0
    j = open_idx
    while j < len(src):
        c = src[j]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("Unbalanced brackets: no matching close found")


def insert_at_end(src, marker, inner):
    base = src.index(marker)
    open_idx = base + len(marker) - 1          # index of the container's opening bracket
    open_ch = src[open_idx]
    close_ch = ']' if open_ch == '[' else '}'
    close = find_close(src, open_idx, open_ch, close_ch)
    pre = src[:close].rstrip()
    pre = pre.rstrip(',')                       # comma-safe: avoid ',,'
    return pre + ',\n' + inner + '\n' + src[close:]


def main():
    zh_inner = open(os.path.join(BASE, "t4_zh_inner.txt"), encoding="utf-8").read().rstrip("\n")
    en_inner = open(os.path.join(BASE, "t4_en_inner.txt"), encoding="utf-8").read().rstrip("\n")

    # ZH: list container
    cpath = os.path.join(BASE, "content.py")
    src = open(cpath, encoding="utf-8").read()
    if "cxdmo-global-vs-china-2026" in src:
        print("ZH entry already present; skipping.")
    else:
        src = insert_at_end(src, "ARTICLES = [", zh_inner)
        open(cpath, "w", encoding="utf-8").write(src)
        print("ZH entry inserted into content.py")

    # EN: dict container
    epath = os.path.join(BASE, "content_en.py")
    esrc = open(epath, encoding="utf-8").read()
    if '"cxdmo-global-vs-china-2026"' in esrc:
        print("EN entry already present; skipping.")
    else:
        esrc = insert_at_end(esrc, "ARTICLES_EN = {", en_inner)
        open(epath, "w", encoding="utf-8").write(esrc)
        print("EN entry inserted into content_en.py")


if __name__ == "__main__":
    main()
