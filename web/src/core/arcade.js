// Optional feature: download only after an explicit arcade action.
let pending;
export async function openArcade() {
  if (!window.openGame) {
    pending ||= new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = document.querySelector('meta[name="minicc-game-asset"]')?.content || "/game.js";
      script.onload = resolve;
      script.onerror = () => { script.remove(); pending = null; reject(new Error("Unable to load arcade")); };
      document.head.append(script);
    });
    await pending;
  }
  window.openGame?.();
}
