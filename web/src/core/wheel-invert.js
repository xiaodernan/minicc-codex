// Mouse wheel direction — one module, one source of truth.
// Default (Windows / Linux) wheel-up scrolls the page upward. On flips to
// macOS-style natural scroll: wheel-up scrolls content downward (swipe follows fingers).
// Off by default; the settings toggle persists the choice in localStorage.

const KEY = "minicc-invert-wheel";
let wired = false;

export function wheelInverted() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setWheelInverted(on) {
  try {
    if (on) localStorage.setItem(KEY, "1");
    else localStorage.removeItem(KEY);
  } catch {
    // private mode
  }
}

function findScrollable(start) {
  let el = start;
  while (el && el.nodeType === 1) {
    const style = window.getComputedStyle(el);
    const overflowY = style?.overflowY;
    if ((overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") && el.scrollHeight > el.clientHeight + 1) {
      return el;
    }
    el = el.parentElement;
  }
  return null;
}

function onWheel(event) {
  if (!wheelInverted()) return;      // default — browser owns it
  if (!event.deltaY) return;
  const target = findScrollable(event.target) ?? (document.scrollingElement ?? document.body);
  const next = target.scrollTop - event.deltaY;
  if (next > 0 || target.scrollTop > 0) {
    target.scrollTop = next;
    event.preventDefault();
  }
}

export function initWheelToggle() {
  if (wired) return;
  wired = true;
  document.addEventListener("wheel", onWheel, { passive: false });
}
