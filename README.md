# CXDMO

CXDMO（CRDMO 及同类合同研发生产外包业务）行业资讯站，域名 **cxdmo.com**。

聚焦企业：药明康德、药明生物、药明合联、康龙化成、凯莱英、博腾，以及海外前沿三星生物（Samsung Biologics）、Lonza（龙沙）。

## 技术架构

纯静态站点，通过 Python 构建脚本从内容数据生成全站 HTML，可直接部署到 Cloudflare Pages。

- `content.py` —— 中文资讯与企业档案数据
- `content_en.py` —— 英文资讯与企业档案数据
- `build.py` —— 一键构建全站（含 sitemap.xml、robots.txt、OG/hreflang meta）
- `assets/style.css` —— 样式

生成产物（无需手动维护，构建自动生成）：

- 根路径：中文版（首页、资讯、企业、关于、文章详情）
- `/en/`：英文版（中英双语，含 hreflang 互指与 SEO meta）
- `articles/`、`en/articles/`：文章详情页

## 本地预览

```bash
python build.py            # 重新生成全站
python -m http.server 8090 # 启动本地预览
# 访问 http://localhost:8090/  （中文）
# 访问 http://localhost:8090/en/ （英文）
```

## 追加内容

在 `content.py` / `content_en.py` 的 `ARTICLES` / `COMPANIES` 列表追加条目，重跑 `python build.py` 即可。

## 部署

Cloudflare Pages：连接本仓库，构建命令 `python build.py`，发布目录为仓库根（所有 HTML 已在根与 `/en/` 下生成）。
也可直接将仓库内容发布为静态站点，无需构建步骤。

---

*本站点内容整理自各公司官网新闻稿、上市公司公告及权威媒体转载，仅供行业研究参考，不构成投资建议。*
