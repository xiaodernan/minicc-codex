// Small insertion-ordered caches. Task execution state itself is never evicted.
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
