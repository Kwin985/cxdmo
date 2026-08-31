# -*- coding: utf-8 -*-
"""CXDMO 资讯站构建脚本（中英双语）
用法: python build.py
输出: 英文版（根路径，默认）+ 中文版（/zh/）
  index.html / news.html / companies.html / about.html
  articles/<id>.html | zh/index.html / zh/news.html / ... / zh/articles/<id>.html
  边缘语言分流见 worker.js（仅根路径 / 按 Cookie cxdmo_lang 或 Accept-Language 分流；.html 页面直出 200 并中和 Cloudflare Clean URLs 的 .html->无扩展名 307，避免 GSC 重定向错误）
  assets/style.css / sitemap.xml / robots.txt
"""
import os
import json
import re
import shutil
import difflib
from content import ARTICLES, COMPANIES
from content_en import ARTICLES_EN, COMPANIES_EN

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_NAME = "CXDMO"
DOMAIN = "https://cxdmo.com"

# Google Analytics 4（GA）跟踪挂钩：填入 GA4 媒体资源的 Measurement ID（形如 G-XXXXXXX）后，
# 全站自动加载 gtag.js；留空则不加载任何跟踪代码。
GA_MEASUREMENT_ID = "G-G6E4LDGGKG"

# 站长联系邮箱：用于文章内容（如转载/版权）侵权等问题的沟通渠道，全站页脚展示。
CONTACT_EMAIL = "mdvrinsider@gmail.com"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

COMPANY_COLORS = {
    "药明康德": "#0a6ea8", "药明生物": "#0d8a6e", "药明合联": "#7a4fbf",
    "康龙化成": "#c2571a", "凯莱英": "#b02a37",
    "博腾股份": "#1f6f8b", "博腾生物": "#1f6f8b", "博腾股份 / 博腾生物": "#1f6f8b",
    "三星生物": "#1746a2",
    "Lonza": "#8a6d1f", "Lonza 龙沙": "#8a6d1f",
    "东曜药业 / BioDlink": "#3a7d44",
    "英矽智能": "#6a3aa0", "Insilico Medicine": "#6a3aa0",
    "行业观察": "#5b6b7a",
}

# 文章 company（中文）→ 英文显示名
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
}
GROUP_EN = {"药明系": "WuXi Group", "国内 CXDMO": "Domestic", "海外前沿": "Global", "行业观察": "Insight"}
CAT_EN = {
    "财报": "Results", "公告": "Announcement", "产能": "Capacity", "并购": "M&A",
    "里程碑": "Milestone", "行业观察": "Insight",
}

articles = sorted(ARTICLES, key=lambda a: a["date"], reverse=True)


def _norm_title(t):
    """去除空白与常见标点、统一小写（拉丁字母），用于标题近似比对。"""
    t = (t or "").strip().lower()
    t = re.sub(r'[\s\u3000，。、：:；;！!？?“”"\'‘’（）()【】\[\]《》<>—\-·•·.。/]+', "", t)
    return t


def validate_articles():
    """新增文章时的去重防护。

    检测的重复类型：
      1) 重复 id                       —— 硬错误（构建中止）
      2) 重复来源 URL                  —— 硬错误（同一条微信/官网原文被两次收录 = 几乎确定重复）
      3) 重复标题（中/英，精确）        —— 警告（标题完全相同 = 高概率重复）
      4) 同公司 + 同日 + 标题相似 >=60% —— 警告（捕捉「同一事件换不同来源」型重复，如 BCM3 微信稿 vs 雪球转载）
    仅警告不中止，便于人工确认；硬错误直接 SystemExit(1)，避免误部署。
    """
    errors, warnings = [], []
    seen_id, seen_url, seen_title_zh, seen_title_en = {}, {}, {}, {}

    for a in articles:
        aid = a["id"]
        # 1) 重复 id
        if aid in seen_id:
            errors.append(f"重复 id: '{aid}'（与 '{seen_id[aid]}' 冲突）")
        else:
            seen_id[aid] = aid
        # 2) 重复来源 URL
        url = (a.get("source_url") or "").strip()
        if url:
            if url in seen_url:
                errors.append(f"重复来源 URL: {url}（'{aid}' 与 '{seen_url[url]}' 疑似同一原文）")
            else:
                seen_url[url] = aid
        # 3) 重复标题（中文精确）
        tzh = _norm_title(a["title"])
        if tzh in seen_title_zh:
            warnings.append(f"重复标题(中): 「{a['title']}」—— '{aid}' 与 '{seen_title_zh[tzh]}' 标题完全相同")
        else:
            seen_title_zh[tzh] = aid
        # 3) 重复标题（英文精确）
        en = ARTICLES_EN.get(aid, {})
        ten = _norm_title(en.get("title", "")) if en else ""
        if ten:
            if ten in seen_title_en:
                warnings.append(f"重复标题(英): 「{en.get('title')}」—— '{aid}' 与 '{seen_title_en[ten]}' 标题完全相同")
            else:
                seen_title_en[ten] = aid

    # 4) 同公司 + 同日 + 标题相似（捕捉换来源的同类事件重复）
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            a, b = articles[i], articles[j]
            if a["company"] == b["company"] and a["date"] == b["date"]:
                ra = difflib.SequenceMatcher(None, _norm_title(a["title"]),
                                             _norm_title(b["title"])).ratio()
                rb = difflib.SequenceMatcher(None,
                                             _norm_title(ARTICLES_EN.get(a["id"], {}).get("title", "")),
                                             _norm_title(ARTICLES_EN.get(b["id"], {}).get("title", ""))).ratio()
                if ra >= 0.6 or rb >= 0.6:
                    warnings.append(
                        f"疑似同一事件: '{a['id']}' 与 '{b['id']}'（同公司 {a['company']} 同日 {a['date']}，"
                        f"标题相似度 {max(ra, rb):.0%}）—— 请确认是否为重复文章")

    if errors:
        print("✖ 去重校验失败（构建中止，未生成文件）：")
        for e in errors:
            print("   - " + e)
        raise SystemExit(1)
    if warnings:
        print("⚠ 去重校验警告（请确认是否为重复文章；构建继续）：")
        for w in warnings:
            print("   - " + w)
    else:
        print("✓ 去重校验通过：无重复 id / 来源 URL / 标题。")





def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_body(body):
    """渲染文章正文：字符串 -> <p>；dict 图块 -> <figure><img><figcaption>。

    支持的 dict 块：
      {"img": url, "caption": "..."}            —— 图片块
      {"video": {"cover": url, "url": url,      —— 视频块（微信原生视频无法外站直播，
                  "caption": "..."}}                故以封面+播放按钮引导跳转原文观看）
    """
    out = []
    for item in body:
        if isinstance(item, dict) and item.get("img"):
            cap = item.get("caption") or ""
            cap_html = f'<figcaption>{esc(cap)}</figcaption>' if cap else ""
            out.append(
                f'<figure class="art-img"><img src="{esc(item["img"])}" '
                f'alt="{esc(cap)}" loading="lazy" decoding="async">{cap_html}</figure>'
            )
        elif isinstance(item, dict) and item.get("video"):
            v = item["video"]
            cover = esc(v.get("cover", ""))
            url = esc(v.get("url", ""))
            cap = v.get("caption") or ""
            cap_html = (
                f'<figcaption>{esc(cap)} '
                f'<a href="{url}" target="_blank" rel="noopener">'
                f'{("观看视频（微信原生）" if "微信" not in cap else "观看视频")} ↗</a></figcaption>'
                if cap else
                f'<figcaption><a href="{url}" target="_blank" rel="noopener">'
                f'观看视频（微信原生）↗</a></figcaption>'
            )
            out.append(
                f'<figure class="art-video">'
                f'<a class="video-link" href="{url}" target="_blank" rel="noopener" '
                f'aria-label="{esc(cap)}">'
                f'<img src="{cover}" alt="{esc(cap)}" loading="lazy" decoding="async">'
                f'<span class="play-btn" aria-hidden="true">▶</span>'
                f'</a>{cap_html}</figure>'
            )
        else:
            out.append(f"<p>{esc(item)}</p>")
    return out


