// HTTP/auth transport. The view subscribes to auth-required independently.
import { authHeaders, state } from "./state.js";

export async function requestJson(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) cancel();
  else options.signal?.addEventListener("abort", cancel, { once: true });
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const headers = new Headers(authHeaders());
    new Headers(options.headers || {}).forEach((value, key) => headers.set(key, value));
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });
    const data = response.status === 204 ? {} : await response.json().catch((error) => {
      if (controller.signal.aborted) throw controller.signal.reason || error;
      if (response.ok) throw new Error(state.locale === "zh" ? "服务器返回了无效数据，请重试。" : "The server returned invalid data. Please retry.");
      return {};
    });
    if (!response.ok) {
      if (response.status === 401 && data.auth_required) {
        window.dispatchEvent(new CustomEvent("minicc-auth-required"));
        throw new Error(state.locale === "zh" ? "需要访问 token，请在弹窗中粘贴后重试。" : "Access token required. Paste it in the dialog and retry.");
      }
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  } catch (error) {
    if (timedOut) throw new Error(state.locale === "zh" ? "请求超时，可刷新工作区重试；运行中的任务仍会继续。" : "Request timed out. Refresh to retry; running tasks continue.");
    throw error;
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener("abort", cancel);
  }
}
