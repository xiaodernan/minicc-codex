// The Atlas' memory — which coordinates of the world the visitor has charted.
// One key, one shape: a JSON string of the union set of
//   "panel:<view>"     — e.g. "panel:almanac"
//   "chapter:<id>"     — e.g. "chapter:lighthouse" (almanac)
//   "manual:<id>"      — e.g. "manual:arch"
// Never throws: private mode or corrupt storage degrades to an empty set and
// the atlas simply shows everything as uncharted — honest, never fake.
const KEY = "minicc-visited";

export function markVisited(id) {
  if (!id) return;
  try {
    const set = new Set(JSON.parse(localStorage.getItem(KEY) || "[]"));
    set.add(String(id));
    localStorage.setItem(KEY, JSON.stringify([...set]));
  } catch {
    /* private mode — the atlas just shows fewer coordinates charted */
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

// The charted-coordinate schema the atlas renders against: 18 panes +
// 19 almanac chapters + 13 manual chapters = 50 waypoints.
export const ATLAS_COORDINATES = 50;
