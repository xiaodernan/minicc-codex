// Browser views are disposable projections; the server owns the transcript.
export const SESSION_CACHE_PREFIX = "minicc-session-view:";
const INDEX_KEY = "minicc-session-cache-index-v1";
const MAX_ENTRIES = 24;
const MAX_TOTAL_CHARS = 1_200_000;
const MAX_ENTRY_CHARS = 180_000;

export function storeSessionMarkup(key, markup) {
  try {
    const storage = window.localStorage;
    let order;
    try { order = JSON.parse(storage.getItem(INDEX_KEY) || "[]"); } catch { order = []; }
    const existing = Object.keys(storage).filter((item) => item.startsWith(SESSION_CACHE_PREFIX) && item !== key);
    const available = new Set(existing);
    order = [...new Set((Array.isArray(order) ? order : []).filter((item) => available.has(item)).concat(existing))];
    const sizes = new Map(order.map((item) => [item, (storage.getItem(item) || "").length]));
    let total = [...sizes.values()].reduce((sum, size) => sum + size, 0);
    const evict = () => {
      const oldest = order.shift();
      if (oldest === undefined) return false;
      total -= sizes.get(oldest) || 0;
      storage.removeItem(oldest);
      return true;
    };
    const source = String(markup || "");
    if (!source || source.length > MAX_ENTRY_CHARS) storage.removeItem(key);
    else {
      while (order.length >= MAX_ENTRIES || total + source.length > MAX_TOTAL_CHARS) if (!evict()) break;
      // Other application preferences may also consume quota. Reclaim only
      // our disposable views and retry; never touch tokens or preferences.
      while (true) {
        try { storage.setItem(key, source); order.push(key); break; }
        catch { if (!evict()) { storage.removeItem(key); break; } }
      }
    }
    storage.setItem(INDEX_KEY, JSON.stringify(order));
  } catch { /* Storage is optional, including when access itself is denied. */ }
}
