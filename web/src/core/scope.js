// Async view work belongs to the workspace/session that started it.
import { runtime, state } from "./state.js";

export function captureViewScope() {
  return { workspacePath: state.workspacePath, sessionId: state.sessionId, workspaceVersion: runtime.workspaceVersion };
}

export function isWorkspaceScopeCurrent(scope) {
  return scope.workspacePath === state.workspacePath && scope.workspaceVersion === runtime.workspaceVersion;
}

export function isViewScopeCurrent(scope) {
  return isWorkspaceScopeCurrent(scope) && scope.sessionId === state.sessionId;
}