def date_cn(d):
    if len(d) == 7:
        return f"{d[:4]} 年 {int(d[5:7])} 月"
    return f"{d[:4]} 年 {int(d[5:7])} 月 {int(d[8:10])} 日"


def date_en(d):
    if len(d) == 7:
        return f"{MONTHS[int(d[5:7]) - 1]} {d[:4]}"
    return f"{MONTHS[int(d[5:7]) - 1]} {int(d[8:10])}, {d[:4]}"


def date_of(d, lang):
    return date_en(d) if lang == "en" else date_cn(d)


def date_iso(d):
    return d if len(d) == 10 else d + "-01"


# ---- 按语言取字段 ----
def a_title(a, lang):
    return ARTICLES_EN[a["id"]]["title"] if lang == "en" else a["title"]


def a_summary(a, lang):
    return ARTICLES_EN[a["id"]]["summary"] if lang == "en" else a["summary"]


def a_body(a, lang):
    return ARTICLES_EN[a["id"]]["body"] if lang == "en" else a["body"]


def a_company(a, lang):
    return CO_EN.get(a["company"], a["company"]) if lang == "en" else a["company"]


def a_cat(a, lang):
    return CAT_EN.get(a["category"], a["category"]) if lang == "en" else a["category"]


def a_source(a, lang):
    if lang == "en":
        return ARTICLES_EN.get(a["id"], {}).get("source", a["source"])
    return a["source"]


def a_source_url(a, lang):
    if lang == "en":
        return ARTICLES_EN.get(a["id"], {}).get("source_url", a["source_url"])
    return a["source_url"]


def g_of(company):
    for c in COMPANIES:
        if company in c["name"] or c["name"] in company:
            return c["group"]
    return "行业观察"


def g_of_lang(company, lang):
    g = g_of(company)
    return GROUP_EN.get(g, g) if lang == "en" else g


def co_matches(company, co_name):
    return company in co_name or co_name in company


# ---- 语言上下文 ----
T = {
    "zh": {
        "nav": [("index.html", "首页", "Home"), ("news.html", "资讯", "News"),
                ("companies.html", "企业", "Companies"), ("about.html", "关于", "About")],
        "hero_kicker": "CXDMO INDUSTRY NEWS · 行业资讯门户",
        "hero_h1": "追踪全球 CXDMO 产业脉动",
        "hero_sub": '聚焦药明康德、药明生物、药明合联、康龙化成、凯莱英、博腾等中国 CXDMO 龙头，<br class="br">以及三星生物、Lonza 等全球前沿 CDMO 的财报、产能、并购与合作动态。',
        "stats": [("10", "追踪企业"), ("{n}", "收录资讯"), ("3", "板块 · 药明系 / 国内 / 海外")],
        "top": "头条要闻", "top_en": "Top Story", "latest": "最新资讯", "latest_en": "Latest",
        "insight": "行业观察", "insight_en": "Insight", "all_news": "全部资讯 →",
        "news_h1": "全部资讯", "news_h1_en": "News",
        "news_sub": "共收录 {n} 篇行业资讯，按企业板块与分类筛选浏览。",
        "seg": "板块", "catlabel": "分类", "search": "搜索",
        "search_ph": "输入关键词，如：ADC、多肽、产能…",
        "empty": "没有匹配的资讯。",
        "groups": ["全部", "药明系", "国内 CXDMO", "海外前沿", "行业观察"],
        "cat_all": "全部",
        "co_h1": "企业名录", "co_h1_en": "Companies",
        "co_sub": "追踪 8 家全球代表性 CXDMO 企业：药明系三驾马车、国内 CXDMO 三强、海外前沿双巨头。",
        "co_news": "资讯 {n} 篇 →", "related": "相关资讯", "related_en": "Related",
        "ticker": "股票代码", "hq": "总部", "visit": "访问官网 ↗",
        "about_h1": "关于本站", "about_h1_en": "About",
        "about_sub": "cxdmo.com — CXDMO 行业资讯门户。",
        "read": "阅读全文 →", "source": "来源：", "home": "首页", "news_crumb": "资讯",
        "art_note": "本文基于公开报道整理，原始来源：{s} · 仅供行业资讯参考，不构成投资建议。",
        "footer_about": "CXDMO（Contract X Development & Manufacturing Organization）资讯门户，追踪药明系、康龙化成、凯莱英、博腾与全球 CXDMO 前沿动态。",
        "footer_cols": "栏目", "footer_decl": "内容声明",
        "footer_decl_text": f"本站内容基于公开报道与企业公告整理，仅供行业资讯参考，不构成任何投资建议。如内容涉及版权问题，请联系 {CONTACT_EMAIL}。",
        "footer_contact": "侵权联系",
        "footer_links": "友情链接",
        "site_title": "CXDMO 资讯 — 追踪全球 CXDMO 产业脉动",
        "site_desc": "CXDMO 行业资讯门户：聚焦药明康德、药明生物、药明合联、康龙化成、凯莱英、博腾等中国 CXDMO 企业，以及三星生物、Lonza 等全球 CXDMO 前沿动态。",
        "news_title": "全部资讯 — CXDMO",
        "news_desc": "CXDMO 行业资讯列表：按企业与分类筛选浏览药明系、国内 CXDMO 与海外前沿动态。",
        "co_title": "企业名录 — CXDMO",
        "co_desc": "药明康德、药明生物、药明合联、康龙化成、凯莱英、博腾、三星生物、Lonza 企业档案与最新动态。",
        "about_title": "关于本站 — CXDMO",
        "about_desc": "CXDMO 资讯门户：站点定位、覆盖范围与内容来源说明。",
    },
    "en": {
        "nav": [("index.html", "Home", ""), ("news.html", "News", ""),
                ("companies.html", "Companies", ""), ("about.html", "About", "")],
        "hero_kicker": "CXDMO INDUSTRY NEWS",
        "hero_h1": "Tracking the Global CXDMO Pulse",
        "hero_sub": 'Covering WuXi AppTec, WuXi Biologics, WuXi XDC, Pharmaron, Asymchem and Porton — China\u2019s CXDMO leaders —<br class="br">plus Samsung Biologics, Lonza and the global CDMO frontier: results, capacity, M&A and partnerships.',
        "stats": [("8", "Companies Tracked"), ("{n}", "Stories"), ("3", "Segments · WuXi / Domestic / Global")],
        "top": "Top Story", "top_en": "", "latest": "Latest", "latest_en": "",
        "insight": "Insight", "insight_en": "", "all_news": "All News →",
        "news_h1": "All News", "news_h1_en": "",
        "news_sub": "{n} industry stories, filterable by segment, category and keyword.",
        "seg": "Segment", "catlabel": "Category", "search": "Search",
        "search_ph": "Keywords, e.g. ADC, peptide, capacity…",
        "empty": "No matching stories.",
        "groups": ["All", "WuXi Group", "Domestic", "Global", "Insight"],
        "cat_all": "All",
        "co_h1": "Companies", "co_h1_en": "",
        "co_sub": "Tracking 8 representative global CXDMOs: the WuXi trio, China\u2019s domestic leaders, and the global frontier giants.",
        "co_news": "{n} stories →", "related": "Related", "related_en": "",
        "ticker": "Ticker", "hq": "HQ", "visit": "Official Website ↗",
        "about_h1": "About", "about_h1_en": "",
        "about_sub": "cxdmo.com — the CXDMO industry news portal.",
        "read": "Read More →", "source": "Source: ",
        "home": "Home", "news_crumb": "News",
        "art_note": "This article is compiled from public reporting. Original source: {s} · For industry reference only; not investment advice.",
        "footer_about": "CXDMO (Contract X Development & Manufacturing Organization) news portal — tracking the WuXi group, Pharmaron, Asymchem, Porton and the global CXDMO frontier.",
        "footer_cols": "Sections", "footer_decl": "Disclaimer",
        "footer_decl_text": f"Content on this site is compiled from public reports and company announcements, for industry reference only, and does not constitute investment advice. For copyright concerns, contact {CONTACT_EMAIL}.",
        "footer_contact": "Contact",
        "footer_links": "Friendly Links",
        "site_title": "CXDMO News — Tracking the Global CXDMO Pulse",
        "site_desc": "The CXDMO industry news portal: WuXi AppTec, WuXi Biologics, WuXi XDC, Pharmaron, Asymchem, Porton, plus Samsung Biologics, Lonza and the global CDMO frontier.",
        "news_title": "All News — CXDMO",
        "news_desc": "All CXDMO industry stories, filterable by company segment and category.",
        "co_title": "Companies — CXDMO",
        "co_desc": "Profiles and latest updates for WuXi AppTec, WuXi Biologics, WuXi XDC, Pharmaron, Asymchem, Porton, Samsung Biologics and Lonza.",
        "about_title": "About — CXDMO",
        "about_desc": "CXDMO news portal: positioning, coverage and content sources.",
    },
}

