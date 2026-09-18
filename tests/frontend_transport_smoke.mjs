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
await assert.rejects(requestJson('/timeout', {}, 5), /Request timed out/);
globalThis.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('invalid JSON'); } });
await assert.rejects(requestJson('/invalid-json'), /invalid data/);
globalThis.fetch = async () => ({ ok: true, status: 204 });
assert.deepEqual(await requestJson('/no-content'), {});
globalThis.fetch = async (_url, { signal }) => ({
  ok: true,
  json: () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true })),
});
await assert.rejects(requestJson('/slow-body', {}, 5), /Request timed out/);
console.log('transport passed: Headers, cancellation, already-aborted requests, timeout, invalid JSON, empty response, body timeout');
