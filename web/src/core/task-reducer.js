// Pure task protocol reduction: no DOM, storage, transport, or UI imports.
const LIMIT = 2048;
const sequenceOf = (value) => Math.max(0, Number(value) || 0);
const boundedAdd = (previous, value) => {
  const next = new Set(previous || []);
  if (value) next.add(value);
  while (next.size > LIMIT) next.delete(next.values().next().value);
  return next;
};
export function reduceTaskEvent(binding, envelope) {
  if (!binding || !envelope || typeof envelope !== "object") return null;
  const sequence = sequenceOf(envelope.sequence);
  const eventId = String(envelope.event_id || "");
  const itemId = String(envelope.item_id || "");
  if ((sequence && sequence <= sequenceOf(binding.cursor))
    || (sequence && binding.seenSequences?.has(sequence))
    || (eventId && binding.seenEventIds?.has(eventId))
    || (!sequence && !eventId && itemId && binding.seenEventIds?.has(`item:${itemId}`))) return null;
  const payload = envelope.payload && typeof envelope.payload === "object" ? envelope.payload : {};
  const data = { ...(binding.data || {}) };
  switch (envelope.kind) {
    case "timeline": {
      const event = { ...payload, event_id: payload.event_id || eventId, item_id: payload.item_id || itemId, sequence: payload.sequence || sequence };
      const events = [...(data.events || [])];
      const existing = events.findIndex((item) => (event.event_id && item.event_id === event.event_id) || (event.item_id && item.item_id === event.item_id));
      if (existing < 0) events.push(event); else events[existing] = { ...events[existing], ...event };
      data.events = events.slice(-2048);
      break;
    }
    case "stream_delta": {
      const length = sequenceOf(payload.stream_length);
      // A delayed snapshot must never replace a newer stream tail.
      if (length && length < sequenceOf(data.stream_length)) break;
      if (payload.stream_text != null) data.stream_text = String(payload.stream_text || "");
      else if (payload.delta) data.stream_text = `${data.stream_text || ""}${payload.delta}`.slice(-32000);
      data.stream_length = length || Math.max(sequenceOf(data.stream_length), String(data.stream_text || "").length);
      if (payload.phase) data.phase = String(payload.phase);
      break;
    }
    case "state": case "status":
      for (const key of ["status", "phase", "finished_at", "error", "cancel_reason"]) if (payload[key] !== undefined) data[key] = payload[key];
      break;
    case "usage":
      for (const key of ["tokens_used", "metrics"]) if (payload[key] && typeof payload[key] === "object") data[key] = { ...payload[key] };
      if (payload.usage) data.usage_by_turn = [...(data.usage_by_turn || []), { ...payload.usage }].slice(-64);
      break;
    case "context": if (payload.context) data.context = { ...payload.context }; break;
    case "compaction": if (payload.event) data.compaction_events = [...(data.compaction_events || []), { ...payload.event }].slice(-64); break;
    case "result":
      for (const key of ["answer", "error"]) if (payload[key] !== undefined) data[key] = payload[key];
      data.result = { ...(data.result || {}), answer: data.answer, error: data.error };
      break;
  }
  if (payload.state_version != null) data.state_version = Math.max(sequenceOf(data.state_version), sequenceOf(payload.state_version));
  const cursor = Math.max(sequenceOf(binding.cursor), sequence);
  data.event_cursor = cursor;
  let seenEventIds = boundedAdd(binding.seenEventIds, eventId);
  if (!sequence && !eventId && itemId) seenEventIds = boundedAdd(seenEventIds, `item:${itemId}`);
  return { data, cursor, seenSequences: boundedAdd(binding.seenSequences, sequence), seenEventIds };
}
