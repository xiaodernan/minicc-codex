// M8-T946: a small, honest burst of delight when a task actually
// completes. Reduced-motion users get the silent, instant version.
// One home, fired only from the live completion path in core/api.js —
// never on history restore, never on failure. Brings a little of the
// celebration that every finished minicc task deserves.
const PALETTE = ["#34d399", "#fbbf24", "#a78bfa", "#60a5fa", "#f472b6", "#f97316"];

export function celebrate(anchor) {
  try {
    // Reduced motion: no particles at all. The completion toast and the
    // timestamp on the bubble are already the visible celebration.
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    if (!anchor || typeof anchor.getBoundingClientRect !== "function") return;

    const rect = anchor.getBoundingClientRect();
    const cx = rect.left + rect.width * 0.5;
    const cy = rect.top + rect.height * 0.35;
    const layer = document.createElement("div");
    layer.className = "celebration-layer";
    document.body.append(layer);

    const count = 26;
    const spread = Math.max(80, Math.min(180, rect.width * 0.75));
    for (let index = 0; index < count; index += 1) {
      const spark = document.createElement("span");
      spark.className = "celebration-spark";
      const angle = (Math.PI * 2 * index) / count + (Math.random() - 0.5) * 0.45;
      const distance = spread * (0.45 + Math.random() * 0.6);
      const dx = Math.cos(angle) * distance;
      const dy = Math.sin(angle) * distance - 36;
      spark.style.setProperty("--cx", `${cx + (Math.random() - 0.5) * rect.width * 0.5}px`);
      spark.style.setProperty("--cy", `${cy + (Math.random() - 0.5) * rect.height * 0.4}px`);
      spark.style.setProperty("--dx", `${dx.toFixed(1)}px`);
      spark.style.setProperty("--dy", `${dy.toFixed(1)}px`);
      spark.style.setProperty("--hue", String(Math.round(Math.random() * 360)));
      spark.style.setProperty("--size", `${(4 + Math.random() * 5).toFixed(1)}px`);
      spark.style.setProperty("--delay", `${(Math.random() * 0.18).toFixed(3)}s`);
      spark.style.setProperty("--color", PALETTE[index % PALETTE.length]);
      spark.style.setProperty("--spin", `${(Math.random() - 0.5) * 540}deg`);
      layer.append(spark);
    }
    window.setTimeout(() => layer.remove(), 1600);
  } catch {
    // A celebration must never break the lifecycle it celebrates.
  }
}
