// cxdmo.com 边缘语言分流 + 爬行稳定性
// 默认英文（根路径）；中文位于 /zh/。
// 优先级：Cookie(cxdmo_lang) > 浏览器 Accept-Language > 默认英文。
//
// 关键约束（SEO / Google 索引）：
//  - 仅对“根路径 /”做语言自动分流重定向；
//  - .html 页面在有 Cookie 记忆时按用户语言重定向到对应 .html，
//    无 Cookie（含 Googlebot 等爬虫）一律直接服务，返回稳定 200；
//  - 中和 Cloudflare Clean URLs 的 “.html -> 无扩展名” 307，
//    让 .html 始终以其自身 URL 返回 200，与 <canonical>/sitemap 保持一致，
//    避免 GSC 报“重定向错误”。

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 仅对 HTML 页面（含根路径）做处理，其余一律直出静态资产
    const isHtml = path === "/" || path.endsWith(".html");
    if (!isHtml) {
      return env.ASSETS.fetch(request);
    }

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

    // 根路径：语言分流（首访自动 + Cookie 记忆）
    if (path === "/" || path === "/zh" || path === "/zh/") {
      if (wantZh && path !== "/zh" && path !== "/zh/") {
        return redirect(url.origin + "/zh/", !!cm);
      }
      if (!wantZh && (path === "/zh" || path === "/zh/")) {
        return redirect(url.origin + "/", !!cm);
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
      const r2 = await env.ASSETS.fetch(new Request(target, request));
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
