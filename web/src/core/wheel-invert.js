// Mouse wheel direction — one module, one source of truth.
//
// `scrollNatural=true` (the original Mac OS "Unnatural" "wheel direction") =
// wheel up slides the page up, like a mouse wheel — this is the default and matches every
// Windows and Linux system on earth. The settings toggle opts into
// macOS natural scroll instead (where swipe-up drops the page down, iOS-style), so Mac
// users who prefer it keep the choice.
//
// Previous implementation only intercepted wheel events while the
// "invert" flag was set, meaning the OS default won — on macOS that is the
// natural direction, which is why the user reported the wheel feels reversed.
// This module now *sets direction unconditionally*, giving the workbench a
// deterministic scroll regardless of any trackpad/mouse setting the user has elsewhere.

const KEY = "minicc-scroll-natural";
let wired = false;

export function naturalScroll() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setNaturalScroll(on) {
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
  if (!event.deltaY) return;
  const target = findScrollable(event.target) ?? (document.scrollingElement ?? document.body);
  // wheel up = deltaY < 0.
  // Default (classic / Windows & Linux): wheel up = view earlier content (scrollTop decreases).
  // Natural (macOS swipe style):           wheel up = view later   content (scrollTop increases).
  const next = naturalScroll()
    ? target.scrollTop - event.deltaY
    : target.scrollTop + event.deltaY;
  // Always own the wheel: preventDefault so the OS default does not fight the setting.
  event.preventDefault();
  if (next !== target.scrollTop) target.scrollTop = next;
}

export function initWheelToggle() {
  if (wired) return;
  wired = true;
  document.addEventListener("wheel", onWheel, { passive: false });
}
