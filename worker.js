// cxmdo.com 边缘语言分流
// 默认英文（根路径）；中文位于 /zh/。
// 优先级：Cookie(cxmdo_lang) > 浏览器 Accept-Language > 默认英文。
// 仅在 / 与 .html 页面做重定向；静态资产（assets/、sitemap、robots 等）直出。

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 仅对 HTML 页面（含根路径）做语言分流，其余一律直出静态资产
    const isHtml = path === "/" || path.endsWith(".html");
    if (!isHtml) {
      return env.ASSETS.fetch(request);
    }

    // 1) 用户手动选择优先（由页面切换按钮写入 Cookie）
    const cookie = request.headers.get("Cookie") || "";
    const cm = cookie.match(/(?:^|;\s*)cxmdo_lang=(zh|en)/);
    let wantZh;
    let forced = false;
    if (cm) {
      wantZh = cm[1] === "zh";
      forced = true;
    } else {
      // 2) 按浏览器语言偏好，默认英文
      wantZh = prefersChinese(request.headers.get("Accept-Language") || "");
    }

    const isZhPath = path.startsWith("/zh/") || path === "/zh";

    // 需要中文，但当前在英文路径 → 重定向到 /zh 对应页
    if (wantZh && !isZhPath) {
      const target = path === "/" ? "/zh/" : "/zh" + path;
      return redirect(url.origin + target, forced);
    }
    // 需要英文，但当前在中文路径 → 去掉 /zh 前缀
    if (!wantZh && isZhPath) {
      const target = path === "/zh" || path === "/zh/" ? "/" : path.slice(3);
      return redirect(url.origin + target, forced);
    }

    return env.ASSETS.fetch(request);
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
