// M8-T600: the plant and zombie registries have one home each.
//
// web/src/game.js carries whole-registry maps for two entity families:
// every plant (19 ids) and every zombie (19 ids). The maps are hand-keyed;
// a map missing an entity silently resolves to a fallback at its render or
// logic site - ZOMBIE_BODY_COLORS shipped with 16 of 19 (scout, shield and
// storm zombies rendered like walkers for months, guarded only by a
// || ZOMBIE_BODY_COLORS.walker fallback).
//
// This gate pins:
//
// 1. the plant registry is plantCost's keys, and PLANT_TYPES derives from it;
// 2. the full plant maps (plantHealth/plantColor/plantCooldown/the codex
//    maps) carry exactly the plant registry, no more, no less;
// 3. the zombie registry is zombieProfiles' keys;
// 4. the full zombie maps (ZOMBIE_BODY_COLORS, codexZombieNames,
//    codexZombieSkills) carry exactly the zombie registry;
// 5. the deliberate profile-subset maps (plantProfiles) stay inside their
//    registries.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const FILE = "web/src/game.js";
const src = await readFile(FILE, "utf8");

function dictBody(name) {
  const marker = `const ${name} = {`;
  const i = src.indexOf(marker);
  assert(i > -1, `${name} not found`);
  const open = src.indexOf("{", i);
  let depth = 0;
  let pos = open;
  for (; pos < src.length; pos += 1) {
    if (src[pos] === "{") depth += 1;
    else if (src[pos] === "}") {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  return src.slice(open + 1, pos);
}

function topLevelKeys(name) {
  const body = dictBody(name);
  const keys = [];
  let depth = 0;
  let i = 0;
  while (i < body.length) {
    const ch = body[i];
    if (ch === "{") { depth += 1; i += 1; continue; }
    if (ch === "}") { depth -= 1; i += 1; continue; }
    const m = body.slice(i).match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/);
    if (depth === 0 && m) {
      keys.push(m[1]);
      i += m[0].length;
      continue;
    }
    i += 1;
  }
  return keys;
}

const plants = topLevelKeys("plantCost");
const zombies = topLevelKeys("zombieProfiles");
assert.equal(plants.length, 19, `plant registry must carry exactly 19 ids, got ${plants.length}`);
assert.equal(zombies.length, 19, `zombie registry must carry exactly 19 ids, got ${zombies.length}`);

const plantTypesLine = src.match(/const PLANT_TYPES = Object\.keys\(plantCost\)/);
assert(plantTypesLine, "PLANT_TYPES must derive from plantCost (the one home)");

const plantMaps = ["plantHealth", "plantColor", "plantCooldown", "codexPlantNames", "codexPlantIcons", "codexPlantSpecials"];
for (const name of plantMaps) {
  const keys = topLevelKeys(name);
  assert.deepEqual(
    [...keys].sort(),
    [...plants].sort(),
    `${name} must carry exactly the plant registry (drift: ${[...plants].filter((k) => !keys.includes(k))} missing, ${keys.filter((k) => !plants.includes(k))} extra)`,
  );
}

const zombieMaps = ["ZOMBIE_BODY_COLORS", "codexZombieNames", "codexZombieSkills"];
for (const name of zombieMaps) {
  const keys = topLevelKeys(name);
  assert.deepEqual(
    [...keys].sort(),
    [...zombies].sort(),
    `${name} must carry exactly the zombie registry (drift: ${[...zombies].filter((k) => !keys.includes(k))} missing, ${keys.filter((k) => !zombies.includes(k))} extra)`,
  );
}

const profiles = topLevelKeys("plantProfiles");
assert(
  profiles.every((key) => plants.includes(key)),
  `plantProfiles carries ids outside the plant registry: ${profiles.filter((k) => !plants.includes(k))}`,
);

console.log(`M8-T600 ok: plant registry (${plants.length}) and zombie registry (${zombies.length}) each carry exactly their 19 ids; all full maps keyed on them are complete; plantProfiles stays a subset`);
