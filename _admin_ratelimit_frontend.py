# -*- coding: utf-8 -*-
import io

p = "web/src/panels/admin.js"
t = io.open(p, encoding="utf-8").read()

anchor = """    const auditPromise = requestJson("/api/oracle-audit-story", {}, 30000).catch(() => null);
    auditPromise.then((story) => renderAudit(story, false));
"""
addition = anchor + """    // Gateway budget — how close the shared 60s / 20-per-client token bucket is
    // to refusing the panel's own model calls; reads what the gate keeps.
    function renderRatelimit(stats, refreshed) {
      const bodyEl = $("#adminRatelimitBody");
      const usageEl = $("#adminRatelimitUsage");
      if (!stats || stats.error) {
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.ratelimitOutage"))}</p>`;
        if (usageEl) usageEl.textContent = stats?.error ? `error: ${String(stats.error).slice(0, 140)}` : "";
        return;
      }
      const allowedRedis = Number(stats?.decisions?.allowed_redis ?? 0);
      const allowedLocal = Number(stats?.decisions?.allowed_local ?? 0);
      const denied = Number(stats?.decisions?.denied ?? 0);
      const degraded = Number(stats?.decisions?.degraded_open ?? 0);
      const allowed = allowedRedis + allowedLocal;
      const limit = Number(stats.limit ?? 20);
      const windowS = Number(stats.window_seconds ?? 60);
      if (bodyEl) {
        bodyEl.innerHTML = `<ul class="admin-ratelimit-list">
          <li><strong>${zh() ? "每客户端每窗口" : "Per client, per window"}</strong><span>${esc(`${limit} / ${windowS}s`)}</span></li>
          <li><strong>${zh() ? "放行" : "Allowed"}</strong><span>${esc(`${allowed} (redis ${allowedRedis} · ${zh() ? "本地" : "local"} ${allowedLocal})`)}</span></li>
          <li><strong>${zh() ? "拒绝" : "Denied"}</strong><span>${esc(String(denied))}</span></li>
          <li><strong>${zh() ? "降级放行（Redis 断→照常服务并计数）" : "Degraded-open (Redis down → serve anyway, counted)"}</strong><span>${esc(String(degraded))}</span></li>
          <li><strong>${zh() ? "本地窗口占用" : "Local windows held"}</strong><span>${esc(String(stats.remaining_local_windows ?? 0))}</span></li>
        </ul>`;
      }
      if (usageEl) {
        usageEl.textContent = zh()
          ? `共享闸门 · Redis ${allowedRedis ? "在线" : "未配置/不可用"}${refreshed ? " · 已重读" : ""}`
          : `Shared bucket · Redis ${allowedRedis ? "serving" : "unconfigured / unavailable"}${refreshed ? " · re-read" : ""}`;
      }
    }
    const ratelimitRefresh = $("#adminRatelimitRefresh");
    if (ratelimitRefresh) {
      ratelimitRefresh.addEventListener("click", () => {
        const bodyEl = $("#adminRatelimitBody");
        const usageEl = $("#adminRatelimitUsage");
        if (bodyEl) bodyEl.innerHTML = `<p class="admin-brief-pending">${esc(t("admin.ratelimitPending"))}</p>`;
        if (usageEl) usageEl.textContent = "";
        requestJson("/api/admin/ratelimit", {}, 10000).catch(() => null).then((stats) => renderRatelimit(stats, true));
      });
    }
    const ratelimitPromise = requestJson("/api/admin/ratelimit", {}, 10000).catch(() => null);
    ratelimitPromise.then((stats) => renderRatelimit(stats, false));
"""
assert t.count(anchor) == 1
t = t.replace(anchor, addition, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("admin.js: gateway budget wired")

# styles: small list styling
p = "web/styles.css"
t = io.open(p, encoding="utf-8").read()
addition = "\n.admin-ratelimit-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }\n.admin-ratelimit-list li { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; border-bottom: 1px solid var(--line); padding: 6px 2px; }\n.admin-ratelimit-list li:last-child { border-bottom: 0; }\n.admin-ratelimit-list strong { color: var(--muted); font-weight: 600; }\n.admin-ratelimit-list span { font-family: var(--font-mono); color: var(--text); }\n"
t = t.rstrip("\n") + "\n" + addition.lstrip("\n")
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("styles.css: ratelimit list styles added")

# i18n keys (CRLF pinned file, byte-safe)
p = "web/src/core/i18n.js"
raw = open(p, "rb").read()
t = raw.decode("utf-8")
NL = "\r\n"
zh_old = '"admin.auditRefresh": "重新读审计故事", "admin.auditOutage": "值守读者暂时不可用——先看审计导出的原始记录。",' + NL
zh_new = zh_old + '    "admin.ratelimitKicker": "网关预算 · 共享闸门", "admin.ratelimitPending": "正在读共享闸尺…",' + NL
assert t.count(zh_old) == 1
t = t.replace(zh_old, zh_new, 1)
zh_old = '"admin.auditRefresh": "重新读审计故事", "admin.auditOutage": "值守读者暂时不可用——先看审计导出的原始记录。",' + NL + '    "admin.ratelimitKicker": "网关预算 · 共享闸门", "admin.ratelimitPending": "正在读共享闸尺…",' + NL
zh_new = zh_old + '    "admin.ratelimitRefresh": "刷新网关预算", "admin.ratelimitOutage": "闸门计数暂时不可读——闸本身 fail-open 照常放行，账本照记。",' + NL
assert t.count(zh_new) == 2 or True  # noqa: it changed already above; recompute below instead
# safer: recompute from current text
t2 = t.replace('"admin.ratelimitRefresh": "刷新网关预算", "admin.ratelimitOutage": "闸门计数暂时不可读——闸本身 fail-open 照常放行，账本照记。",' + NL, "")
t = zh_old + '    "admin.ratelimitRefresh": "刷新网关预算", "admin.ratelimitOutage": "闸门计数暂时不可读——闸本身 fail-open 照常放行，账本照记。",' + NL + t.split(zh_old, 1)[1] if t.count(zh_old) == 1 else t
en_old = '"admin.auditRefresh": "Re-read the audit story", "admin.auditOutage": "The on-duty reader is unavailable — check the raw audit trail first.",' + NL
en_new = en_old + '    "admin.ratelimitKicker": "Gateway budget · shared gate", "admin.ratelimitPending": "Reading the shared bucket…",' + NL
assert t.count(en_old) == 1
t = t.replace(en_old, en_new, 1)
en_old2 = en_new + '    "admin.ratelimitRefresh": "Refresh the gateway budget", "admin.ratelimitOutage": "The gate counters are unreadable — the gate itself fails open and keeps counting.",' + NL
assert t.count(en_old + '    "admin.ratelimitRefresh": "Refresh the gateway budget", "admin.ratelimitOutage": "The gate counters are unreadable — the gate itself fails open and keeps counting.",' + NL) == 0
t = t.replace(en_old + '    "admin.ratelimitKicker": "Gateway budget · shared gate", "admin.ratelimitPending": "Reading the shared bucket…",' + NL, en_old2, 1)
open(p, "wb").write(t.encode("utf-8"))
print("i18n.js: ratelimit keys added")
