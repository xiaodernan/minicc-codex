import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Exercise transport boundaries without a DOM or browser. The state dependency
// is replaced by a fixture, while the real transport implementation is loaded.
const source = (await readFile('web/src/core/transport.js', 'utf8')).replace(
  'import { authHeaders, state } from "./state.js";',
  'const authHeaders = () => ({ Authorization: "Bearer fixture" }); const state = { locale: "en" };',
);
const { requestJson } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
globalThis.window = { setTimeout, clearTimeout, dispatchEvent() {} };
globalThis.fetch = async (_url, options) => {
  assert.equal(options.headers.get('authorization'), 'Bearer fixture');
  assert.equal(options.headers.get('x-client'), 'test');
  return { ok: true, json: async () => ({ ok: true }) };
};
assert.deepEqual(await requestJson('/ok', { headers: new Headers({ 'X-Client': 'test' }) }), { ok: true });

globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
  const cancel = () => reject(signal.reason || new DOMException('Aborted', 'AbortError'));
  if (signal.aborted) cancel(); else signal.addEventListener('abort', cancel, { once: true });
});
const controller = new AbortController();
const request = requestJson('/cancelled', { signal: controller.signal });
controller.abort();
await assert.rejects(request, { name: 'AbortError' });
await assert.rejects(requestJson('/already-cancelled', { signal: controller.signal }), { name: 'AbortError' });
// M8-T1314: a timeout carries a machine-readable code so panels can tell
// "slow" from "unreachable". The localized message stays byte-identical.
await assert.rejects(
  requestJson('/timeout', {}, 5),
  (error) => error instanceof Error && error.code === 'timeout' && /Request timed out/.test(error.message),
);
await assert.rejects(requestJson('/timeout-msg', {}, 5), /Request timed out/);
// M8-T1315: HTTP failures carry a class code while keeping the exact message.
globalThis.fetch = async () => ({ ok: false, status: 503, statusText: 'Unavailable', json: async () => ({ error: 'backend down' }) });
await assert.rejects(
  requestJson('/server-error'),
  (error) => error instanceof Error && error.code === 'server-error' && error.status === 503 && error.message === 'backend down',
);
globalThis.fetch = async () => ({ ok: false, status: 403, statusText: 'Forbidden', json: async () => ({}) });
await assert.rejects(
  requestJson('/http-error'),
  (error) => error instanceof Error && error.code === 'http-error' && error.status === 403 && error.message === '403 Forbidden',
);
// A bare fetch rejection (TypeError) is a real network outage. An AbortError
// cancellation must NOT be relabeled as one — it already carries a name.
globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
await assert.rejects(requestJson('/network'), (error) => error.code === 'network');
globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
  const cancel = () => reject(signal.reason || new DOMException('Aborted', 'AbortError'));
  if (signal.aborted) cancel(); else signal.addEventListener('abort', cancel, { once: true });
});
const abortCtrl = new AbortController();
const aborting = requestJson('/cancel-not-network', { signal: abortCtrl.signal });
abortCtrl.abort();
await assert.rejects(aborting, (error) => error.name === 'AbortError' && error.code !== 'network');

globalThis.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('invalid JSON'); } });
await assert.rejects(requestJson('/invalid-json'), /invalid data/);
globalThis.fetch = async () => ({ ok: true, status: 204 });
assert.deepEqual(await requestJson('/no-content'), {});
globalThis.fetch = async (_url, { signal }) => ({
  ok: true,
  json: () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true })),
});
// Body-read timeouts must carry the code too — same helper, same contract.
await assert.rejects(
  requestJson('/slow-body', {}, 5),
  (error) => error instanceof Error && error.code === 'timeout',
);
console.log('transport passed: Headers, cancellation, already-aborted requests, timeout (code=timeout), invalid JSON, empty response, body timeout');
