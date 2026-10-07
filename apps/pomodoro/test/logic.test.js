const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const L = require('../renderer/logic.js');

test('formatMMSS floors, pads and never goes negative', () => {
  assert.equal(L.formatMMSS(25 * 60 * 1000), '25:00');
  assert.equal(L.formatMMSS(61_999), '01:01');
  assert.equal(L.formatMMSS(999), '00:00');
  assert.equal(L.formatMMSS(-5000), '00:00');
});

test('clampMinutes accepts 1-180 and falls back to 25 for junk', () => {
  assert.equal(L.clampMinutes('50'), 50);
  assert.equal(L.clampMinutes('0'), 25);
  assert.equal(L.clampMinutes('-3'), 25);
  assert.equal(L.clampMinutes(''), 25);
  assert.equal(L.clampMinutes('abc'), 25);
  assert.equal(L.clampMinutes('999'), 180);
});

test('remaining time comes from wall-clock timestamps, so a long sleep still ends the session', () => {
  const start = 1_000_000;
  const end = start + 25 * 60 * 1000;
  assert.equal(L.remainingMs(end, start + 60_000), 24 * 60 * 1000);
  assert.ok(L.remainingMs(end, start + 3 * 3600 * 1000) <= 0);     // woke up hours later
  assert.equal(L.formatMMSS(L.remainingMs(end, start + 3 * 3600 * 1000)), '00:00');
});

test('log line keeps the original markdown format', () => {
  const date = new Date(2026, 9, 2, 14, 5);
  assert.equal(
    L.buildLogLine({ date, plannedMinutes: 25, result: 'completed', elapsedMs: 0, task: 'Write report' }),
    '- [x] 2026-10-02 14:05 — 25 min planned, 25:00 elapsed — "Write report" — completed');
  assert.equal(
    L.buildLogLine({ date, plannedMinutes: 25, result: 'abandoned', elapsedMs: 7 * 60 * 1000 + 400, task: '' }),
    '- [ ] 2026-10-02 14:05 — 25 min planned, 07:00 elapsed — "(no task)" — abandoned');
});

const seeded = () => { let x = 7; return () => { x = (x * 16807) % 2147483647; return x / 2147483647; }; };

test('confetti particles are pixel squares from the kawaii palette and burst upward', () => {
  const rand = seeded();
  for (let i = 0; i < 50; i++) {
    const p = L.makeParticle(rand, 266, true);
    assert.ok([4, 6, 8].includes(p.size));
    assert.ok(L.CONFETTI_COLORS.includes(p.color));
    assert.ok(p.vy < 0);                                               // bursts go up first
  }
  assert.ok(L.makeParticle(rand, 266, false).vy > 0);                  // the gentle rain falls down
});

test('particles fall under gravity, eventually leave the window, and are dropped', () => {
  let list = [L.makeParticle(seeded(), 266, true)];
  let steps = 0;
  while (list.length && steps < 2000) { list = L.stepParticles(list, 16, 322); steps += 1; }
  assert.equal(list.length, 0);
  assert.ok(steps < 2000);
});

test('a stalled frame cannot teleport particles', () => {
  const p = { x: 100, y: 0, vx: 0, vy: 0, size: 4, color: '#fff', spin: 0, angle: 0 };
  const [moved] = L.stepParticles([p], 60_000, 10_000);                // one huge dt is clamped to ~64 ms
  assert.ok(moved.y < 5);
});

test('the preload exposes only the narrow API the timer needs', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'preload.js'), 'utf8');
  const exposed = [...src.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1]).sort();
  assert.deepEqual(exposed, ['alarmAttention', 'getLogDestination', 'quit', 'selectLogDestination', 'windowShake', 'writeLog']);
  assert.ok(!/require\(['"](fs|child_process)['"]\)/.test(src));       // no filesystem/shell handed to the renderer
});

test('main process keeps the renderer sandboxed and the alarm able to sound unfocused', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');
  for (const needle of ['contextIsolation: true', 'nodeIntegration: false', 'sandbox: true',
    "autoplayPolicy: 'no-user-gesture-required'", 'backgroundThrottling: false', "setAlwaysOnTop(true, 'floating')"]) {
    assert.ok(src.includes(needle), `missing: ${needle}`);
  }
});
