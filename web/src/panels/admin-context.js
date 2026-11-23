// Cold-start baseline: 25 live reads measured p95 2303.8 ms, max 2348.853 ms; keep >10x headroom.
export const CONTEXT_TIMEOUT_FALLBACK_MS = 30_000;
const CONTEXT_TIMEOUT_FLOOR_MS = 5_000;
const CONTEXT_TIMEOUT_CEILING_MS = 120_000;
const CONTEXT_SAMPLE_LIMIT = 20;

const esc = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export function deriveContextTimeout(samples) {
  const values = samples
    .map(Number)
    .filter((value) => Number.isFinite(value) && value >= 0)
    .sort((a, b) => a - b);
  if (!values.length) return CONTEXT_TIMEOUT_FALLBACK_MS;
  const p95Index = Math.ceil(values.length * 0.95) - 1;
  const p95 = values[p95Index];
  const budget = Math.ceil((p95 * 3 + 1_000) / 1_000) * 1_000;
  return Math.min(CONTEXT_TIMEOUT_CEILING_MS, Math.max(CONTEXT_TIMEOUT_FLOOR_MS, budget));
}

const FAILURE_COPY = {
  timeout: ["timeout", "admin.contextTimeout"],
  "network": ["unreachable", "admin.contextOutage"],
  "server-error": ["server-error", "admin.contextServerError"],
  "http-error": ["rejected", "admin.contextRejected"],
  "auth-required": ["rejected", "admin.contextRejected"],
};

export function contextFailure(error) {
  return FAILURE_COPY[error?.code] || FAILURE_COPY.network;
}

export function contextPackState(pack) {
  if (!pack) return ["unreachable", "admin.contextOutage"];
  if (pack.ok === false) return ["backend-error", "admin.contextSlow"];
  if (!Array.isArray(pack.chunks) || !pack.chunks.length) return ["empty", "admin.contextEmpty"];
  return ["present", ""];
}

export function createContextInspector({
  factsEl,
  sourcesEl,
  refreshEl,
  request,
  t,
  question,
  now = () => performance.now(),
  initialSamples = [],
  onSamples,
  autostart = true,
}) {
  const samples = initialSamples.slice(-CONTEXT_SAMPLE_LIMIT);
  let timeoutMs = deriveContextTimeout(samples);
  let latestRequest = 0;

  function pending(state, text) {
    if (!factsEl || !sourcesEl) return;
    factsEl.dataset.contextState = state;
    factsEl.dataset.contextTimeoutMs = String(timeoutMs);
    delete factsEl.dataset.contextElapsedMs;
    sourcesEl.dataset.contextState = state;
    factsEl.innerHTML = `<p class="admin-brief-pending">${esc(text)}</p>`;
    sourcesEl.innerHTML = "";
  }

  function render(pack, elapsed) {
    if (!factsEl || !sourcesEl) return;
    const [state, copyKey] = contextPackState(pack);
    factsEl.dataset.contextState = state;
    factsEl.dataset.contextElapsedMs = String(Math.round(elapsed));
    factsEl.dataset.contextTimeoutMs = String(timeoutMs);
    sourcesEl.dataset.contextState = state;
    if (state !== "present") {
      const reason = state === "backend-error" && typeof pack.error === "string" && pack.error.trim()
        ? ` ${pack.error}` : "";
      pending(state, `${t(copyKey)}${reason}`);
      return;
    }
    const chunks = pack.chunks;
    const rows = [
      [t("admin.contextBudget"), `${pack.budget_tokens}`],
      [t("admin.contextPacked"), `${pack.estimated_tokens} tokens`],
      [t("admin.contextChunksCandidates"), `${chunks.length} / ${pack.candidates}`],
      [t("admin.contextFingerprint"), String(pack.prefix_fingerprint || "—")],
    ];
    const notes = [
      pack.truncated ? t("admin.contextTruncated") : "",
      t("admin.contextTiming", { elapsed: Math.round(elapsed), timeout: timeoutMs, samples: samples.length }),
    ].filter(Boolean);
    factsEl.innerHTML = `<div class="admin-context-facts-grid">${rows.map(([key, value]) =>
      `<div><span>${esc(key)}</span><b>${esc(value)}</b></div>`).join("")}</div>` +
      notes.map((note) => `<p class="admin-context-note">${esc(note)}</p>`).join("");
    sourcesEl.innerHTML = chunks.slice(0, 6).map((chunk, index) =>
      `<div class="admin-context-source"><span class="n">[${index + 1}]</span>` +
      `<code>${esc(chunk.source)}:${chunk.start_line}–${chunk.end_line}</code>` +
      `<span class="tok">${chunk.tokens} tok</span></div>`).join("");
  }

  async function read() {
    const requestNumber = ++latestRequest;
    const started = now();
    pending("pending", t("admin.contextPending"));
    try {
      const pack = await request(`/api/rag/context?q=${encodeURIComponent(question())}&budget=8000`, {}, timeoutMs);
      if (requestNumber !== latestRequest) return;
      const elapsed = Math.max(0, now() - started);
      samples.push(elapsed);
      if (samples.length > CONTEXT_SAMPLE_LIMIT) samples.shift();
      timeoutMs = deriveContextTimeout(samples);
      try { onSamples?.(samples.slice()); } catch {}
      render(pack, elapsed);
    } catch (error) {
      if (requestNumber !== latestRequest) return;
      const [state, copyKey] = contextFailure(error);
      pending(state, t(copyKey));
    }
  }

  refreshEl?.addEventListener("click", () => { void read(); });
  if (autostart) void read();
  return { read, timeoutMs: () => timeoutMs };
}
