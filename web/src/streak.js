// M8-T955: a tiny streak of showing up — every day with at least one
// completed task counts one flame. Local-only, no network, no analytics;
// the number lives in localStorage and only the user can see it.
// The flame is lit once per day on the real completion path (after the
// live answer lands, independent of motion preference).

const KEY = "minicc-streak-v1";

function dayKey(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function parseStored() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.count !== "number" || !parsed?.day) return null;
    if (!Number.isFinite(parsed.count) || parsed.count < 1) return null;
    return { day: String(parsed.day), count: Math.floor(parsed.count) };
  } catch {
    return null;
  }
}

function currentCount(stored) {
  if (!stored) return 0;
  const today = dayKey(new Date());
  if (stored.day === today) return stored.count;
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (stored.day === dayKey(yesterday)) return stored.count;
  return 0;
}

export function updateStreakChip() {
  const chip = document.getElementById("streakChip");
  if (!chip) return;
  const days = currentCount(parseStored());
  const countEl = document.getElementById("streakCount");
  if (countEl) countEl.textContent = String(days);
  chip.hidden = days <= 0;
}

// Fires on the same real-completion path as the celebration burst.
// Counted once per calendar day; a gap of two or more days restarts at 1.
export function markTaskCompletedForStreak() {
  const today = dayKey(new Date());
  const stored = parseStored();
  let next;
  if (stored && stored.day === today) {
    next = stored; // already counted today — no double-lighting
  } else if (stored) {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    next = stored.day === dayKey(yesterday)
      ? { day: today, count: stored.count + 1 }
      : { day: today, count: 1 };
  } else {
    next = { day: today, count: 1 };
  }
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // a full localStorage must never break the celebration it rides on
  }
  updateStreakChip();
}
