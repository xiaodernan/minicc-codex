// Reconcile stable timeline nodes, preserving details, selection, and scroll.
const keyOf = (node) => node.nodeType === 1
  ? [node.tagName, node.dataset.agentRound || node.dataset.agentItem || node.dataset.toolEvent || node.dataset.stageCode || ""].join(":")
  : "";
function patchNode(current, next) {
  if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName) { current.replaceWith(next); return next; }
  if (current.nodeType !== 1) { if (current.nodeValue !== next.nodeValue) current.nodeValue = next.nodeValue; return current; }
  for (const attr of [...current.attributes]) if (attr.name !== "open" && !next.hasAttribute(attr.name)) current.removeAttribute(attr.name);
  for (const attr of next.attributes) if (attr.name !== "open" && current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
  patchChildren(current, next);
  return current;
}
function patchChildren(parent, nextParent) {
  const keyed = new Map([...parent.children].map((node) => [keyOf(node), node]).filter(([key]) => key && !key.endsWith(":")));
  let position = parent.firstChild;
  for (const next of [...nextParent.childNodes]) {
    const key = keyOf(next);
    let current = key && !key.endsWith(":") ? keyed.get(key) : position;
    if (!current || (key && !key.endsWith(":") && keyOf(current) !== key)) {
      parent.insertBefore(next, position);
      continue;
    }
    if (current !== position) parent.insertBefore(current, position);
    const updated = patchNode(current, next);
    position = updated.nextSibling;
  }
  while (position) { const next = position.nextSibling; position.remove(); position = next; }
}
export function reconcileTimeline(timeline, markup) {
  const template = timeline.ownerDocument.createElement("template");
  template.innerHTML = markup;
  patchChildren(timeline, template.content);
}
