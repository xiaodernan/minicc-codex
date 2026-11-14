// M8-T960: the "/" key that filters the sidebar's recent-task list.
// Pure view behavior: no network, no re-render, zero task-content exposure.
// The list's own refresh re-paints it every few seconds; a MutationObserver
// re-applies the active query so typing doesn't fight the poller.
import { t } from "./core/i18n.js";

const DEBOUNCE_MS = 160;

export function initThreadFilter() {
  const input = document.getElementById("threadFilter");
  const list = document.getElementById("threadList");
  if (!input || !list) return;

  let timer = 0;
  const apply = () => {
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    list.querySelectorAll(".thread-item").forEach((button) => {
      const match = !query || (button.textContent ?? "").toLowerCase().includes(query);
      button.hidden = !match;
      if (match) visible += 1;
    });
    let empty = list.querySelector(".thread-filter-empty");
    if (query && visible === 0 && list.querySelector(".thread-item")) {
      if (!empty) {
        empty = document.createElement("div");
        empty.className = "thread-empty thread-filter-empty";
        empty.textContent = t("tasks.filterEmpty");
        list.append(empty);
      } else {
        empty.hidden = false;
      }
    } else if (empty) {
      empty.hidden = true;
    }
  };

  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(apply, DEBOUNCE_MS);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      input.value = "";
      apply();
      input.blur();
      event.stopPropagation();
      return;
    }
    if (event.key === "Enter") {
      const first = list.querySelector(".thread-item:not([hidden])");
      if (first) first.click();
    }
  });

  // "/" focuses the filter when the user isn't typing somewhere already.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
    const active = document.activeElement;
    const tag = active?.tagName?.toUpperCase();
    const editable = active?.isContentEditable
      || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if (editable) return;
    if (active?.closest?.(".panel, .dialog, .modal, #arcadeModal")) return;
    event.preventDefault();
    input.focus();
  });

  // The history poll re-paints rows every few seconds — re-apply the query.
  const observer = new MutationObserver(() => apply());
  observer.observe(list, { childList: true });
  apply();
}