ABOUT_EN = '''
<section class="page-head">
  <div class="wrap">
    <h1>About <span></span></h1>
    <p>cxdmo.com — the CXDMO industry news portal.</p>
  </div>
</section>
<main class="wrap">
  <div class="prose">
    <h2>What is a CXDMO?</h2>
    <p>CXDMO is an umbrella term for CRDMOs (Contract Research, Development and Manufacturing Organizations) and related pharmaceutical outsourcing business models. It spans the full value chain — from drug discovery and process development through preclinical and clinical research to commercial manufacturing — and is the hub connecting biotech, pharma and capacity in the innovation ecosystem.</p>
    <p>With the new-molecule wave in ADC/XDC, the boom in peptides and oligonucleotides (TIDES), and the geographic restructuring of global capacity, the CXDMO industry is being reshaped: Chinese leaders compete on cost, speed and integration, while Western giants respond with M&A and refocusing.</p>
    <h2>What We Cover</h2>
    <p>CXDMO (cxdmo.com) is an independent industry news portal tracking:</p>
    <ul>
      <li><b>The WuXi Group</b>: WuXi AppTec (small-molecule CRDMO), WuXi Biologics (large-molecule CRDMO), WuXi XDC (ADC/XDC CRDMO)</li>
      <li><b>Domestic CXDMOs</b>: Pharmaron, Asymchem, Porton Pharma / Porton Bio</li>
      <li><b>Global Frontier</b>: Samsung Biologics, Lonza</li>
    </ul>
    <p>Coverage spans financial results, capacity expansion, M&amp;A and integration, strategic partnerships, regulatory qualifications and industry trend analysis.</p>
    <h2>Sources &amp; Updates</h2>
    <p>Content is compiled from company press releases, listed-company announcements and reporting by mainstream financial and industry media, with the original source cited on every story. Content from closed channels such as WeChat official accounts is captured via equivalent public press releases and authoritative republications.</p>
    <p>The site is static by architecture, generated by a local build script, and suited to static hosting platforms such as Cloudflare Pages.</p>
    <h2>Disclaimer</h2>
    <p>All content is for industry reference only and does not constitute investment advice. Data and facts are subject to official company disclosures. For copyright concerns, please reach out via the site pages.</p>
  </div>
</main>'''


def lang_path(lang, p):
    """根路径绝对 URL。默认英文在根，中文在 /zh/（从任意子目录页面引用均正确）"""
    return f"/{p}" if lang == "en" else f"/zh/{p}"


def canonical_path(lang, p):
    if p == "index.html":
        return f"{DOMAIN}/" if lang == "en" else f"{DOMAIN}/zh/"
    return f"{DOMAIN}{lang_path(lang, p)}"


def hreflang_tags(lang, p):
    en = f"{DOMAIN}/" if p == "index.html" else f"{DOMAIN}/{p}"
    zh = f"{DOMAIN}/zh/" if p == "index.html" else f"{DOMAIN}/zh/{p}"
    return (f'<link rel="alternate" hreflang="zh-CN" href="{zh}">\n'
            f'<link rel="alternate" hreflang="en" href="{en}">\n'
            f'<link rel="alternate" hreflang="x-default" href="{en}">')


# 语言切换：点击写入 cxdmo_lang Cookie 记忆用户选择（普通字符串，非 f-string，避免 {} 被解析）
LANG_SWITCH_SCRIPT = '''<script>
document.querySelectorAll('.lang-switch').forEach(function(el){
  el.addEventListener('click', function(){
    document.cookie = 'cxdmo_lang=' + el.dataset.lang + '; path=/; max-age=31536000; samesite=lax';
  });
});
</script>'''


# ---------------- JSON-LD 结构化数据 ----------------
OG_IMG = f"{DOMAIN}/assets/og-image.png"


def _jsonld(data):
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False, separators=(",", ":"))}</script>'


def org_website_jsonld(lang):
    """全站 Organization + WebSite JSON-LD：搜索引擎品牌识别与 Bing 知识图谱。"""
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{DOMAIN}/#organization",
                "name": "CXDMO",
                "url": f"{DOMAIN}/",
                "logo": {"@type": "ImageObject", "url": OG_IMG},
                "description": T[lang]["footer_about"],
            },
            {
                "@type": "WebSite",
                "@id": f"{DOMAIN}/#website",
                "name": "CXDMO",
                "url": f"{DOMAIN}/",
                "inLanguage": "en" if lang == "en" else "zh-CN",
                "publisher": {"@id": f"{DOMAIN}/#organization"},
            },
        ],
    }
    return _jsonld(data)


def article_jsonld(lang, a):
    """文章页 NewsArticle + BreadcrumbList JSON-LD。"""
    url = f"{DOMAIN}{lang_path(lang, 'articles/' + a['id'] + '.html')}"
    in_lang = "en" if lang == "en" else "zh-CN"
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "NewsArticle",
                "@id": url + "#article",
                "headline": a_title(a, lang),
                "description": a_summary(a, lang),
                "datePublished": date_iso(a["date"]),
                "dateModified": date_iso(a["date"]),
                "inLanguage": in_lang,
                "mainEntityOfPage": {"@type": "WebPage", "@id": url},
                "image": [OG_IMG],
                "author": {"@type": "Organization", "name": "CXDMO Editorial"},
                "publisher": {"@type": "Organization", "name": "CXDMO",
                              "logo": {"@type": "ImageObject", "url": OG_IMG}},
                "articleSection": a_cat(a, lang),
                "keywords": f"{a_company(a, lang)}, {a_cat(a, lang)}, CXDMO",
                "isAccessibleForFree": True,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": T[lang]["home"],
                     "item": f"{DOMAIN}{lang_path(lang, 'index.html')}"},
                    {"@type": "ListItem", "position": 2, "name": T[lang]["news_crumb"],
                     "item": f"{DOMAIN}{lang_path(lang, 'news.html')}"},
                    {"@type": "ListItem", "position": 3, "name": a_company(a, lang),
                     "item": f"{DOMAIN}{lang_path(lang, 'news.html')}?company={esc(a_company(a, lang))}"},
                ],
            },
        ],
    }
    return _jsonld(data)


def companies_jsonld(lang):
    """企业名录页 ItemList JSON-LD（8 家追踪企业）。"""
    items = []
    for i, c in enumerate(COMPANIES, 1):
        name = c["name_en"] if lang == "en" else c["name"]
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": name,
            "url": f"{DOMAIN}{lang_path(lang, 'news.html')}?company={esc(name)}",
        })
    data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": T[lang]["co_h1"],
        "numberOfItems": len(items),
        "itemListElement": items,
    }
    return _jsonld(data)


# Google Analytics 4（GA）跟踪代码挂钩；GA_MEASUREMENT_ID 留空时不加载
GA_SNIPPET = '''<script async src="https://www.googletagmanager.com/gtag/js?id=__MID__"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","__MID__");</script>'''

def ga_head():
    """返回 GA4 gtag 跟踪代码；未配置 Measurement ID 时返回空字符串（不加载）。"""
    if not GA_MEASUREMENT_ID or GA_MEASUREMENT_ID.startswith("G-XXXX"):
        return ""
    return GA_SNIPPET.replace("__MID__", esc(GA_MEASUREMENT_ID))


