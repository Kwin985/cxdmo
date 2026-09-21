// cxdmo.com 边缘语言分流 + 爬行稳定性
// 默认英文（根路径）；中文位于 /zh/。
// 优先级：Cookie(cxdmo_lang) > 浏览器 Accept-Language > 默认英文。
//
// 关键约束（SEO / Google 索引）：
//  - 仅对“根路径 /”做语言自动分流重定向；显式 /zh 与 /zh/ 一律直出中文首页
//    （/zh 以 301 归一到 /zh/），不受 Cookie / Accept-Language 影响；
//  - .html 页面在有 Cookie 记忆时按用户语言重定向到对应 .html，
//    无 Cookie（含 Googlebot 等爬虫）一律直接服务，返回稳定 200；
//  - 中和 Cloudflare Clean URLs 的 “.html -> 无扩展名” 307，
//    让 .html 始终以其自身 URL 返回 200，与 <canonical>/sitemap 保持一致，
//    避免 GSC 报“重定向错误”。

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 1) 用户手动选择优先（由页面切换按钮写入 Cookie）
    const cookie = request.headers.get("Cookie") || "";
    const cm = cookie.match(/(?:^|;\s*)cxdmo_lang=(zh|en)/);
    let wantZh;
    if (cm) {
      wantZh = cm[1] === "zh";
    } else {
      // 2) 按浏览器语言偏好，默认英文
      wantZh = prefersChinese(request.headers.get("Accept-Language") || "");
    }

    // 根路径：**仅 `/` 做语言自动分流**（Cookie 记忆 > Accept-Language > 默认英文）。
    // 显式 /zh、/zh/ 一律直出中文首页 —— 语言分流若也作用于 /zh/，非中文偏好
    // （或不带 Accept-Language 的爬虫）的访问者会被弹回英文首页，与 sitemap /
    // hreflang 中登记的 /zh/ 冲突（GSC 会报「网页会重定向」）。
    // 注意：必须在此处、在“无扩展名 -> .html”处理之前判断，
    // 否则 /zh/ 会被误判为无扩展名页面而 301 到 /zh/.html。
    if (path === "/" || path === "/zh" || path === "/zh/") {
      if (path === "/" && wantZh) {
        return redirect(url.origin + "/zh/", !!cm);
      }
      if (path === "/zh") {
        // 归一到 sitemap / hreflang 登记的规范形态 /zh/
        return new Response(null, { status: 301, headers: { Location: url.origin + "/zh/" } });
      }
      // 服务对应语言的首页。html_handling="none" 下资产层不会自动把
      // 目录映射为 index.html，故显式向 ASSETS 绑定请求并以原 URL 返回。
      // 依赖 wrangler.toml [assets] 的 binding = "ASSETS"：该字段缺省时
      // env.ASSETS 为 undefined，任何调用都会抛 TypeError → 1101 → 500。
      const indexUrl = path === "/" ? "/index.html" : "/zh/index.html";
      try {
        return await env.ASSETS.fetch(new Request(url.origin + indexUrl, {
          method: request.method,
          headers: request.headers,
          redirect: "manual",
        }));
      } catch (err) {
        // 终极兜底：302 到 /index.html（该路径由资产层直接服务，不经过 worker，
        // 也不依赖 env.ASSETS），确保首页在任何配置异常下可达而非 500。
        return new Response(null, { status: 302, headers: { Location: indexUrl } });
      }
    }

    // 已下线文章（内容与既有文章重复，已合并）→ 301 到合并后的目标，避免死链。
    // 键为不带 .html 的规范路径，两种语言各一条。
    const REMOVED_ALIASES = {
      "/articles/biodlink-adc-cdmo-milestone-2026": "/articles/biodlink-h1-2026.html",
      "/zh/articles/biodlink-adc-cdmo-milestone-2026": "/zh/articles/biodlink-h1-2026.html",
    };
    const aliasKey = path.endsWith(".html") ? path.slice(0, -5) : path;
    if (REMOVED_ALIASES[aliasKey]) {
      return new Response(null, {
        status: 301,
        headers: { Location: url.origin + REMOVED_ALIASES[aliasKey] },
      });
    }

    // 仅对 .html 页面做处理，其余一律直出静态资产
    if (!path.endsWith(".html")) {
      // 为统一到 canonical 的 .html 形态、避免 Google 把干净 URL 当成独立页，
      // 对“无扩展名且非静态资产”的页面路径 301 到对应 .html。
      const isAssetLike = path.includes(".");
      if (!isAssetLike) {
        const target = new URL(url.origin + path + ".html");
        target.search = url.search; // 保留查询串（如 ?company=Porton）
        return new Response(null, { status: 301, headers: { Location: target.toString() } });
      }
      return env.ASSETS.fetch(request);
    }

    // .html 页面：
    //  - 有 Cookie 记忆时，按用户语言重定向到对应 .html 版本（人类体验）
    //  - 无 Cookie（含爬虫）直接服务，并中和 Clean URLs 的 307
    const isZhPath = path.startsWith("/zh/");
    if (cm) {
      if (wantZh && !isZhPath) {
        return redirect(url.origin + "/zh" + path, true);
      }
      if (!wantZh && isZhPath) {
        return redirect(url.origin + path.slice(3), true);
      }
    }

    // 直接服务 .html；若 Cloudflare Clean URLs 将其 307 到无扩展名，
    // 则抓取该无扩展名版本的真实内容并以原 .html URL 返回 200。
    const res = await env.ASSETS.fetch(request);
    if (res.status === 307 && res.headers.get("Location")) {
      const target = new URL(res.headers.get("Location"), url.origin);
      const r2 = await env.ASSETS.fetch(new Request(target.toString(), {
        method: request.method,
        headers: request.headers,
        redirect: "manual",
      }));
      if (r2.ok) {
        return new Response(r2.body, {
          status: 200,
          headers: { "content-type": r2.headers.get("content-type") || "text/html; charset=utf-8" },
        });
      }
    }
    return res;
  },
};

function redirect(location, forced) {
  const headers = { Location: location };
  // 仅自动识别（非手动）时声明随 Accept-Language 变化，便于 CDN/爬虫缓存正确
  if (!forced) headers["Vary"] = "Accept-Language";
  return new Response(null, { status: 302, headers });
}

// 解析 Accept-Language，比较 zh 与 en 的权重；两者皆无或 en 更高 → false（默认英文）
function prefersChinese(accept) {
  const parts = accept.split(",").map((s) => s.trim()).filter(Boolean);
  let zhQ = -1;
  let enQ = -1;
  for (const part of parts) {
    const [tag, qStr] = part.split(";q=");
    const q = qStr ? parseFloat(qStr) : 1;
    if (isNaN(q)) continue;
    const primary = tag.split("-")[0].toLowerCase();
    if (primary === "zh" && q > zhQ) zhQ = q;
    if (primary === "en" && q > enQ) enQ = q;
  }
  if (zhQ === -1 && enQ === -1) return false;
  return zhQ >= enQ;
}
