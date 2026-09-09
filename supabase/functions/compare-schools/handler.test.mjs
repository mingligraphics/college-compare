import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHandler } from './handler.mjs';

const sql = readFileSync(new URL('../../migrations/20260908000000_create_private_schools.sql', import.meta.url), 'utf8');
const fields = [...sql.split('returns table (')[1].split(')\nlanguage')[0].matchAll(/^  (\w+) /gm)].map(m => m[1]);
const row = id => ({ ...Object.fromEntries(fields.map(f => [f, null])), school_id: id });
const records = [{ ...row('nyu'), tuition: 68576, first_year_enrollment: 5723, internal: 'must not leak' }, row('bu')];
const env = { SUPABASE_URL: 'https://example.invalid', SUPABASE_SECRET_KEYS: JSON.stringify({ default: 'fake-test-key', other: 'unused-key' }) };
const request = (body, method = 'POST', origin = 'https://mingligraphics.github.io') => new Request('http://localhost', {
  method, headers: { 'content-type': 'application/json', origin },
  ...(method === 'POST' ? { body: typeof body === 'string' ? body : JSON.stringify(body) } : {}),
});
const valid = { schoolA: 'nyu', schoolB: 'bu' };

 test('NYU + BU success, RPC arguments, allowlist, and CORS', async () => {
  const handler = createHandler({ getEnv: n => env[n], fetchImpl: async (url, options) => {
    assert.equal(url, 'https://example.invalid/rest/v1/rpc/get_school_comparison');
    assert.deepEqual(JSON.parse(options.body), { p_school_id_a: 'nyu', p_school_id_b: 'bu' });
    assert.equal(options.headers.apikey, 'fake-test-key');
    assert.equal(new Headers(options.headers).has('authorization'), false);
    return Response.json(records);
  }});
  const res = await handler(request(valid));
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('access-control-allow-origin'), 'https://mingligraphics.github.io');
  const data = await res.json();
  assert.deepEqual(data.map(r => r.school_id), ['nyu', 'bu']);
  assert.equal(data[0].first_year_enrollment, 5723);
  assert.equal(data[1].tuition, null);
  assert.equal(Object.hasOwn(data[0], 'internal'), false);
  assert.equal(JSON.stringify(data).includes('fake-test-key'), false);
});
for (const [name, body] of [
  ['duplicate', { schoolA: 'nyu', schoolB: 'nyu' }],
  ['blank', { schoolA: ' ', schoolB: 'bu' }],
  ['malformed JSON', '{'], ['null', null], ['array', []],
  ['non-string', { schoolA: 3, schoolB: 'bu' }],
  ['extra key', { ...valid, extra: true }], ['missing key', { schoolA: 'nyu' }],
  ['oversized', ' '.repeat(1025)],
]) test(name, async () => {
  const handler = createHandler({ getEnv: n => env[n], fetchImpl: () => { throw new Error('Must not call RPC'); } });
  assert.equal((await handler(request(body))).status, 400);
});
for (const [name, status, payload, expected] of [
  ['unknown school', 400, { code: 'P0002' }, 404],
  ['RPC invalid input', 400, { code: '22023' }, 400],
  ['database failure', 500, { message: 'sensitive', code: 'XX000' }, 500],
  ['partial result', 200, [records[0]], 500],
  ['wrong order', 200, [...records].reverse(), 500],
  ['missing columns', 200, [{school_id: 'nyu'}, {school_id: 'bu'}], 500],
]) test(name, async () => {
  const handler = createHandler({ getEnv: n => env[n], fetchImpl: async () => Response.json(payload, { status }) });
  const res = await handler(request(valid));
  assert.equal(res.status, expected);
  assert.equal((await res.text()).includes('sensitive'), false);
});
test('GET 405; preflight 204; disallowed origin has no CORS grant', async () => {
  const handler = createHandler({ getEnv: () => undefined });
  assert.equal((await handler(request(null, 'GET'))).status, 405);
  assert.equal((await handler(request(null, 'OPTIONS'))).status, 204);
  assert.equal((await handler(request(null, 'OPTIONS', 'https://other.invalid'))).headers.has('access-control-allow-origin'), false);
});
test('network failure is sanitized', async () => {
  const handler = createHandler({ getEnv: n => env[n], fetchImpl: async () => { throw new Error('fake-test-key'); } });
  const res = await handler(request(valid));
  assert.equal(res.status, 500);
  assert.equal((await res.text()).includes('fake-test-key'), false);
});
test('missing environment produces 500', async () => {
  assert.equal((await createHandler({ getEnv: () => undefined })(request(valid))).status, 500);
});

for (const [name, secretKeys] of [
  ['missing secret keys', undefined], ['malformed secret JSON', '{'],
  ['null secret map', 'null'], ['array secret map', '[]'],
  ['string secret map', '"fake-test-key"'], ['missing default key', '{}'],
  ['non-string default key', '{"default":123}'],
  ['blank default key', '{"default":"  "}'],
]) test(name, async () => {
  let calls = 0;
  const handler = createHandler({
    getEnv: n => n === 'SUPABASE_SECRET_KEYS' ? secretKeys : env[n],
    fetchImpl: async () => { calls++; return Response.json(records); },
  });
  const res = await handler(request(valid));
  assert.equal(res.status, 500);
  assert.deepEqual(await res.json(), { error: 'Server configuration error' });
  assert.equal(calls, 0);
});
