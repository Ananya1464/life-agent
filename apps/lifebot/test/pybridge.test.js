const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const path = require('node:path');

const { PyBridge } = require('../lib/pybridge.js');
const env = require('../lib/env.js');

/** A fake child process whose stdout we control. */
function fakeProc() {
  const proc = new EventEmitter();
  proc.stdin = new PassThrough();
  proc.stdout = new PassThrough();
  proc.stderr = new PassThrough();
  proc.kill = () => proc.emit('exit', 0);
  proc.written = [];
  proc.stdin.on('data', (d) => d.toString().split('\n').filter(Boolean).forEach((l) => proc.written.push(JSON.parse(l))));
  return proc;
}

const tick = () => new Promise((r) => setImmediate(r));

test('matches responses to requests by id, even out of order', async () => {
  const proc = fakeProc();
  const bridge = new PyBridge({ python: 'py', cwd: '.', spawnFn: () => proc });
  const a = bridge.request('chat', { m: 1 });
  const b = bridge.request('ping');
  await tick();
  const [ra, rb] = proc.written;
  proc.stdout.write(JSON.stringify({ id: rb.id, result: { ok: true } }) + '\n');
  proc.stdout.write(JSON.stringify({ id: ra.id, result: { reply: 'hi' } }) + '\n');
  assert.deepEqual(await b, { ok: true });
  assert.deepEqual(await a, { reply: 'hi' });
});

test('python errors reject; junk stdout lines are logged, not fatal', async () => {
  const proc = fakeProc();
  const bridge = new PyBridge({ python: 'py', cwd: '.', spawnFn: () => proc });
  const logs = [];
  bridge.on('log', (l) => logs.push(l));
  const p = bridge.request('chat');
  await tick();
  proc.stdout.write('some stray print\n');
  proc.stdout.write(JSON.stringify({ id: proc.written[0].id, error: 'ValueError: nope' }) + '\n');
  await assert.rejects(p, /ValueError: nope/);
  assert.ok(logs.some((l) => l.includes('stray print')));
});

test('requests time out', async () => {
  const bridge = new PyBridge({ python: 'py', cwd: '.', spawnFn: () => fakeProc() });
  await assert.rejects(bridge.request('chat', {}, 30), /timed out/);
});

test('a crash rejects pending requests, reports offline, and restarts on the next request', async () => {
  const procs = [];
  const bridge = new PyBridge({ python: 'py', cwd: '.', spawnFn: () => { const p = fakeProc(); procs.push(p); return p; } });
  const statuses = [];
  bridge.on('status', (s) => statuses.push(s));
  const pending = bridge.request('chat');
  await tick();
  procs[0].emit('exit', 1);
  await assert.rejects(pending, /exited/);
  assert.equal(bridge.online, false);
  await assert.rejects(bridge.request('ping'), /restarting/);              // inside the backoff window
  bridge.lastStart = 0;                                                    // backoff elapsed
  const next = bridge.request('ping');
  await tick();
  assert.equal(procs.length, 2);
  procs[1].stdout.write(JSON.stringify({ id: procs[1].written[0].id, result: { ok: true } }) + '\n');
  assert.deepEqual(await next, { ok: true });
  assert.deepEqual(statuses, ['online', 'offline', 'online']);
});

test('a missing interpreter surfaces as an error, not a crash', async () => {
  const proc = fakeProc();
  const bridge = new PyBridge({ python: 'nope', cwd: '.', spawnFn: () => proc });
  const p = bridge.request('ping');
  await tick();
  proc.emit('error', new Error('spawn nope ENOENT'));
  await assert.rejects(p, /ENOENT/);
});

test('REAL python bridge: ping, an unknown method, and clean stdout', async (t) => {
  const repo = env.findRepoRoot(path.join(__dirname, '..'));
  assert.ok(repo, 'repo root not found');
  const picked = await env.pickPython(env.candidatePythons(repo));
  if (!picked) return t.skip('no suitable python found');
  const bridge = new PyBridge({
    python: picked.python, cwd: repo,
    env: { ...process.env, PYTHONPATH: path.join(repo, 'src'), PYTHONIOENCODING: 'utf-8', NOTION_TOKEN: process.env.NOTION_TOKEN || 'x' },
  });
  try {
    assert.deepEqual(await bridge.request('ping', {}, 20000), { ok: true });
    await assert.rejects(bridge.request('bogus', {}, 20000), /unknown method/);
    assert.deepEqual(await bridge.request('ping', {}, 20000), { ok: true });   // still healthy after an error
  } finally {
    bridge.stop();
  }
});