def page(lang, title, desc, active, content, p="index.html", extra_head=""):
    t = T[lang]
    nav = "".join(
        f'<a href="{lang_path(lang, h)}"{" class=\"active\"" if h == active else ""}>{label}{f"<span>{en}</span>" if en else ""}</a>'
        for h, label, en in t["nav"])
    alt = "zh" if lang == "en" else "en"
    alt_label = "中文" if lang == "en" else "EN"
    og_type = "article" if p.startswith("articles/") else "website"
    og_locale = "en_US" if lang == "en" else "zh_CN"
    return f'''<!DOCTYPE html>
<html lang="{'en' if lang == 'en' else 'zh-CN'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0a5c8c">
<meta name="author" content="CXDMO Editorial">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical_path(lang, p)}">
{hreflang_tags(lang, p)}
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:url" content="{canonical_path(lang, p)}">
<meta property="og:locale" content="{og_locale}">
<meta property="og:image" content="{OG_IMG}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="CXDMO — Tracking the Global CXDMO Pulse">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{OG_IMG}">
<meta name="twitter:image:alt" content="CXDMO — Tracking the Global CXDMO Pulse">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/style.css">
{ga_head()}
{org_website_jsonld(lang)}
{extra_head}
</head>
<body>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="logo" href="{lang_path(lang, 'index.html')}"><span class="logo-mark">CX</span><span class="logo-text">CXDMO<em>.com</em></span></a>
    <div class="nav-right">
      <a class="lang-switch" href="{lang_path(alt, p)}" data-lang="{alt}">{alt_label}</a>
      <nav class="main-nav">{nav}</nav>
    </div>
  </div>
</header>
{content}
<footer class="site-footer">
  <div class="wrap footer-inner">
    <div class="footer-brand">
      <div class="logo footer-logo"><span class="logo-mark">CX</span><span class="logo-text light">CXDMO</span></div>
      <p>{t["footer_about"]}</p>
    </div>
    <div class="footer-col">
      <h4>{t["footer_cols"]}</h4>
      <a href="{lang_path(lang, 'news.html')}">{t["nav"][1][1]}</a>
      <a href="{lang_path(lang, 'companies.html')}">{t["nav"][2][1]}</a>
      <a href="{lang_path(lang, 'about.html')}">{t["nav"][3][1]}</a>
    </div>
    <div class="footer-col">
      <h4>{t["footer_decl"]}</h4>
      <p class="small">{t["footer_decl_text"]}</p>
    </div>
  </div>
  {friendly_links(lang)}
  <div class="wrap footer-bottom"><span>© 2026 cxdmo.com · CXDMO Insight</span><span class="sep">·</span><span>{t["footer_contact"]}: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></span></div>
</footer>
{LANG_SWITCH_SCRIPT}
</body>
</html>'''


def friendly_links(lang):
    """页脚“友情链接”区：链接到各追踪企业的官方站点（复用 COMPANIES 的 site 字段）。"""
    t = T[lang]
    items = "".join(
        f'<a href="{esc(c["site"])}" target="_blank" rel="noopener noreferrer">'
        f'{esc(c["name_en"] if lang == "en" else c["name"])}</a>'
        for c in COMPANIES)
    return (f'<div class="wrap footer-links">'
            f'<span class="fl-label">{esc(t["footer_links"])}</span>'
            f'<nav class="fl-nav">{items}</nav>'
            f'</div>')


def tag(lang, company):
    color = COMPANY_COLORS.get(company, "#5b6b7a")
    label = a_company({"company": company}, lang)
    return (f'<a class="tag" href="{lang_path(lang, "news.html")}?company={esc(label)}" '
            f'style="--tag-color:{color}">{esc(label)}</a>')


def card(lang, a, featured=False):
    t = T[lang]
    cls = "card featured" if featured else "card"
    inner = f'''
        <div class="card-top">{tag(lang, a["company"])}<span class="cat">{esc(a_cat(a, lang))}</span></div>
        <h3 class="card-title"><a href="{lang_path(lang, f'articles/{a["id"]}.html')}">{esc(a_title(a, lang))}</a></h3>
        <p class="card-sum">{esc(a_summary(a, lang))}</p>
        <div class="card-meta"><time>{date_of(a["date"], lang)}</time><span class="more">{t["read"]}</span></div>'''
    return f'<article class="{cls}">{inner}</article>'


# ---------------- 首页 ----------------
def build_index(lang):
    t = T[lang]
    head = articles[0]
    rest = articles[1:7]
    co_chips = "".join(
        f'<a class="chip" href="{lang_path(lang, "news.html")}?company={esc(a_company({"company": c["name"]}, lang))}"'
        f' style="--tag-color:{COMPANY_COLORS.get(c["name"], "#0a5c8c")}">{esc(c["name_en"] if lang == "en" else c["name"])}</a>'
        for c in COMPANIES)
    industry = [a for a in articles if a["company"] == "行业观察"][:2]
    stats = "".join(f'<div class="stat"><b>{v.replace("{n}", str(len(articles)))}</b><span>{k}</span></div>'
                    for v, k in t["stats"])
    content = f'''
<section class="hero">
  <div class="wrap">
    <p class="hero-kicker">{t["hero_kicker"]}</p>
    <h1>{t["hero_h1"]}</h1>
    <p class="hero-sub">{t["hero_sub"]}</p>
    <div class="hero-stats">{stats}</div>
    <div class="hero-chips">{co_chips}</div>
  </div>
</section>
<main class="wrap">
  <section class="section">
    <div class="section-head"><h2>{t["top"]}{f' <span>{t["top_en"]}</span>' if t["top_en"] else ''}</h2><a class="see-all" href="{lang_path(lang, "news.html")}">{t["all_news"]}</a></div>
    <div class="card-grid single">{card(lang, head, featured=True)}</div>
  </section>
  <section class="section">
    <div class="section-head"><h2>{t["latest"]}{f' <span>{t["latest_en"]}</span>' if t["latest_en"] else ''}</h2></div>
    <div class="card-grid">{"".join(card(lang, a) for a in rest)}</div>
  </section>
  <section class="section">
    <div class="section-head"><h2>{t["insight"]}{f' <span>{t["insight_en"]}</span>' if t["insight_en"] else ''}</h2></div>
    <div class="card-grid two">{"".join(card(lang, a) for a in industry)}</div>
  </section>
</main>'''
    return page(lang, t["site_title"], t["site_desc"], "index.html", content)


