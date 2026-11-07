# -*- coding: utf-8 -*-
"""Insert the 2026-11 round articles into content.py (list) and content_en.py (dict)
using bracket-depth scanning so each entry lands just before the container's
closing bracket regardless of nested braces inside existing entries.
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))

IDS = [
    "wuxi-apptec-investor-day-2026",
    "pharmaron-q3-2026",
    "lonza-merck-us-cdmo-2026",
]


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
    open_idx = base + len(marker) - 1
    open_ch = src[open_idx]
    close_ch = ']' if open_ch == '[' else '}'
    close = find_close(src, open_idx, open_ch, close_ch)
    pre = src[:close].rstrip()
    if pre.endswith(','):
        pre = pre[:-1]
    return pre + ',\n' + inner + '\n' + src[close:]


def main():
    cpath = os.path.join(BASE, "content.py")
    epath = os.path.join(BASE, "content_en.py")
    csrc = open(cpath, encoding="utf-8").read()
    esrc = open(epath, encoding="utf-8").read()

    for id_ in IDS:
        zh = open(os.path.join(BASE, id_ + "_zh_inner.txt"), encoding="utf-8").read().rstrip("\n")
        en = open(os.path.join(BASE, id_ + "_en_inner.txt"), encoding="utf-8").read().rstrip("\n")
        if id_ in csrc:
            print("ZH %s already present; skip" % id_)
        else:
            csrc = insert_at_end(csrc, "ARTICLES = [", zh)
            print("ZH %s inserted" % id_)
        if '"%s"' % id_ in esrc:
            print("EN %s already present; skip" % id_)
        else:
            esrc = insert_at_end(esrc, "ARTICLES_EN = {", en)
            print("EN %s inserted" % id_)

    open(cpath, "w", encoding="utf-8").write(csrc)
    open(epath, "w", encoding="utf-8").write(esrc)
    print("done")


if __name__ == "__main__":
    main()
