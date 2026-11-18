/**
 * Wheel direction for this app only.  Native overflow scrolling belongs to the OS
 * (Windows / Linux traditional by default; macOS natural).  That is the right
 * default, but it means this app can feel inverted on a machine whose system
 * scroll direction does not match the user's hands.  This module owns a tiny
 * opt-in: one capture-phase listener that, when enabled, flips the effective
 * deltaY sign for any scrollable element inside the app.  Atlas / Arcade canvases
 * have their own wheel contracts and are untouched.
 */
// M8-T1222: the stored preference key is bumped on purpose. A stale
// `minicc-wheel-invert=1` from an old build overrode the sane default for
// everyone on this origin forever, with no way back except the settings
// toggle (which reads no user's intent from that era). Direction is governed
// by the OS by default; the opt-in lives on under a fresh key that no
// historical value can hijack. The settings UI (stream.js) reads and writes
// this exact constant, kept in sync with the stale-key cleanup below.
const STORAGE_KEY = "minicc-wheel-v2";

let enabled = false;
try { enabled = localStorage.getItem(STORAGE_KEY) === "1"; } catch { /* storage unavailable */ }

export function wheelInvertEnabled() { return enabled; }

export function setWheelInvert(value) {
  enabled = Boolean(value);
  try { localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0"); } catch { /* private mode */ }
}

function isScrollable(el) {
  if (!el || el.nodeType !== 1) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === "html" || tag === "body" || tag === "document") return false;
  const cs = getComputedStyle(el);
  if (!/(auto|scroll)/.test(cs.overflowY)) return false;
  return el.scrollHeight > el.clientHeight + 4;
}

function findScrollable(start) {
  let el = start && start.nodeType === 1 ? start : null;
  while (el) {
    if (isScrollable(el)) return el;
    el = el.parentElement;
  }
  return null;
}

// One capture-phase listener: only active after the user opts in; Atlas / Arcade
// canvases are never scrollable and so never intercepted.
document.addEventListener("wheel", (ev) => {
  if (!enabled) return;
  const target = findScrollable(ev.target);
  if (!target) return;
  const delta = ev.deltaMode === 1 ? ev.deltaY * 16
    : ev.deltaMode === 2 ? ev.deltaY * 240
    : ev.deltaY;
  ev.preventDefault();
  target.scrollTop -= delta;
}, { passive: false, capture: true });