# ---------------- 资讯列表页 ----------------
def build_news(lang):
    t = T[lang]
    # 公司→板块映射（当前语言）
    if lang == "en":
        co_group_map = {}
        for a in articles:
            co_group_map[CO_EN.get(a["company"], a["company"])] = GROUP_EN.get(g_of(a["company"]))
        for c in COMPANIES:
            co_group_map[c["name_en"]] = GROUP_EN.get(g_of(c["name"]), "Global")
    else:
        co_group_map = {}
        for c in COMPANIES:
            co_group_map[c["name"]] = c["group"]
        for a in articles:
            co_group_map[a["company"]] = g_of(a["company"])
    map_json = json.dumps(co_group_map, ensure_ascii=False)
    cats = sorted({a["category"] for a in articles})
    co_btns = "".join(f'<button class="chip-btn" data-group="{g}">{g}</button>' for g in t["groups"])
    cat_btns = "".join(
        f'<button class="chip-btn" data-cat="{CAT_EN.get(c, c) if lang == "en" else c}">'
        f'{CAT_EN.get(c, c) if lang == "en" else c}</button>' for c in cats)
    items = "".join(f'''
      <article class="list-item" data-group="{esc(g_of_lang(a["company"], lang))}" data-cat="{esc(a_cat(a, lang))}"
               data-company="{esc(a_company(a, lang))}"
               data-title="{esc(a_title(a, lang))}{esc(a_summary(a, lang))}">
        <div class="card-top">{tag(lang, a["company"])}<span class="cat">{esc(a_cat(a, lang))}</span></div>
        <h3 class="card-title"><a href="{lang_path(lang, f'articles/{a["id"]}.html')}">{esc(a_title(a, lang))}</a></h3>
        <p class="card-sum">{esc(a_summary(a, lang))}</p>
        <div class="card-meta"><time>{date_of(a["date"], lang)}</time></div>
      </article>''' for a in articles)
    content = f'''
<section class="page-head">
  <div class="wrap">
    <h1>{t["news_h1"]}{f' <span>{t["news_h1_en"]}</span>' if t["news_h1_en"] else ''}</h1>
    <p>{t["news_sub"].replace("{n}", str(len(articles)))}</p>
  </div>
</section>
<main class="wrap">
  <div class="filter-bar">
    <div class="filter-row"><span class="filter-label">{t["seg"]}</span>{co_btns}<button class="chip-btn co-clear" id="coFilter" hidden></button></div>
    <div class="filter-row"><span class="filter-label">{t["catlabel"]}</span><button class="chip-btn" data-cat="{t["cat_all"]}">{t["cat_all"]}</button>{cat_btns}</div>
    <div class="filter-row"><span class="filter-label">{t["search"]}</span><input id="q" type="search" placeholder="{t["search_ph"]}"></div>
  </div>
  <div class="news-list" id="newsList">{items}</div>
  <p class="empty" id="empty" hidden>{t["empty"]}</p>
</main>
<script>
(function() {{
  var group = "{t["groups"][0]}", cat = "{t["cat_all"]}", q = "", company = "";
  var map = {map_json};
  var params = new URLSearchParams(location.search);
  var pc = params.get("company");
  var coBtn = document.getElementById("coFilter");
  function groupOf(name) {{
    if (map[name]) return map[name];
    for (var k in map) {{ if (name.indexOf(k) > -1 || k.indexOf(name) > -1) return map[k]; }}
    return null;
  }}
  function setCompany(c) {{
    company = c;
    if (c) {{
      coBtn.textContent = "{t["seg"]}: " + c + " ✕";
      coBtn.hidden = false;
      coBtn.classList.add("on");
    }} else {{
      coBtn.hidden = true;
      coBtn.classList.remove("on");
    }}
  }}
  if (pc) {{
    setCompany(pc);
    var g = groupOf(pc);
    if (g) {{
      group = g;
      var btn = document.querySelector('.chip-btn[data-group="' + g + '"]');
      if (btn) btn.classList.add("on");
    }}
  }}
  function apply() {{
    var items = document.querySelectorAll(".list-item");
    var n = 0;
    items.forEach(function(el) {{
      var ok = (group === "{t["groups"][0]}" || el.dataset.group === group) &&
               (cat === "{t["cat_all"]}" || el.dataset.cat === cat) &&
               (!company || el.dataset.company === company ||
                 company.indexOf(el.dataset.company) > -1 || el.dataset.company.indexOf(company) > -1) &&
               (!q || el.dataset.title.indexOf(q) > -1);
      el.style.display = ok ? "" : "none";
      if (ok) n++;
    }});
    document.getElementById("empty").hidden = n > 0;
  }}
  coBtn.addEventListener("click", function() {{
    setCompany("");
    group = "{t["groups"][0]}";
    document.querySelectorAll("[data-group]").forEach(function(x) {{ x.classList.remove("on"); }});
    document.querySelector('[data-group="{t["groups"][0]}"]').classList.add("on");
    apply();
  }});
  document.querySelectorAll(".chip-btn[data-group],.chip-btn[data-cat]").forEach(function(b) {{
    var isGroup = b.dataset.group !== undefined;
    if (!pc || !isGroup) {{
      if (isGroup && b.dataset.group === "{t["groups"][0]}") b.classList.add("on");
      if (!isGroup && b.dataset.cat === "{t["cat_all"]}") b.classList.add("on");
    }}
    b.addEventListener("click", function() {{
      document.querySelectorAll(isGroup ? "[data-group]" : "[data-cat]").forEach(function(x) {{ x.classList.remove("on"); }});
      b.classList.add("on");
      if (isGroup) {{ group = b.dataset.group; setCompany(""); }} else {{ cat = b.dataset.cat; }}
      apply();
    }});
  }});
  document.getElementById("q").addEventListener("input", function(e) {{
    q = e.target.value.trim(); apply();
  }});
  apply();
}})();
</script>'''
    return page(lang, t["news_title"], t["news_desc"], "news.html", content, "news.html")


# ---------------- 企业页 ----------------
def build_companies(lang):
    t = T[lang]
    blocks = []
    for c in COMPANIES:
        color = COMPANY_COLORS.get(c["name"], "#0a5c8c")
        n = len([a for a in articles if co_matches(a["company"], c["name"])])
        ce = COMPANIES_EN.get(c["id"], {})
        name_disp = c["name_en"] if lang == "en" else c["name"]
        name_sub = c["name"] if lang == "en" else c["name_en"]
        tagline = ce.get("tagline", c["tagline"]) if lang == "en" else c["tagline"]
        desc = ce.get("desc", c["desc"]) if lang == "en" else c["desc"]
        group_disp = GROUP_EN.get(g_of(c["name"]), "") if lang == "en" else c["group"]
        related = [a for a in articles if co_matches(a["company"], c["name"])][:3]
        rel_html = ""
        if related:
            lis = "".join(
                f'<li><a href="{lang_path(lang, "articles/" + a["id"] + ".html")}">{esc(a_title(a, lang))}</a>'
                f'<span class="mini-date">{date_of(a["date"], lang)}</span></li>' for a in related)
            rel_html = f'<div class="co-news"><h4>{t["related"]}</h4><ul>{lis}</ul></div>'
        blocks.append(f'''
  <section class="co-card" style="--co:{color}">
    <div class="co-head">
      <div class="co-avatar">{esc(c["name_en"][:2])}</div>
      <div class="co-title">
        <h3>{esc(name_disp)} <span class="co-en">{esc(name_sub)}</span></h3>
        <p class="co-tagline">{esc(tagline)}</p>
      </div>
      <a class="co-link" href="{lang_path(lang, "news.html")}?company={esc(a_company({"company": c["name"]}, lang))}">{t["co_news"].replace("{n}", str(n))}</a>
    </div>
    <div class="co-meta">
      <span>{t["ticker"]} {esc(c["ticker"])}</span><span>{t["hq"]} {esc(c["hq"] if lang == "zh" else _hq_en(c["hq"]))}</span><span>{esc(group_disp)}</span>
    </div>
    <p class="co-desc">{esc(desc)}</p>
    {rel_html}
    <a class="co-site" href="{c["site"]}" target="_blank" rel="noopener">{t["visit"]}</a>
  </section>''')
    content = f'''
<section class="page-head">
  <div class="wrap">
    <h1>{t["co_h1"]}{f' <span>{t["co_h1_en"]}</span>' if t["co_h1_en"] else ''}</h1>
    <p>{t["co_sub"]}</p>
  </div>
</section>
<main class="wrap">
  <div class="co-grid">{''.join(blocks)}</div>
</main>'''
    return page(lang, t["co_title"], t["co_desc"], "companies.html", content, "companies.html", extra_head=companies_jsonld(lang))


HQ_EN = {"上海": "Shanghai", "北京": "Beijing", "天津": "Tianjin", "重庆 / 苏州": "Chongqing / Suzhou",
         "上海 / 无锡": "Shanghai / Wuxi", "韩国仁川": "Incheon, South Korea", "瑞士巴塞尔": "Basel, Switzerland"}


def _hq_en(hq):
    return HQ_EN.get(hq, hq)


