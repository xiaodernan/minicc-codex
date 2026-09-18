// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { escapeHtml } from "../chat/markdown.js";
import { beginPanelRequest, changeStatusLabel, openPanel } from "../chat/stream.js";
import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, runtime, state } from "../core/state.js";
import { icon } from "../icons.js";
import { showToast } from "../panels/index.js";

export function fileTypeFromPath(path) {
  const extension = String(path || "").split(".").pop()?.toLowerCase();
  const map = {
    py: "python", js: "javascript", mjs: "javascript", cjs: "javascript", ts: "typescript",
    tsx: "typescript", jsx: "javascript", css: "css", scss: "scss", html: "xml", htm: "xml",
    md: "markdown", json: "json", sh: "bash", bash: "bash", yml: "yaml", yaml: "yaml",
    xml: "xml", svg: "xml", rs: "rust", go: "go", java: "java", kt: "kotlin",
  };
  return map[extension] || "";
}

export function looksLikeWorkspacePath(value) {
  const text = String(value || "").trim();
  if (!text || text.length > 260) return false;
  if (/^(ok|error|denied|completed|failed|blocked|done)$/i.test(text)) return false;
  if (/\s/.test(text) && !/[\\/]/.test(text)) return false;
  return /[\\/]/.test(text) || /\.[A-Za-z0-9]{1,8}$/.test(text);
}

export function highlightFileContent(content, language) {
  const source = String(content ?? "");
  const highlighter = typeof hljs !== "undefined" ? hljs : window.hljs;
  if (highlighter) {
    try {
      if (language && highlighter.getLanguage?.(language)) {
        return highlighter.highlight(source, { language, ignoreIllegals: true }).value;
      }
      if (!language && source.length <= 20000 && highlighter.highlightAuto) {
        return highlighter.highlightAuto(source).value;
      }
    } catch {
      // Highlighting is cosmetic.
    }
  }
  return escapeHtml(source);
}

export function fileEditorMarkup(path, content) {
  const source = String(content ?? "");
  const lines = source.length ? source.split("\n") : [""];
  const language = fileTypeFromPath(path);
  const highlighted = highlightFileContent(source, language);
  const gutter = lines.map((_, index) => `<span class="file-editor-ln">${index + 1}</span>`).join("");
  const classes = language ? `hljs language-${escapeHtml(language)}` : "hljs";
  return `<div class="file-editor">
    <div class="file-editor-toolbar"><span>${escapeHtml(t("file.current"))}</span><button type="button" class="file-copy-button" data-copy-file>${icon("copy")}<span>${escapeHtml(t("file.copy"))}</span></button></div>
    <textarea class="file-editor-source" hidden readonly>${escapeHtml(source)}</textarea>
    <div class="file-editor-body">
      <div class="file-editor-gutter" aria-hidden="true">${gutter}</div>
      <pre class="file-editor-code"><code class="${classes}">${highlighted || "&nbsp;"}</code></pre>
    </div>
  </div>`;
}

export function diffRowMarkup(kind, sign, oldLine, newLine, code) {
  const oldCell = oldLine ? `<span class="diff-ln diff-ln-old">${oldLine}</span>` : `<span class="diff-ln diff-ln-old"></span>`;
  const newCell = newLine ? `<span class="diff-ln diff-ln-new">${newLine}</span>` : `<span class="diff-ln diff-ln-new"></span>`;
  return `<span class="diff-row ${kind}">${oldCell}${newCell}<span class="diff-sign">${escapeHtml(sign || " ")}</span><span class="diff-code">${escapeHtml(code.length ? code : " ")}</span></span>`;
}

