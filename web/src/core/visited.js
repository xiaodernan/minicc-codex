// The Atlas' memory — which coordinates of the world the visitor has charted,
// and in what order they were charted.
// One key, one shape: a JSON string of the ordered union array of
//   "panel:<view>"     — e.g. "panel:almanac"
//   "chapter:<id>"     — e.g. "chapter:lighthouse" (almanac)
//   "manual:<id>"      — e.g. "manual:arch"
// Never throws: private mode or corrupt storage degrades to an empty trail and
// the atlas simply shows everything as uncharted — honest, never fake.
const KEY = "minicc-visited";
const ORDER_KEY = "minicc-visited-order";
const MILESTONE_KEY = "minicc-stardust-milestone";

/** Stardust milestone wiring — Atlas checks after every visit. */
let stardustListener = null;
export function setStardustListener(fn) {
  stardustListener = typeof fn === "function" ? fn : null;
}
export function readStardustMilestone() {
  try {
    return Number(localStorage.getItem(MILESTONE_KEY) || "0") || 0;
  } catch {
    return 0;
  }
}
export function writeStardustMilestone(n) {
  try {
    localStorage.setItem(MILESTONE_KEY, String(Number(n) || 0));
  } catch {
    /* private mode — milestone simply won't persist */
  }
}

export function markVisited(id) {
  if (!id) return;
  try {
    const seq = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]");
    const set = new Set(JSON.parse(localStorage.getItem(KEY) || "[]"));
    const value = String(id);
    if (!set.has(value)) {
      if (Array.isArray(seq)) {
        seq.push(value);
        localStorage.setItem(ORDER_KEY, JSON.stringify(seq));
      }
      set.add(value);
      localStorage.setItem(KEY, JSON.stringify([...set]));
    } else if (Array.isArray(seq) && !seq.includes(value)) {
      // migrate: visited already had this id from before the order key existed
      seq.push(value);
      localStorage.setItem(ORDER_KEY, JSON.stringify(seq));
    }
  } catch {
    /* private mode — the atlas just shows fewer coordinates charted */
  }
  if (stardustListener) {
    try { stardustListener(); } catch { /* milestone toasts must never break the visit itself */ }
  }
}

export function readVisited() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw.map(String) : []);
  } catch {
    return new Set();
  }
}

/** The charted order — the trail the atlas can draw. Empty in private mode. */
export function readVisitTrail() {
  try {
    const raw = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]");
    return Array.isArray(raw) ? raw.map(String) : [];
  } catch {
    return [];
  }
}

/** Wipe every charted coordinate — honestly, everywhere. */
export function clearVisitHistory() {
  try {
    localStorage.removeItem(KEY);
    localStorage.removeItem(ORDER_KEY);
    localStorage.removeItem(MILESTONE_KEY);
    return true;
  } catch {
    return false;
  }
}


