// Optional feature: download only after an explicit arcade action.
// We also warm the bundle on idle so the click path is instant and the
// network is never contended for the lazy injection.
let pending;

function ensureArcadeLoaded() {
  if (window.openGame) return Promise.resolve();
  pending ||= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = document.querySelector('meta[name="minicc-game-asset"]')?.content || "/game.js";
    script.onload = resolve;
    script.onerror = () => { script.remove(); pending = null; reject(new Error("Unable to load arcade")); };
    document.head.append(script);
  });
  return pending;
}

export function preloadArcade() {
  return ensureArcadeLoaded().catch(() => undefined);
}

function setArcadeBusy(busy) {
  const btn = document.getElementById("arcadeButton");
  if (!btn) return () => {};
  const prev = { disabled: btn.disabled, ariaBusy: btn.getAttribute("aria-busy"), className: btn.className };
  if (busy) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.classList.add("nav-item-busy");
  }
  return () => {
    btn.disabled = prev.disabled;
    if (prev.ariaBusy === null) btn.removeAttribute("aria-busy");
    else btn.setAttribute("aria-busy", prev.ariaBusy);
    btn.classList.remove("nav-item-busy");
  };
}

export async function openArcade() {
  const done = setArcadeBusy(true);
  try {
    await ensureArcadeLoaded();
  } finally {
    done();
  }
  window.openGame?.();
}
