import { requestJson } from "./core/transport.js";
import { openArcade } from "./core/arcade.js";
// ES module source for the minicc workbench. Bundled by scripts/build-web.mjs.
import { escapeHtml, loadTaskHistory, persistSessionView, renderSession, renderTaskHistory, sessionViewKey } from "./chat/markdown.js";
import { addImageFiles, cancelActiveTask, closePanel, exportChat, loadWorkspace, openActivityPanel, openBatchPanel, openHelpPanel, openOptionsPanel, openPanel, openPromoPanel, openSettingsPanel, openTaskDetail, openTaskInWorkspace, openTaskListPanel, openWorkspacesPanel, renderAttachmentTray, resetTask, restoreTaskSnapshot, rewindToUserIndex, runDemoFlow, sendMessage, switchInspectorTab, togglePanelFullscreen, watchTask } from "./chat/stream.js";
import { applyTaskEvent, setTimelineDetails, syncLiveEvents, updateBoundTask, updateLiveTask } from "./core/api.js";
import { t } from "./core/i18n.js";
import { applyFocusMode, applyLocale, applyPaneLayout, finishStartupSplash, prepareStartupSplash, setFocusMode, setInspectorCollapsed, setLocale, setSidebarCollapsed, setStartupSplashError, setTheme } from "./core/locale.js";
import { $, $$, runningTasks, runtime, sessionMarkup, state, taskBySession } from "./core/state.js";
import { copyFilePreviewContent, looksLikeWorkspacePath, openFilePreview } from "./files/preview.js";
import { applyIcons, icon, refreshIcons } from "./icons.js";
import { handleFileTreeKeydown } from "./panels/index.js";
import { PERMISSION_MODES, addAssistantMessage, addLoadingMessage, addUserMessage, applyMentionOption, assistantMessageMarkup, bindRunningTask, closeMentionPopover, effectiveTaskPermissions, eventTimelineMarkup, handleMentionKeydown, mentionState, openGlobalSearchPanel, refreshFileTree, scrollChat, setBusy, setPermissionMode, setSession, showAuthModal, showToast, stopTaskTimer, submitAuthToken, taskSessionKey, toggleFileDir, toggleTodoSection, updateChatFollowState, updateMentionPopover, updateMode, updateReasoningControl, updateTaskDock, visibleAgentEvents } from "./panels/index.js";

