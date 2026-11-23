// HTTP/auth transport. The view subscribes to auth-required independently.
import { authHeaders, state } from "./state.js";

// M8-T1315: attach a machine-readable code to every failure class while
// keeping the localized message byte-identical. Existing callers show only
// the message (or swallow the error), so this is a pure addition — panels that
// want to be honest about WHY a read failed can now branch on `code`.
function taggedError(message, code, extra) {
  const error = new Error(message);
  error.code = code;
  if (extra) Object.assign(error, extra);
  return error;
}

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
        throw taggedError(state.locale === "zh" ? "需要访问 token，请在弹窗中粘贴后重试。" : "Access token required. Paste it in the dialog and retry.", "auth-required");
      }
      // M8-T1315: 5xx means the service answered but failed; 4xx (other than
      // auth) means our request was rejected. Neither is "unreachable" — tag
      // the class so a panel can say the truth instead of guessing.
      throw taggedError(
        data.error || `${response.status} ${response.statusText}`,
        response.status >= 500 ? "server-error" : "http-error",
        { status: response.status },
      );
    }
    return data;
  } catch (error) {
    if (timedOut) {
      // M8-T1314: keep the localized message byte-identical (every caller
      // already shows it), but add a machine-readable code so a panel can
      // tell "the request timed out" apart from "the server is unreachable".
      // Previously callers did .catch(() => null) and reported both as an
      // outage — a slow response was accused of being a dead service.
      const timeoutError = new Error(state.locale === "zh" ? "请求超时，可刷新工作区重试；运行中的任务仍会继续。" : "Request timed out. Refresh to retry; running tasks continue.");
      timeoutError.code = "timeout";
      throw timeoutError;
    }
    // M8-T1315: a bare fetch rejection (TypeError: Failed to fetch) is a real
    // network outage. Leave already-tagged errors (auth/http/server/abort)
    // untouched — a cancellation is not a network failure.
    if (error && !error.code && error instanceof TypeError) {
      error.code = "network";
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener("abort", cancel);
  }
}