# ---------------- 关于页 ----------------
def build_about(lang):
    if lang == "en":
        content = ABOUT_EN
        return page(lang, T["en"]["about_title"], T["en"]["about_desc"], "about.html", content, "about.html")
    content = '''
<section class="page-head">
  <div class="wrap">
    <h1>关于本站 <span>About</span></h1>
    <p>cxdmo.com — CXDMO 行业资讯门户。</p>
  </div>
</section>
<main class="wrap">
  <div class="prose">
    <h2>什么是 CXDMO？</h2>
    <p>CXDMO 是 CRDMO（Contract Research, Development and Manufacturing Organization，合同研究、开发与生产组织）及其他类似医药外包业务形态的统称。它覆盖了从药物发现、工艺开发、临床前与临床研究，到商业化生产的全产业链服务，是创新药生态中连接 Biotech、Pharma 与产能的枢纽环节。</p>
    <p>近年来，随着 ADC/XDC 等新分子浪潮、多肽与寡核苷酸（TIDES）赛道爆发，以及全球产能地理重构，CXDMO 行业正经历深刻变局：中国龙头以"成本+速度+一体化"重塑竞争格局，海外巨头则以并购与归核应对。</p>
    <h2>本站定位</h2>
    <p>CXDMO（cxdmo.com）是一个独立的行业资讯门户，持续追踪以下企业动态：</p>
    <ul>
      <li><b>药明系</b>：药明康德（小分子 CRDMO）、药明生物（大分子 CRDMO）、药明合联（ADC/XDC CRDMO）</li>
      <li><b>国内 CXDMO</b>：康龙化成、凯莱英、博腾股份/博腾生物</li>
      <li><b>海外前沿</b>：三星生物（Samsung Biologics）、Lonza（龙沙）</li>
    </ul>
    <p>内容维度涵盖：财报业绩、产能扩建、并购整合、战略合作、监管资质与行业趋势观察。</p>
    <h2>内容来源与更新说明</h2>
    <p>本站内容基于各公司官网新闻稿、上市公司公告、主流财经与行业媒体的公开报道整理撰写，每篇资讯均标注原始来源。微信公众号等封闭渠道的内容，本站通过其公开发布的等效新闻稿与权威转载渠道收录。</p>
    <p>网站为静态架构，内容通过本地构建脚本生成，适合部署于 Cloudflare Pages 等静态托管平台。</p>
    <h2>免责声明</h2>
    <p>本站内容仅供行业资讯参考，不构成任何投资建议。数据与事实以企业官方披露为准；如内容涉及版权问题，请通过站点页面联系处理。</p>
  </div>
</main>'''
    return page(lang, T["zh"]["about_title"], T["zh"]["about_desc"], "about.html", content, "about.html")


# ---------------- 文章页 ----------------
def build_article(lang, a):
    t = T[lang]
    p = f'articles/{a["id"]}.html'
    related = [x for x in articles if x["id"] != a["id"] and
               (x["company"] == a["company"] or x["category"] == a["category"])][:3]
    rel_html = "".join(f'''
      <article class="card">
        <div class="card-top">{tag(lang, x["company"])}<span class="cat">{esc(a_cat(x, lang))}</span></div>
        <h3 class="card-title"><a href="{lang_path(lang, f"articles/{x['id']}.html")}">{esc(a_title(x, lang))}</a></h3>
        <div class="card-meta"><time>{date_of(x["date"], lang)}</time></div>
      </article>''' for x in related)
    paragraphs = "".join(_render_body(a_body(a, lang)))
    crumb_co = a_company(a, lang)
    content = f'''
<article class="article">
  <div class="wrap">
    <nav class="crumb"><a href="{lang_path(lang, "index.html")}">{t["home"]}</a> / <a href="{lang_path(lang, "news.html")}">{t["news_crumb"]}</a> / <a href="{lang_path(lang, "news.html")}?company={esc(crumb_co)}">{esc(crumb_co)}</a></nav>
    <div class="art-head">
      <div class="card-top">{tag(lang, a["company"])}<span class="cat">{esc(a_cat(a, lang))}</span></div>
      <h1>{esc(a_title(a, lang))}</h1>
      <div class="art-meta">
        <time>{date_of(a["date"], lang)}</time>
        <span>{t["source"]}<a href="{a_source_url(a, lang)}" target="_blank" rel="noopener">{esc(a_source(a, lang))} ↗</a></span>
      </div>
    </div>
    <div class="prose">
      <p class="lead">{esc(a_summary(a, lang))}</p>
      {paragraphs}
    </div>
    <div class="art-src">{t["art_note"].replace("{s}", f'<a href="{a_source_url(a, lang)}" target="_blank" rel="noopener">{esc(a_source(a, lang))}</a>')}</div>
  </div>
</article>
<section class="section related">
  <div class="wrap">
    <div class="section-head"><h2>{t["related"]}{f' <span>{t["related_en"]}</span>' if t["related_en"] else ''}</h2><a class="see-all" href="{lang_path(lang, "news.html")}">{t["all_news"]}</a></div>
    <div class="card-grid three">{rel_html}</div>
  </div>
</section>'''
    head_extras = (
        f'<meta property="article:published_time" content="{date_iso(a["date"])}">\n'
        f'<meta property="article:author" content="CXDMO Editorial">\n'
        f'<meta property="article:section" content="{esc(a_cat(a, lang))}">\n'
        f'<meta property="article:tag" content="{esc(a_company(a, lang))}">\n'
        f'<meta property="article:tag" content="{esc(a_cat(a, lang))}">\n'
        + article_jsonld(lang, a))
    return page(lang, f'{a_title(a, lang)} — {SITE_NAME}', a_summary(a, lang), "news.html", content, p, extra_head=head_extras)


