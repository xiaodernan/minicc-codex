// M8-T894: desktop notifications for task completion. The one home for the
// permission state, the user toggle, and the terminal-event hook. Fires only
// when the tab is hidden — an on-screen toast already covers the visible case.
// Deliberately imports nothing from stream.js/panels: api.js sits below both,
// and a module cycle here would run their top level mid-initialisation. The
// click-to-open side instead dispatches "minicc-open-task", which main.js owns.
// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { t } from "./i18n.js";

const TOGGLE_KEY = "minicc-notifications";
const TERMINAL_TITLES = { completed: "notify.completed", failed: "notify.failed", cancelled: "notify.cancelled", interrupted: "notify.cancelled" };

function supported() {
  return typeof window.Notification === "function";
}

export function notificationsEnabled() {
  return localStorage.getItem(TOGGLE_KEY) === "true";
}

export function notificationsBlocked() {
  return supported() && window.Notification.permission === "denied";
}

// Returns true when the toggle may read as "on" afterwards; the caller owns the
// toast for denied permission or unsupported browsers (it knows the language UI).
export async function setNotificationsEnabled(enabled) {
  localStorage.setItem(TOGGLE_KEY, enabled ? "true" : "false");
  if (!enabled) return true;
  if (!supported()) return false;
  if (window.Notification.permission === "granted") return true;
  if (window.Notification.permission === "denied") return false;
  try {
    const permission = await window.Notification.requestPermission();
    if (permission === "granted") return true;
  } catch {
    // Some browsers reject requestPermission outside a user gesture; the
    // caller surfaces that as a plain failure toast.
  }
  return false;
}

// One hook from completeTask (the single terminal home in core/api.js).
// `task` carries { task_id, status, prompt, preview }.
export function notifyTaskFinished(task) {
  if (!notificationsEnabled() || !document.hidden || !supported()) return;
  if (window.Notification.permission !== "granted") return;
  const status = String(task?.status || "");
  const titleKey = TERMINAL_TITLES[status];
  if (!titleKey) return;
  const title = `minicc · ${t(titleKey)}`;
  const body = String(task?.prompt || task?.preview || task?.task_id || "").slice(0, 160);
  try {
    const notice = new window.Notification(title, { body, tag: `minicc-task-${task?.task_id || ""}`, silent: false });
    notice.onclick = () => {
      window.focus();
      if (task?.task_id) window.dispatchEvent(new CustomEvent("minicc-open-task", { detail: { taskId: task.task_id } }));
      notice.close();
    };
    window.setTimeout(() => notice.close(), 12000);
  } catch {
    // A flaky notification must never break the task lifecycle it reports on.
  }
}