export function bindUI() {
  window.addEventListener("minicc-auth-required", showAuthModal);
  $("#chatForm").addEventListener("submit", sendMessage);
  $("#chatArea").addEventListener("scroll", () => {
    state.chatRestoreVersion += 1;
    state.chatUserScrolledAt = performance.now();
    updateChatFollowState();
  }, { passive: true });
  $("#jumpLatestButton").addEventListener("click", () => scrollChat("auto", true));
  $("#newTaskButton").addEventListener("click", resetTask);
  $("#demoFlowButton").addEventListener("click", runDemoFlow);
  $("#cancelTaskButton").addEventListener("click", cancelActiveTask);
  $("#gameClose")?.addEventListener("click", () => window.closeGame?.());
  $("#gameNewWindow")?.addEventListener("click", () => window.openGameWindow?.());
  $("#gameWideMode")?.addEventListener("click", () => window.toggleGameWideMode?.());
  $("#gameCodex")?.addEventListener("click", () => window.openGameCodex?.("plants"));
  $("#gameCodexClose")?.addEventListener("click", () => window.closeGameCodex?.());
  document.querySelectorAll(".codex-tab").forEach((tab) => tab.addEventListener("click", () => window.openGameCodex?.(tab.dataset.codexTab)));
  $("#gameCodexPanel")?.addEventListener("click", (event) => { if (event.target.id === "gameCodexPanel") window.closeGameCodex?.(); });
  $("#gameFullscreen")?.addEventListener("click", () => window.toggleGameFullscreen?.());
  $("#gameStart")?.addEventListener("click", () => window.startGame?.());
  $("#gameShovel")?.addEventListener("click", () => window.toggleShovel?.());
  document.querySelectorAll(".game-skill").forEach((button) => button.addEventListener("click", () => window.activateGameSkill?.(button.dataset.skill)));
  $("#gamePause")?.addEventListener("click", () => window.toggleGamePause?.());
  $("#gameDifficulty")?.addEventListener("change", (event) => window.setGameDifficulty?.(event.target.value));
  $("#gameAutoSun")?.addEventListener("change", (event) => {
    if (window.game) window.game.autoSun = event.target.checked;
    localStorage.setItem("minicc-game-auto-sun", event.target.checked ? "on" : "off");
  });
  $("#gameSoundToggle")?.addEventListener("click", () => window.toggleGameSound?.());
  $("#gameVolume")?.addEventListener("input", (event) => window.setGameVolume?.(event.target.value));
  document.addEventListener("visibilitychange", () => window.setGamePaused?.(document.hidden));
  $("#gameModal")?.addEventListener("click", (event) => { if (event.target.id === "gameModal") window.closeGame?.(); });
  $("#gameCanvas")?.addEventListener("click", (event) => {
    if (window.collectSun?.(event)) return;
    window.plantAt?.(event);
  });
  $("#gameCanvas")?.addEventListener("pointermove", (event) => window.updateGameHover?.(event), { passive: true });
  $("#gameCanvas")?.addEventListener("pointerleave", () => window.clearGameHover?.(), { passive: true });
  document.querySelectorAll(".seed-card").forEach((card) => card.addEventListener("click", () => window.selectPlant?.(card)));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const arcade = window.game;
      if ($("#gameModal")?.classList.contains("show") && (arcade?.selected || arcade?.shovel)) {
        window.clearPlantSelection?.();
        if (arcade) arcade.shovel = false;
        window.updateShovelButton?.();
      } else { window.closeGame?.(); closePanel(); }
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") { event.preventDefault(); resetTask(); }
    if (event.key === "/" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") { event.preventDefault(); $("#threadSearch").focus(); }
  });
  $("#allowChanges").addEventListener("change", (event) => {
    state.allowChanges = event.target.checked;
    localStorage.setItem("minicc-allow", String(state.allowChanges));
    updateMode();
    showToast(state.allowChanges ? (state.locale === "zh" ? "已允许当前任务修改" : "Changes enabled for new requests") : (state.locale === "zh" ? "已启用安全模式" : "Safe mode enabled"));
  });
  $("#allowNetwork").addEventListener("change", (event) => {
    state.allowNetwork = event.target.checked;
    updateMode();
    localStorage.setItem("minicc-network", String(state.allowNetwork));
    showToast(state.allowNetwork ? (state.locale === "zh" ? "已允许当前任务联网搜索" : "Web search enabled for new requests") : (state.locale === "zh" ? "已关闭联网搜索" : "Web search disabled"));
  });
  $("#permModeGroup").addEventListener("click", (event) => {
    const option = event.target.closest(".perm-mode-option[data-mode]");
    if (option) setPermissionMode(option.dataset.mode);
  });
  $("#permModeGroup").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const index = PERMISSION_MODES.indexOf(state.permissionMode);
    const delta = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    setPermissionMode(PERMISSION_MODES[(index + delta + PERMISSION_MODES.length) % PERMISSION_MODES.length]);
    $("#permModeGroup .perm-mode-option.active")?.focus();
  });
  $("#todoSectionToggle").addEventListener("click", () => toggleTodoSection());
  $("#localeZh").addEventListener("click", () => setLocale("zh"));
  $("#localeEn").addEventListener("click", () => setLocale("en"));
  $("#themeButton").addEventListener("click", () => setTheme(state.theme === "light" ? "dark" : "light"));
  $("#focusToggle").addEventListener("click", () => setFocusMode(!state.focusMode));
  $("#moreOptionsButton").addEventListener("click", openOptionsPanel);
  $("#reasoningButton").addEventListener("click", openSettingsPanel);
  $("#moreTasksButton").addEventListener("click", openTaskListPanel);
  $("#globalSearchButton").addEventListener("click", openGlobalSearchPanel);
  $("#taskDockOpen").addEventListener("click", openActivityPanel);
  $("#batchButton").addEventListener("click", openBatchPanel);
  $("#attachButton").addEventListener("click", () => $("#imageInput").click());
  $("#imageInput").addEventListener("change", (event) => { addImageFiles(event.target.files); });
  $("#attachmentTray").addEventListener("click", (event) => {
    const target = event.target.closest("[data-remove-attachment]");
    if (!target) return;
    state.attachments = state.attachments.filter((item) => item.id !== target.dataset.removeAttachment);
    renderAttachmentTray();
  });
  $("#composerShell").addEventListener("dragover", (event) => { if ([...(event.dataTransfer?.items || [])].some((item) => item.kind === "file")) { event.preventDefault(); $("#composerShell").classList.add("drag-active"); } });
  $("#composerShell").addEventListener("dragleave", () => $("#composerShell").classList.remove("drag-active"));
  $("#composerShell").addEventListener("drop", (event) => { event.preventDefault(); $("#composerShell").classList.remove("drag-active"); addImageFiles(event.dataTransfer?.files); });
  $("#promptInput").addEventListener("paste", (event) => { const images = [...(event.clipboardData?.files || [])].filter((file) => String(file.type || "").startsWith("image/")); if (images.length) { event.preventDefault(); addImageFiles(images); } });
  $("#profileButton").addEventListener("click", openSettingsPanel);
  $("#panelClose").addEventListener("click", closePanel);
  $("#panelExpand").addEventListener("click", togglePanelFullscreen);
  $("#panelModal").addEventListener("click", (event) => { if (event.target.id === "panelModal") closePanel(); });
  $("#refreshFiles").addEventListener("click", () => { loadWorkspace(); showToast(state.locale === "zh" ? "工作区状态已刷新" : "Workspace refreshed"); });
  $("#refreshFileTree").addEventListener("click", refreshFileTree);
  $("#fileTree").addEventListener("click", (event) => {
    const dirRow = event.target.closest("[data-tree-dir]");
    if (dirRow) { toggleFileDir(dirRow.dataset.treeDir); return; }
    const fileRow = event.target.closest("[data-open-diff]");
    if (fileRow) openFilePreview(fileRow.dataset.openDiff);
  });
  document.querySelectorAll(".inspector-tab").forEach((button) => button.addEventListener("click", () => switchInspectorTab(button.dataset.inspectorTab)));
  $("#fileTree").addEventListener("keydown", handleFileTreeKeydown);
  $("#fileTree").addEventListener("focusin", (event) => {
    const row = event.target.closest('[role="treeitem"]');
    if (row) $("#fileTree").querySelectorAll('[role="treeitem"]').forEach((item) => { item.tabIndex = item === row ? 0 : -1; });
  });
  $(".inspector-tabs").addEventListener("keydown", (event) => {
    const tabs = $$(".inspector-tab");
    const index = tabs.indexOf(document.activeElement);
    if (index < 0 || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowLeft" ? -1 : 1) + tabs.length) % tabs.length;
    tabs[next].click(); tabs[next].focus();
  });
  $("#fileList").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-diff]");
    if (target) openFilePreview(target.dataset.openDiff);
  });
  $("#changeList").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-diff]");
    if (target) openFilePreview(target.dataset.openDiff);
  });
  $("#messageList").addEventListener("click", (event) => {
    const start = event.target.closest("[data-start-action]");
    if (start) {
      $("#promptInput").value = t(`start.${start.dataset.startAction}Prompt`);
      $("#promptInput").focus();
      $("#promptInput").dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    const timelineToggle = event.target.closest("[data-timeline-toggle]");
    if (timelineToggle) {
      const timeline = timelineToggle.closest(".execution-trail");
      setTimelineDetails(timeline, timelineToggle.dataset.timelineToggle === "expand");
      event.preventDefault();
      return;
    }
    const rewind = event.target.closest(".rewind-to-here");
    if (rewind) {
      event.preventDefault();
      rewindToUserIndex(rewind.dataset.userIndex);
      return;
    }
    const restore = event.target.closest("[data-restore-task]");
    if (restore) {
      event.preventDefault();
      restoreTaskSnapshot(restore.dataset.restoreTask);
      return;
    }
    const target = event.target.closest("[data-open-diff]");
    if (target) {
      openFilePreview(target.dataset.openDiff);
      return;
    }
    const pathNode = event.target.closest(".tool-path");
    if (pathNode && looksLikeWorkspacePath(pathNode.textContent)) openFilePreview(pathNode.textContent.trim());
  });
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => {
    const view = button.dataset.view;
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
    if (view === "tasks") { closePanel(); }
    else if (view === "workspaces") openWorkspacesPanel();
    else if (view === "promo") openPromoPanel();
    else if (view === "activity") openActivityPanel();
    else if (view === "arcade") openArcade().catch((error) => showToast(error.message));
    else closePanel();
  }));
  document.querySelectorAll(".action-chip").forEach((button) => button.addEventListener("click", () => {
    const prompt = state.locale === "zh" ? button.dataset.promptZh : button.dataset.promptEn;
    if (!prompt && !button.dataset.prompt) return;
    $("#promptInput").value = prompt || button.dataset.prompt || "";
    $("#promptInput").focus();
  }));
  $("#brandWorkspaceButton")?.addEventListener("click", openWorkspacesPanel);
  $("#brandSearchButton")?.addEventListener("click", openGlobalSearchPanel);
  $("#helpMenuButton")?.addEventListener("click", openHelpPanel);
  $("#sidebarOpen").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setSidebarCollapsed(false);
    else { $("#sidebar").classList.add("open"); $("#mobileScrim").classList.add("show"); }
  });
  $("#codexMenuToggle")?.addEventListener("click", () => $("#sidebarOpen")?.click());
  $("#sidebarClose").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setSidebarCollapsed(true);
    else { $("#sidebar").classList.remove("open"); $("#mobileScrim").classList.remove("show"); }
  });
  $("#mobileScrim").addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#inspector").classList.remove("open"); $("#mobileScrim").classList.remove("show"); });
  $("#inspectorToggle").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setInspectorCollapsed(!state.inspectorCollapsed);
    else $("#inspector").classList.toggle("open");
  });
  $("#inspectorClose").addEventListener("click", () => {
    if (window.matchMedia?.("(min-width: 1181px)").matches) setInspectorCollapsed(true);
    else $("#inspector").classList.remove("open");
  });
  window.addEventListener("resize", applyPaneLayout);
  $("#panelBody").addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches('.task-row[data-open-task]')) {
      event.preventDefault();
      event.target.click();
    }
  });
  $("#panelBody").addEventListener("change", (event) => {
    if (event.target.id !== "reasoningEffortSelect") return;
    const value = event.target.value;
    if (!["low", "mid", "high", "xhigh", "max", "ultra"].includes(value)) return;
    state.reasoningEffort = value;
    localStorage.setItem("minicc-reasoning", value);
    updateReasoningControl();
    showToast(state.locale === "zh" ? "新的任务将使用 " + t("reasoning." + value) + " 推理强度" : "New tasks will use " + t("reasoning." + value) + " reasoning effort");
  });
  $("#panelBody").addEventListener("click", async (event) => {
    const timelineToggle = event.target.closest("[data-timeline-toggle]");
    if (timelineToggle) {
      setTimelineDetails(timelineToggle.closest(".execution-trail"), timelineToggle.dataset.timelineToggle === "expand");
      event.preventDefault();
      return;
    }
    if (event.target.closest("[data-copy-file]")) {
      event.preventDefault();
      copyFilePreviewContent();
      return;
    }
    const rewind = event.target.closest(".rewind-to-here");
    if (rewind) {
      event.preventDefault();
      rewindToUserIndex(rewind.dataset.userIndex);
      return;
    }
    const restore = event.target.closest("[data-restore-task]");
    if (restore) {
      event.preventDefault();
      restoreTaskSnapshot(restore.dataset.restoreTask);
      return;
    }
    const fileTarget = event.target.closest("[data-open-diff]");
    if (fileTarget) {
      openFilePreview(fileTarget.dataset.openDiff);
      return;
    }
    const pathNode = event.target.closest(".tool-path");
    if (pathNode && looksLikeWorkspacePath(pathNode.textContent)) {
      openFilePreview(pathNode.textContent.trim());
      return;
    }
    const target = event.target.closest("[data-cancel-task], [data-resume-task], [data-open-task], [data-open-detail], [data-select-workspace], [data-remove-worktree], [data-set-locale], [data-switch-session], [data-panel-action]");
    if (!target) return;
    if (target.dataset.openDetail) { openTaskDetail(target.dataset.openDetail); return; }
    if (target.dataset.resumeTask) {
      try {
        const task = await requestJson(`/api/tasks/${encodeURIComponent(target.dataset.resumeTask)}/resume`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        closePanel();
        setSession(task.session_id || state.sessionId);
        const loadingId = addLoadingMessage();
        bindRunningTask(task, loadingId, task.session_id || state.sessionId);
        state.activeTaskId = task.task_id;
        setBusy(true);
        updateTaskDock(task);
        await loadTaskHistory();
        await watchTask(task.task_id);
      } catch (error) { showToast(error.message); }
      finally { if (!taskBySession.has(taskSessionKey(state.sessionId))) state.activeTaskId = null; setBusy(false); }
      return;
    }
    if (target.dataset.openTask) { openTaskInWorkspace(target.dataset.openTask); return; }
    if (target.dataset.selectWorkspace) {
      try {
        showToast(t("workspace.switching"));
        await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: target.dataset.selectWorkspace }) });
        await loadWorkspace();
        closePanel();
        showToast(state.locale === "zh" ? "工作区已切换" : "Workspace switched");
      } catch (error) { showToast(error.message); }
      return;
    }
    if (target.dataset.cancelTask) {
      try { await requestJson(`/api/tasks/${encodeURIComponent(target.dataset.cancelTask)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); openActivityPanel(); }
      catch (error) { showToast(error.message); }
      return;
    }
    if (target.dataset.removeWorktree) {
      try { await requestJson("/api/worktrees/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: target.dataset.removeWorktree }) }); openWorkspacesPanel(); }
      catch (error) { showToast(error.message); }
      return;
    }
    if (target.dataset.setLocale) { setLocale(target.dataset.setLocale); openSettingsPanel(); return; }
    if (target.dataset.switchSession) { setSession(target.dataset.switchSession); closePanel(); return; }
    if (target.dataset.panelAction === "activity") { openActivityPanel(); return; }
    if (target.dataset.panelAction === "new-task") { closePanel(); resetTask(); return; }
    if (target.dataset.panelAction === "clear") { const key = sessionViewKey(state.sessionId); sessionMarkup.delete(key); localStorage.removeItem(key); renderSession(state.sessionId); closePanel(); showToast(state.locale === "zh" ? "当前视图已清空" : "Current view cleared"); return; }
    if (target.dataset.panelAction === "export") { exportChat(); closePanel(); return; }
    if (target.dataset.panelAction === "reload") { loadWorkspace(); closePanel(); return; }
  });
  $("#panelBody").addEventListener("submit", async (event) => {
    if (event.target.id === "batchForm") {
      event.preventDefault();
      const form = event.target;
      const messages = [...form.querySelectorAll("textarea[name=task]")].map((field) => field.value.trim()).filter(Boolean);
      if (messages.length < 2) { showToast(state.locale === "zh" ? "至少填写 2 个子任务" : "Add at least 2 subtasks"); return; }
      try {
        const sharedContext = String(form.elements.namedItem("shared_context")?.value || "").trim();
        const permissions = effectiveTaskPermissions();
        const created = await requestJson("/api/tasks/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages, shared_context: sharedContext, message: state.locale === "zh" ? "并行执行多个独立子任务" : "Run independent subtasks in parallel", session_id: state.sessionId, permission_mode: permissions.mode, allow_changes: permissions.allowChanges, allow_network: permissions.allowNetwork, reasoning_effort: state.reasoningEffort, workspace_path: state.workspacePath }) });
        const task = await requestJson(`/api/tasks/${encodeURIComponent(created.task_id)}`);
        closePanel();
        addUserMessage(task.message || (state.locale === "zh" ? "并行执行多个独立子任务" : "Run independent subtasks in parallel"));
        const loadingId = addLoadingMessage();
        bindRunningTask(task, loadingId, task.session_id || state.sessionId);
        state.activeTaskId = task.task_id;
        setBusy(true);
        updateTaskDock(task);
        await loadTaskHistory();
        await watchTask(task.task_id);
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(false);
      }
      return;
    }
    if (event.target.id === "workspaceSelectForm") {
      event.preventDefault();
      const form = event.target;
      const path = String(form.elements.namedItem("path")?.value || "").trim();
      try {
        showToast(t("workspace.switching"));
        await requestJson("/api/workspace/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
        await loadWorkspace();
        closePanel();
        showToast(state.locale === "zh" ? "工作区已切换" : "Workspace switched");
      } catch (error) { showToast(error.message); }
      return;
    }
    if (event.target.id !== "worktreeForm") return;
    event.preventDefault();
    const form = event.target;
    const nameField = form.elements.namedItem("name");
    const branchField = form.elements.namedItem("branch");
    const name = String(nameField?.value || "").trim();
    const branch = String(branchField?.value || "").trim();
    try {
      await requestJson("/api/worktrees", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, branch: branch || undefined }) });
      showToast(state.locale === "zh" ? "worktree 已创建" : "Worktree created");
      openWorkspacesPanel();
    } catch (error) { showToast(error.message); }
  });
  $("#promptInput").addEventListener("keydown", (event) => {
    if (handleMentionKeydown(event)) return;
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    sendMessage(event);
  });
  $("#promptInput").addEventListener("input", updateMentionPopover);
  // Arrow-key caret moves do not fire "input"; keep the @-token in sync.
  $("#promptInput").addEventListener("keyup", (event) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) updateMentionPopover();
  });
  // preventDefault on mousedown keeps the textarea caret (and its selection)
  // intact while the user clicks a mention option.
  $("#mentionPopover").addEventListener("mousedown", (event) => event.preventDefault());
  $("#mentionPopover").addEventListener("click", (event) => {
    const option = event.target.closest("[data-mention-index]");
    if (option) applyMentionOption(Number(option.dataset.mentionIndex));
  });
  document.addEventListener("click", (event) => {
    if (!mentionState.open) return;
    if (event.target === $("#promptInput") || $("#mentionPopover")?.contains(event.target)) return;
    closeMentionPopover();
  });
  $("#threadList").addEventListener("click", (event) => {
    const item = event.target.closest(".thread-item");
    if (!item) return;
    if (item.dataset.taskId) openTaskInWorkspace(item.dataset.taskId);
    else setSession(item.dataset.session);
  });
  $("#threadSearch").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();
    document.querySelectorAll(".thread-item").forEach((item) => { item.hidden = !item.textContent.toLowerCase().includes(query); });
  });
  const authForm = $("#authForm");
  if (authForm) authForm.addEventListener("submit", submitAuthToken);
}

if (typeof location !== "undefined" && new URLSearchParams(location.search).get("arcade") === "1") {
  document.documentElement.dataset.arcade = "1";
}

document.addEventListener("DOMContentLoaded", () => {
  bindUI();
  updateMode();
  applyFocusMode();
  applyPaneLayout();
  switchInspectorTab(runtime.inspectorTab);
  const resizeViewport = () => {
    document.documentElement.style.setProperty("--app-height", `${window.visualViewport?.height || window.innerHeight}px`);
    document.documentElement.style.setProperty("--viewport-top", `${window.visualViewport?.offsetTop || 0}px`);
  };
  resizeViewport();
  window.visualViewport?.addEventListener("resize", resizeViewport, { passive: true });
  window.visualViewport?.addEventListener("scroll", resizeViewport, { passive: true });
  window.addEventListener("resize", resizeViewport, { passive: true });
  runtime.initialMessageMarkup = $("#messageList").innerHTML;
  setSession(state.sessionId);
  applyLocale();
  refreshIcons();
  prepareStartupSplash();
  loadWorkspace()
    .then((online) => {
      if (online) {
        finishStartupSplash();
        return;
      }
      setStartupSplashError();
      window.setTimeout(finishStartupSplash, 420);
    })
    .catch(() => {
      setStartupSplashError();
      window.setTimeout(finishStartupSplash, 420);
    });
  if (document.documentElement.dataset.arcade === "1") openArcade().catch((error) => showToast(error.message));
  // Keep tasks created in another session or browser tab visible in the sidebar.
  window.setInterval(() => { if (!document.hidden) loadTaskHistory(); }, 5000);
  window.addEventListener("beforeunload", () => persistSessionView());
});

export function exposeWorkbenchGlobals() {
  Object.assign(window, {
    $, $$, t, state, icon, refreshIcons, applyIcons, showToast, openPanel, closePanel, escapeHtml,
    eventTimelineMarkup, assistantMessageMarkup, visibleAgentEvents, addLoadingMessage, bindRunningTask,
    loadWorkspace, openArcade, applyTaskEvent, runningTasks, taskBySession, stopTaskTimer, updateLiveTask, syncLiveEvents,
    addAssistantMessage, updateTaskDock, renderTaskHistory, updateBoundTask, openFilePreview, openHelpPanel, setTimelineDetails,
  });
}
exposeWorkbenchGlobals();