# ---------------- CSS ----------------
STYLE = '''/* CXDMO 资讯站 样式 */
:root{
  --primary:#0a5c8c; --primary-dark:#08496f; --accent:#0d8a6e;
  --ink:#16232e; --muted:#5b6b7a; --faint:#8b98a5;
  --line:#e3e9ef; --bg:#f6f8fa; --card:#fff;
  --radius:12px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif;color:var(--ink);background:var(--bg);line-height:1.75;font-size:16px}
a{color:inherit;text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:0 24px}
img{max-width:100%}

/* header */
.site-header{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:50}
.header-inner{display:flex;align-items:center;justify-content:space-between;height:64px}
.logo{display:flex;align-items:center;gap:10px}
.logo-mark{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:9px;background:linear-gradient(135deg,var(--primary),var(--accent));color:#fff;font-weight:800;font-size:15px;letter-spacing:.5px}
.logo-text{font-size:22px;font-weight:800;color:var(--ink);letter-spacing:.5px}
.logo-text em{font-style:normal;font-weight:500;color:var(--faint);font-size:15px}
.nav-right{display:flex;align-items:center;gap:14px}
.lang-switch{padding:5px 13px;border-radius:999px;border:1px solid var(--line);font-size:13px;font-weight:700;color:var(--primary);transition:.15s}
.lang-switch:hover{border-color:var(--primary);background:var(--primary);color:#fff}
.main-nav{display:flex;gap:6px}
.main-nav a{padding:8px 16px;border-radius:8px;font-weight:600;font-size:15px;color:var(--muted);display:flex;flex-direction:column;line-height:1.2}
.main-nav a span{font-size:11px;font-weight:400;color:var(--faint);letter-spacing:.5px}
.main-nav a:hover{background:var(--bg);color:var(--primary)}
.main-nav a.active{background:var(--primary);color:#fff}
.main-nav a.active span{color:rgba(255,255,255,.75)}

/* hero */
.hero{background:linear-gradient(160deg,#0a5c8c 0%,#08496f 55%,#0d3f5e 100%);color:#fff;padding:72px 0 64px}
.hero-kicker{font-size:13px;letter-spacing:3px;color:#9fd4c4;font-weight:700;margin-bottom:18px}
.hero h1{font-size:42px;font-weight:800;letter-spacing:1px;margin-bottom:18px}
.hero-sub{font-size:17px;color:rgba(255,255,255,.82);max-width:760px;margin-bottom:36px}
.hero-stats{display:flex;gap:48px;margin-bottom:32px;flex-wrap:wrap}
.stat b{display:block;font-size:34px;font-weight:800}
.stat span{font-size:13px;color:rgba(255,255,255,.7)}
.hero-chips{display:flex;flex-wrap:wrap;gap:10px}
.chip{padding:7px 16px;border-radius:999px;border:1px solid rgba(255,255,255,.35);color:#fff;font-size:14px;font-weight:600;transition:.2s}
.chip:hover{background:rgba(255,255,255,.15)}

/* sections */
.section{padding:44px 0 8px}
.section-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:22px}
.section-head h2{font-size:24px;font-weight:800}
.section-head h2 span{font-size:12px;font-weight:600;color:var(--faint);letter-spacing:2px;margin-left:10px;text-transform:uppercase}
.see-all{font-size:14px;font-weight:600;color:var(--primary)}
.see-all:hover{text-decoration:underline}

/* cards */
.card-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.card-grid.two{grid-template-columns:repeat(2,1fr)}
.card-grid.three{grid-template-columns:repeat(3,1fr)}
.card-grid.single{grid-template-columns:1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:24px;display:flex;flex-direction:column;gap:12px;transition:.2s}
.card:hover{box-shadow:0 8px 24px rgba(10,60,95,.09);transform:translateY(-2px)}
.card.featured{flex-direction:row;align-items:flex-start;gap:28px;padding:30px}
.card-top{display:flex;align-items:center;gap:10px}
.tag{font-size:12px;font-weight:700;color:var(--tag-color,#0a5c8c);background:color-mix(in srgb,var(--tag-color,#0a5c8c) 10%,white);padding:3px 10px;border-radius:6px}
.cat{font-size:12px;color:var(--faint);font-weight:600}
.card-title{font-size:18px;line-height:1.5;font-weight:700}
.card.featured .card-title{font-size:24px}
.card-title a:hover{color:var(--primary)}
.card-sum{font-size:14px;color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.card.featured .card-sum{-webkit-line-clamp:4;font-size:15px}
.card-meta{margin-top:auto;display:flex;justify-content:space-between;font-size:13px;color:var(--faint)}
.more{color:var(--primary);font-weight:600;font-size:13px}

/* page head */
.page-head{background:#fff;border-bottom:1px solid var(--line);padding:48px 0 40px}
.page-head h1{font-size:32px;font-weight:800}
.page-head h1 span{font-size:13px;color:var(--faint);letter-spacing:2px;margin-left:12px;font-weight:600;text-transform:uppercase}
.page-head p{color:var(--muted);margin-top:10px}

/* filter bar */
.filter-bar{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:18px 22px;margin:28px 0;display:flex;flex-direction:column;gap:12px}
.filter-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.filter-label{font-size:13px;font-weight:700;color:var(--faint);width:64px;flex-shrink:0}
.chip-btn{padding:6px 14px;border-radius:999px;border:1px solid var(--line);background:#fff;font-size:13px;font-weight:600;color:var(--muted);cursor:pointer;transition:.15s}
.chip-btn:hover{border-color:var(--primary);color:var(--primary)}
.chip-btn.on{background:var(--primary);border-color:var(--primary);color:#fff}
#q{flex:1;min-width:220px;padding:8px 14px;border:1px solid var(--line);border-radius:8px;font-size:14px;outline:none}
#q:focus{border-color:var(--primary)}

/* news list */
.news-list{display:flex;flex-direction:column;gap:16px;padding-bottom:40px}
.list-item{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:22px 26px;display:flex;flex-direction:column;gap:10px;transition:.15s}
.list-item:hover{box-shadow:0 6px 18px rgba(10,60,95,.08)}
.list-item .card-title{font-size:19px}
.list-item .card-sum{-webkit-line-clamp:2}
.empty{color:var(--faint);text-align:center;padding:40px 0}

/* companies */
.co-grid{display:flex;flex-direction:column;gap:22px;padding:32px 0 48px}
.co-card{background:#fff;border:1px solid var(--line);border-left:4px solid var(--co,var(--primary));border-radius:var(--radius);padding:28px 32px}
.co-head{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.co-avatar{width:54px;height:54px;border-radius:12px;background:color-mix(in srgb,var(--co,var(--primary)) 12%,white);color:var(--co,var(--primary));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px;flex-shrink:0}
.co-title h3{font-size:22px;font-weight:800}
.co-en{font-size:14px;color:var(--faint);font-weight:500;margin-left:8px}
.co-tagline{font-size:14px;color:var(--co,var(--primary));font-weight:600;margin-top:2px}
.co-link{margin-left:auto;font-size:14px;font-weight:700;color:var(--primary);white-space:nowrap}
.co-meta{display:flex;gap:22px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:16px 0 10px}
.co-meta span{background:var(--bg);padding:3px 12px;border-radius:6px}
.co-desc{font-size:15px;color:var(--muted);max-width:860px}
.co-news{margin-top:18px;border-top:1px dashed var(--line);padding-top:16px}
.co-news h4{font-size:14px;color:var(--ink);margin-bottom:10px}
.co-news ul{list-style:none;display:flex;flex-direction:column;gap:8px}
.co-news li{display:flex;justify-content:space-between;gap:16px;font-size:14px}
.co-news li a{color:var(--muted)}
.co-news li a:hover{color:var(--primary)}
.mini-date{color:var(--faint);font-size:12px;white-space:nowrap}
.co-site{display:inline-block;margin-top:16px;font-size:13px;font-weight:600;color:var(--primary)}

/* article */
.article{padding:36px 0 12px}
.crumb{font-size:13px;color:var(--faint);margin-bottom:24px}
.crumb a:hover{color:var(--primary)}
.art-head{max-width:820px;margin-bottom:28px}
.art-head h1{font-size:30px;line-height:1.45;font-weight:800;margin:14px 0 18px}
.art-meta{display:flex;gap:24px;font-size:14px;color:var(--faint);flex-wrap:wrap}
.art-meta a{color:var(--primary);font-weight:600}
.prose{max-width:820px}
.prose h2{font-size:22px;margin:34px 0 14px;font-weight:800}
.prose p{margin-bottom:18px;color:#2a3a47;font-size:16.5px}
.prose .lead{font-size:18px;color:var(--ink);font-weight:600;border-left:3px solid var(--primary);padding-left:18px}
.prose ul{margin:0 0 18px 22px;color:#2a3a47}
.prose li{margin-bottom:8px}
.art-src{max-width:820px;margin-top:28px;background:var(--bg);border-radius:10px;padding:14px 18px;font-size:13px;color:var(--muted)}
.art-src a{color:var(--primary);font-weight:600}
.prose figure.art-img{margin:30px 0}
.prose figure.art-img img{width:100%;border-radius:var(--radius);display:block;border:1px solid var(--line);background:#fff}
.prose figure.art-img figcaption{font-size:13px;color:var(--muted);margin-top:10px;text-align:center;line-height:1.5}
.prose figure.art-video{margin:30px 0}
.prose figure.art-video .video-link{display:block;position:relative;overflow:hidden;border-radius:var(--radius);border:1px solid var(--line);background:#000}
.prose figure.art-video img{width:100%;display:block;border-radius:var(--radius);opacity:.92;transition:.2s}
.prose figure.art-video .video-link:hover img{opacity:1}
.prose figure.art-video .play-btn{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:64px;height:64px;border-radius:50%;background:rgba(10,92,140,.9);color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;padding-left:4px;box-shadow:0 6px 20px rgba(0,0,0,.32);transition:.2s}
.prose figure.art-video .video-link:hover .play-btn{background:var(--primary);transform:translate(-50%,-50%) scale(1.06)}
.prose figure.art-video figcaption{font-size:13px;color:var(--muted);margin-top:10px;text-align:center;line-height:1.5}
.prose figure.art-video figcaption a{color:var(--primary);font-weight:600}
.related{padding-bottom:56px}

/* footer */
.site-footer{background:#0e2433;color:#aebccb;margin-top:56px}
.footer-inner{display:grid;grid-template-columns:2fr 1fr 1.4fr;gap:40px;padding:48px 24px 36px}
.footer-logo{margin-bottom:14px}
.footer-logo .logo-text{color:#fff}
.footer-brand p{font-size:14px;color:#8ba0b3}
.footer-col h4{color:#fff;font-size:15px;margin-bottom:14px}
.footer-col a{display:block;font-size:14px;color:#8ba0b3;margin-bottom:8px}
.footer-col a:hover{color:#fff}
.footer-col .small{font-size:13px;color:#71879b}
.footer-links{display:flex;align-items:center;gap:16px;flex-wrap:wrap;border-top:1px solid #1d3a4f;padding:18px 24px}
.fl-label{color:#fff;font-size:14px;font-weight:600;white-space:nowrap}
.fl-nav{display:flex;flex-wrap:wrap;gap:8px 18px}
.fl-nav a{font-size:13px;color:#8ba0b3;text-decoration:none}
.fl-nav a:hover{color:#fff;text-decoration:underline}
.footer-bottom{border-top:0;padding:18px 24px;font-size:13px;color:#71879b}
.footer-bottom .sep{margin:0 10px;color:#3a556b}
.footer-bottom a{color:#9fc3e0;text-decoration:none}
.footer-bottom a:hover{color:#cfe4f5;text-decoration:underline}

@media (max-width:900px){
  .card-grid,.card-grid.two,.card-grid.three{grid-template-columns:1fr 1fr}
  .card.featured{flex-direction:column}
  .hero h1{font-size:32px}
  .footer-inner{grid-template-columns:1fr}
  .br{display:none}
}
@media (max-width:620px){
  .card-grid,.card-grid.two,.card-grid.three{grid-template-columns:1fr}
  .main-nav a span{display:none}
  .main-nav a{padding:8px 10px;font-size:14px}
  .lang-switch{padding:4px 10px;font-size:12px}
  .co-link{margin-left:0}
  .hero{padding:48px 0}
  .hero h1{font-size:28px}
}
'''


