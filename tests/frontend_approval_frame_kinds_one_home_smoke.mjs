// M8-T611: the approval frame kinds have one home on each face.
//
// The server emits "approval_request" / "approval_resolved" frames
// (minicc/audit.py owns the kind strings; minicc/web.py emits them). The web
// consumer in approvals.js must use named constants pinned to the Python home,
// not bare literals.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const HOME = path.join("web", "src", "core", "approvals.js");
const PYHOME = path.join("minicc", "audit.py");

const js = await readFile(HOME, "utf8");
const req = js.match(/export const APPROVAL_FRAME_REQUEST_KIND\s*=\s*"([^"]+)"\s*;/);
const res = js.match(/export const APPROVAL_FRAME_RESOLVED_KIND\s*=\s*"([^"]+)"\s*;/);
assert(req, "approvals.js must export APPROVAL_FRAME_REQUEST_KIND");
assert(res, "approvals.js must export APPROVAL_FRAME_RESOLVED_KIND");

const py = await readFile(PYHOME, "utf8");
const pyReq = py.match(/APPROVAL_FRAME_REQUEST_KIND\s*=\s*"([^"]+)"\s*/);
const pyRes = py.match(/APPROVAL_FRAME_RESOLVED_KIND\s*=\s*"([^"]+)"\s*/);
assert(pyReq, "minicc/audit.py must define APPROVAL_FRAME_REQUEST_KIND");
assert(pyRes, "minicc/audit.py must define APPROVAL_FRAME_RESOLVED_KIND");

assert.equal(req[1], pyReq[1], `request kind disagrees: JS=${req[1]} Python=${pyReq[1]}`);
assert.equal(res[1], pyRes[1], `resolved kind disagrees: JS=${res[1]} Python=${pyRes[1]}`);

const code = js
  .replace(/\/\/[^\n]*/g, "")
  .replace(/"[^"\n]*"/g, "")
  .split("\n")
  .filter((line) => !/APPROVAL_FRAME_(REQUEST|RESOLVED)_KIND\s*=\s*/.test(line))
  .join("\n");
for (const kind of ["approval_request", "approval_resolved"]) {
  assert(!code.includes(kind), `bare ${kind} literal reappeared in approvals.js outside its constant`);
}

console.log("M8-T611 ok: approval frame kinds have one home on each face and agree");