export function renderUnifiedDiffRows(patch) {
  const rows = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const line of String(patch || "").split("\n")) {
    if (line.startsWith("@@")) {
      const header = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
      if (header) {
        oldLine = Number(header[1]);
        newLine = Number(header[2]);
        inHunk = true;
      }
      rows.push(`<span class="diff-row diff-hunk"><span class="diff-code">${escapeHtml(line || " ")}</span></span>`);
      continue;
    }
    if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("--- ") || line.startsWith("+++ ") || line.startsWith("old mode") || line.startsWith("new mode") || line.startsWith("similarity ") || line.startsWith("rename ")) {
      rows.push(`<span class="diff-row diff-file"><span class="diff-code">${escapeHtml(line || " ")}</span></span>`);
      continue;
    }
    if (line.startsWith("\\")) {
      rows.push(`<span class="diff-row diff-meta"><span class="diff-code">${escapeHtml(line)}</span></span>`);
      continue;
    }
    if (!inHunk) {
      if (line) rows.push(`<span class="diff-row diff-file"><span class="diff-code">${escapeHtml(line)}</span></span>`);
      continue;
    }
    if (line.startsWith("+")) {
      rows.push(diffRowMarkup("diff-add-line", "+", 0, newLine, line.slice(1)));
      newLine += 1;
    } else if (line.startsWith("-")) {
      rows.push(diffRowMarkup("diff-del-line", "-", oldLine, 0, line.slice(1)));
      oldLine += 1;
    } else if (line) {
      rows.push(diffRowMarkup("diff-context", " ", oldLine, newLine, line.startsWith(" ") ? line.slice(1) : line));
      oldLine += 1;
      newLine += 1;
    }
  }
  return rows.join("");
}

let previewRequest = 0;
export async function openFilePreview(path) {
  const current = beginPanelRequest(`${t("panel.file")} · ${path}`);
  const request = ++previewRequest;
  const version = runtime.workspaceVersion;
  const workspace = state.workspacePath;
  const stale = () => !current() || request !== previewRequest || version !== runtime.workspaceVersion || workspace !== state.workspacePath;
  try {
    const [diff, data] = await Promise.all([
      requestJson(`/api/diff?path=${encodeURIComponent(path)}`),
      requestJson(`/api/file?path=${encodeURIComponent(path)}`).catch((error) => ({ content: "", error: error.message })),
    ]);
    if (stale()) return;
    const additions = Number(diff.additions || 0);
    const deletions = Number(diff.deletions || 0);
    const diffRows = renderUnifiedDiffRows(diff.patch);
    const diffBody = diffRows || `<span class="diff-row diff-empty"><span class="diff-code">${escapeHtml(t("diff.empty"))}</span></span>`;
    const fileHead = `<div class="diff-file-head"><span class="diff-file-path">${icon("file-code-2")}<strong>${escapeHtml(path)}</strong></span><span class="diff-file-badges"><span class="diff-badge diff-badge-status">${escapeHtml(changeStatusLabel(diff.status || "modified"))}</span><span class="diff-badge diff-badge-add">+${additions}</span><span class="diff-badge diff-badge-del">-${deletions}</span></span></div>`;
    const currentContent = data.error
      ? `<div class="file-tree-status" role="status">${escapeHtml(diff.status === "deleted" ? (state.locale === "zh" ? "文件已删除；上方显示删除前的差异。" : "File deleted; the diff above shows its previous content.") : data.error)}</div>`
      : fileEditorMarkup(path, data.content || "");
    openPanel(`${t("panel.file")} · ${path}`, `<div class="diff-toolbar"><span>${escapeHtml(t("diff.previewAria"))}</span><span class="mono">${escapeHtml(diff.source || "diff")}</span></div>${fileHead}<pre class="diff-preview" aria-label="${escapeHtml(`${t("diff.previewAria")} · ${t("diff.oldLine")} / ${t("diff.newLine")}`)}">${diffBody}</pre><details class="file-current" open><summary>${escapeHtml(t("file.current"))}</summary>${currentContent}</details>`);
  } catch (error) {
    if (stale()) return;
    openPanel(t("panel.file"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}

export async function copyFilePreviewContent() {
  const source = $("#panelBody .file-editor-source");
  const text = source instanceof HTMLTextAreaElement ? source.value : source?.textContent || "";
  try {
    await navigator.clipboard.writeText(text);
    showToast(t("file.copied"));
  } catch {
    showToast(state.locale === "zh" ? "复制失败，请在预览中手动选择文本。" : "Copy failed. Select the preview text to copy manually.");
  }
}