def build_404(lang):
    """生成站点风格的 404 页面，供 Cloudflare not_found_handling=404-page 使用。"""
    if lang == "en":
        title = "Page not found · CXDMO"
        desc = "The page you requested could not be found."
        kicker = "ERROR 404"
        h1 = "Page not found"
        sub = "The page you are looking for may have been moved, removed, or never existed. Try one of these instead:"
        chips = [("/", "Home"), ("/news.html", "News"),
                 ("/companies.html", "Companies"), ("/about.html", "About")]
    else:
        title = "页面未找到 · CXDMO"
        desc = "您访问的页面不存在或已被移除。"
        kicker = "错误 404"
        h1 = "页面未找到"
        sub = "您访问的页面可能已被移动、删除，或从未存在。您可以："
        chips = [("/zh/", "首页"), ("/zh/news.html", "资讯"),
                 ("/zh/companies.html", "企业"), ("/zh/about.html", "关于")]
    chip_html = "".join(f'<a class="chip" href="{href}">{label}</a>' for href, label in chips)
    content = f'''<section class="hero">
  <div class="wrap">
    <div class="hero-kicker">{kicker}</div>
    <h1>{h1}</h1>
    <p class="hero-sub">{sub}</p>
    <div class="hero-chips">{chip_html}</div>
  </div>
</section>'''
    return page(lang, title, desc, "", content, p="404.html",
                extra_head='<meta name="robots" content="noindex">')


def build():
    validate_articles()  # 新增文章去重防护：重复 id / 来源 URL 中止，重复标题/同事件近似告警
    os.makedirs(os.path.join(ROOT, "dist", "articles"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "dist", "zh", "articles"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "dist", "assets"), exist_ok=True)

    # 复制源码级静态资源（favicon / og-image 等非生成资源）到 dist/assets，
    # 避免部署后这些引用 404；随后生成的 style.css 会覆盖复制进来的源码版本。
    src_assets = os.path.join(ROOT, "assets")
    if os.path.isdir(src_assets):
        shutil.copytree(src_assets, os.path.join(ROOT, "dist", "assets"), dirs_exist_ok=True)

    files = {}
    for lang in ("zh", "en"):
        pfx = "" if lang == "en" else "zh/"
        files[f"{pfx}index.html"] = build_index(lang)
        files[f"{pfx}news.html"] = build_news(lang)
        files[f"{pfx}companies.html"] = build_companies(lang)
        files[f"{pfx}about.html"] = build_about(lang)
        for a in articles:
            files[f"{pfx}articles/{a['id']}.html"] = build_article(lang, a)
    # 404 页面（供 Cloudflare not_found_handling=404-page 服务缺失路径，避免 500）
    files["404.html"] = build_404("en")
    files["zh/404.html"] = build_404("zh")
    files["assets/style.css"] = STYLE

    # sitemap（双语 + hreflang 交替 + 文章页 lastmod）
    sm = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
          '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n')

    def _alt_pair(pname):
        """给定路径（'' | 'news.html' | 'articles/x.html'），返回 (en_loc, zh_loc)。"""
        if pname.startswith("articles/"):
            base = pname  # articles/x.html
            return (f"{DOMAIN}/{base}", f"{DOMAIN}/zh/{base}")
        en = f"{DOMAIN}/{pname}" if pname else f"{DOMAIN}/"
        zh = f"{DOMAIN}/zh/{pname}" if pname else f"{DOMAIN}/zh/"
        return (en, zh)

    def _url(loc, lastmod, en_loc, zh_loc):
        s = f"  <url>\n    <loc>{loc}</loc>\n"
        if lastmod:
            s += f"    <lastmod>{lastmod}</lastmod>\n"
        s += (f'    <xhtml:link rel="alternate" hreflang="en" href="{en_loc}"/>\n'
              f'    <xhtml:link rel="alternate" hreflang="zh-CN" href="{zh_loc}"/>\n'
              f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en_loc}"/>\n'
              f"  </url>\n")
        return s

    # 静态页：双语各列一次（带全量 hreflang 交替）
    for pname in ("", "news.html", "companies.html", "about.html"):
        en_loc, zh_loc = _alt_pair(pname)
        sm += _url(en_loc, None, en_loc, zh_loc)
        sm += _url(zh_loc, None, en_loc, zh_loc)
    # 文章页：双语各列一次
    for a in articles:
        pname = f"articles/{a['id']}.html"
        en_loc, zh_loc = _alt_pair(pname)
        lm = date_iso(a["date"])
        sm += _url(en_loc, lm, en_loc, zh_loc)
        sm += _url(zh_loc, lm, en_loc, zh_loc)
    sm += "</urlset>\n"
    files["sitemap.xml"] = sm
    files["robots.txt"] = (f"User-agent: *\nAllow: /\n"
                           f"Sitemap: {DOMAIN}/sitemap.xml\n")

    # llms.txt：给 AI / LLM 抓取的可读站点索引（与 mdvr.ai 同思路）
    llms_lines = [
        "# CXDMO",
        "",
        "> CXDMO (Contract X Development & Manufacturing Organization) industry news portal —",
        "> tracking WuXi AppTec, WuXi Biologics, WuXi XDC, Pharmaron, Asymchem, Porton,",
        "> Samsung Biologics and Lonza. Results, capacity, M&A and partnerships.",
        "",
        "## Pages",
        f"- [Home]({DOMAIN}/): hero, top story and latest news ({len(articles)} total stories).",
        f"- [News]({DOMAIN}/news.html): filterable by segment, category and keyword.",
        f"- [Companies]({DOMAIN}/companies.html): profiles for {len(COMPANIES)} tracked CXDMO organizations.",
        f"- [About]({DOMAIN}/about.html): what is a CXDMO, sources and disclaimer.",
        "",
        "## Companies tracked",
    ]
    for c in COMPANIES:
        llms_lines.append(f"- [{c['name_en']} ({c['name']})]({c['site']}): {c['tagline']}")
    llms_lines += [
        "",
        "## Languages",
        "- English is the default (root).",
        "- Chinese is served at /zh/ via Accept-Language edge detection.",
        "",
        "## Content sources",
        "- Public company announcements, financial filings and industry media reports.",
        "- Each article links to its original source.",
        "",
        "## Last updated",
        f"- {max(a['date'] for a in articles)}",
    ]
    files["llms.txt"] = "\n".join(llms_lines) + "\n"

    for path, content in files.items():
        full = os.path.join(ROOT, "dist", path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    print(f"Done. {len(articles)} articles x 2 languages, {len(COMPANIES)} companies, {len(files)} files.")


if __name__ == "__main__":
    build()
