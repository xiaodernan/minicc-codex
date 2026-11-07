// Small insertion-ordered caches. Task execution state itself is never evicted.

//: The one event-retention cap for a bound/binding surface: how many
//: event-identity keys are remembered for dedup (``task-reducer.js``'s
//: seen-sets, ``state.js``'s panels-side tracker) and how many recent
//: timeline events are kept rendered (``task-reducer.js``'s slice).
//: Previously spelled as a bare literal in two modules plus a named
//: constant in a third.
export const MAX_SEEN_EVENT_KEYS = 2048;

export class BoundedMap extends Map {
  constructor(limit) { super(); this.limit = limit; }
  set(key, value) {
    if (this.has(key)) this.delete(key);
    super.set(key, value);
    while (this.size > this.limit) this.delete(this.keys().next().value);
    return this;
  }
}
export class BoundedSet extends Set {
  constructor(limit) { super(); this.limit = limit; }
  add(value) {
    if (this.has(value)) this.delete(value);
    super.add(value);
    while (this.size > this.limit) this.delete(this.values().next().value);
    return this;
  }
}
