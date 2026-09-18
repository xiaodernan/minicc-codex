// Shared keyboard/focus lifecycle for workbench dialogs. No application imports.
const dialogs = [];
const background = new Map();
const focusable = 'button, input, textarea, select, a[href], summary, [tabindex]';
let listening = false;

function controls(modal) {
  return [...modal.querySelectorAll(focusable)].filter((node) => !node.disabled
    && node.tabIndex >= 0 && !node.closest('[hidden], [inert]') && node.getClientRects().length);
}

function focusDialog(entry) {
  const preferred = entry.initialFocus && entry.modal.querySelector(entry.initialFocus);
  const target = preferred || controls(entry.modal)[0] || entry.modal.querySelector('[role="dialog"]');
  if (target) {
    if (target.tabIndex < 0) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  }
}

function syncBackground() {
  for (const [node, inert] of background) node.inert = inert;
  background.clear();
  const entry = dialogs.at(-1);
  if (!entry) return;
  for (const node of document.body.children) {
    if (node.contains(entry.modal) || ['SCRIPT', 'STYLE', 'LINK'].includes(node.tagName)) continue;
    background.set(node, node.inert);
    node.inert = true;
  }
}

export function activateDialog(modal, options = {}) {
  let entry = dialogs.find((item) => item.modal === modal);
  if (!entry) {
    entry = { modal, previousFocus: document.activeElement, ...options };
    dialogs.push(entry);
  } else Object.assign(entry, options);
  if (!listening) {
    listening = true;
    document.addEventListener('keydown', (event) => {
      const active = dialogs.at(-1);
      if (!active) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        active.onEscape?.();
      } else if (event.key === 'Tab') {
        const nodes = controls(active.modal);
        const index = nodes.indexOf(document.activeElement);
        if (!nodes.length || index < 0 || (event.shiftKey && index === 0) || (!event.shiftKey && index === nodes.length - 1)) {
          event.preventDefault();
          if (!nodes.length) focusDialog(active);
          else nodes[event.shiftKey ? nodes.length - 1 : 0].focus({ preventScroll: true });
        }
      }
    }, true);
    document.addEventListener('focusin', (event) => {
      const active = dialogs.at(-1);
      if (active && !active.modal.contains(event.target)) focusDialog(active);
    });
  }
  syncBackground();
  if (dialogs.at(-1) === entry && !modal.contains(document.activeElement)) focusDialog(entry);
  // Opening visibility transitions and inert changes may defer focusability
  // until layout. Retry within the transition without stealing user focus.
  requestAnimationFrame(() => {
    if (dialogs.at(-1) === entry && !modal.contains(document.activeElement)) focusDialog(entry);
  });
  window.setTimeout(() => {
    if (dialogs.at(-1) === entry && !modal.contains(document.activeElement)) focusDialog(entry);
  }, 220);
}

export function deactivateDialog(modal) {
  const index = dialogs.findIndex((item) => item.modal === modal);
  if (index < 0) return;
  const [entry] = dialogs.splice(index, 1);
  syncBackground();
  if (index !== dialogs.length) return;
  const active = dialogs.at(-1);
  if (entry.previousFocus?.isConnected && !entry.previousFocus.closest('[inert]')) entry.previousFocus.focus({ preventScroll: true });
  else if (active) focusDialog(active);
}
