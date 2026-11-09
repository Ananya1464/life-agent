const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const R = require('../lib/reminders.js');
const P = require('../lib/pomodoro.js');
const T = require('../lib/tasks.js');
const { createStore } = require('../lib/store.js');
const ntfy = require('../lib/ntfy.js');
const env = require('../lib/env.js');

const at = (s) => new Date(s);
const NOW = at('2026-10-01T21:00:00+05:30');

// ------------------------------------------------------------------ reminders
test('make validates text, repeat, time and the past', () => {
  const r = R.make({ text: ' Stretch ', at: '2026-10-02T08:00:00+05:30', repeat: 'daily' }, NOW);
  assert.equal(r.text, 'Stretch');
  assert.equal(r.status, 'pending');
  assert.throws(() => R.make({ text: '', at: '2026-10-02T08:00' }, NOW), /required/);
  assert.throws(() => R.make({ text: 'x', at: 'nonsense' }, NOW), /valid date/);
  assert.throws(() => R.make({ text: 'x', at: '2026-09-01T08:00:00+05:30' }, NOW), /past/);
  assert.throws(() => R.make({ text: 'x', at: '2026-10-02T08:00:00+05:30', repeat: 'monthly' }, NOW), /Repeat/);
  assert.throws(() => R.make({ text: 'x'.repeat(201), at: '2026-10-02T08:00:00+05:30' }, NOW), /too long/);
});

test('due only returns pending reminders whose time has come', () => {
  const list = [
    { id: 'a', at: '2026-10-01T20:59:00+05:30', status: 'pending', repeat: 'none' },
    { id: 'b', at: '2026-10-01T21:30:00+05:30', status: 'pending', repeat: 'none' },
    { id: 'c', at: '2026-10-01T20:00:00+05:30', status: 'done', repeat: 'none' },
    { id: 'd', at: '2026-10-01T20:00:00+05:30', status: 'fired', repeat: 'none' },
  ];
  assert.deepEqual(R.due(list, NOW).map((r) => r.id), ['a']);
});

test('one-off fires once and waits for acknowledgement; completing marks it done', () => {
  const r = { id: 'a', text: 't', at: '2026-10-01T20:59:00+05:30', status: 'pending', repeat: 'none' };
  const fired = R.fire(r, NOW);
  assert.equal(fired.status, 'fired');
  assert.deepEqual(R.due([fired], NOW), []);          // not re-fired every tick
  assert.equal(R.complete(fired, NOW).status, 'done');
});

test('daily reminders advance past now, keeping wall-clock time, even after days offline', () => {
  const r = { id: 'a', text: 't', at: '2026-09-25T09:00:00+05:30', status: 'pending', repeat: 'daily' };
  const fired = R.fire(r, NOW);
  assert.equal(fired.status, 'pending');
  const next = R.parseAt(fired.at);
  assert.ok(next > NOW);
  assert.equal(next.getHours(), at('2026-09-25T09:00:00+05:30').getHours());
  assert.ok(next - NOW <= 24 * 3600 * 1000);
});

test('weekday reminders skip weekends', () => {
  const friday = at('2026-10-02T09:00:00+05:30');                        // a Friday
  const next = R.nextOccurrence(friday, 'weekdays', friday);
  assert.equal(next.getDay(), 1);                                        // Monday
  assert.equal(R.nextOccurrence(friday, 'none', friday), null);
});

test('snooze moves a reminder forward and clamps silly values', () => {
  const r = { id: 'a', text: 't', at: '2026-10-01T20:59:00+05:30', status: 'fired', repeat: 'none' };
  const s = R.snooze(r, 10, NOW);
  assert.equal(s.status, 'pending');
  assert.equal(R.parseAt(s.at) - NOW, 10 * 60000);
  assert.equal(R.parseAt(R.snooze(r, 0, NOW).at) - NOW, 10 * 60000);    // missing/zero -> default
  assert.equal(R.parseAt(R.snooze(r, 'abc', NOW).at) - NOW, 10 * 60000);
  assert.equal(R.parseAt(R.snooze(r, -5, NOW).at) - NOW, 60000);        // negative -> 1 minute minimum
  assert.equal(R.parseAt(R.snooze(r, 99999, NOW).at) - NOW, 24 * 3600000);
});

// ------------------------------------------------------------------ pomodoro
const t0 = 1_000_000;
const TASK = { id: 't1', text: 'Write report' };

test('start emits started and counts down from timestamps', () => {
  const { state, events } = P.start(P.idle(), TASK, t0);
  assert.deepEqual(events.map((e) => e.type), ['started']);
  assert.equal(P.remainingMs(state, t0 + 60000), 24 * 60000);
  assert.equal(P.format(P.remainingMs(state, t0)), '25:00');
});

test('focus completes into a break, then the break ends', () => {
  let { state } = P.start(P.idle(), TASK, t0);
  let r = P.tick(state, t0 + 24 * 60000);
  assert.deepEqual(r.events, []);
  r = P.tick(state, t0 + 25 * 60000);
  assert.equal(r.events[0].type, 'completed');
  assert.equal(r.events[0].durationSec, 1500);
  assert.equal(r.state.phase, 'break');
  const end = P.tick(r.state, t0 + 25 * 60000 + 5 * 60000);
  assert.equal(end.events[0].type, 'break_done');
  assert.equal(end.state.phase, 'idle');
});

test('a long sleep still yields exactly one completed event', () => {
  const { state } = P.start(P.idle(), TASK, t0);
  const r = P.tick(state, t0 + 3 * 3600000);
  assert.equal(r.events.filter((e) => e.type === 'completed').length, 1);
  // the break starts at wake-up time, so nothing else fires immediately (and no second completion)
  assert.deepEqual(P.tick(r.state, t0 + 3 * 3600000).events, []);
  assert.equal(r.state.phase, 'break');
});

test('pause freezes time and resume continues', () => {
  let { state } = P.start(P.idle(), TASK, t0);
  state = P.pause(state, t0 + 10 * 60000).state;
  assert.equal(P.remainingMs(state, t0 + 99 * 60000), 15 * 60000);
  assert.deepEqual(P.tick(state, t0 + 99 * 60000).events, []);            // paused never completes
  state = P.resume(state, t0 + 20 * 60000).state;
  assert.equal(P.remainingMs(state, t0 + 25 * 60000), 10 * 60000);
});

test('stop abandons a focus run with elapsed seconds, but a break just ends', () => {
  const { state } = P.start(P.idle(), TASK, t0);
  const stopped = P.stop(state, t0 + 7 * 60000 + 400);
  assert.equal(stopped.events[0].type, 'abandoned');
  assert.equal(stopped.events[0].durationSec, 420);
  assert.equal(stopped.state.phase, 'idle');
  const brk = P.tick(state, t0 + 25 * 60000).state;
  assert.deepEqual(P.stop(brk, t0 + 26 * 60000).events, []);
});

test('starting a new task abandons the current run first and gives each run its own id', () => {
  const first = P.start(P.idle(), TASK, t0);
  const second = P.start(first.state, { id: 't2', text: 'Other' }, t0 + 5 * 60000);
  assert.deepEqual(second.events.map((e) => e.type), ['abandoned', 'started']);
  assert.equal(second.events[0].runId, first.state.runId);
  assert.notEqual(second.state.runId, first.state.runId);
});

test('custom durations are respected', () => {
  const { state } = P.start(P.idle(), TASK, t0, { focusMin: 50 });
  assert.equal(P.remainingMs(state, t0), 50 * 60000);
});

// ------------------------------------------------------------------ tasks
const MD = '## Today\n\n- [ ] Write report\n- [x] Email prof (done 2026-10-01T09:00)\n- [ ] Write report\n';

test('listTasks gives stable ids and numbers duplicates', () => {
  const tasks = T.listTasks(MD, '2026-10-01');
  assert.deepEqual(tasks.map((t) => t.id), [
    '2026-10-01:lifebot:write-report', '2026-10-01:lifebot:email-prof', '2026-10-01:lifebot:write-report#2']);
  assert.equal(tasks[1].checked, true);
  assert.equal(tasks[1].text, 'Email prof');
});

test('addTask appends after the last task, or creates a heading when empty', () => {
  assert.match(T.addTask(MD, 'New thing'), /- \[ \] Write report\n- \[ \] New thing\n$/);
  assert.equal(T.addTask('', ' First  task '), '## Today\n\n- [ ] First task\n');
  assert.throws(() => T.addTask(MD, '   '), /required/);
});

test('toggle round-trips through the markdown with a done timestamp', () => {
  const checked = T.toggle(MD, 2, true, '2026-10-01T10:00');
  assert.match(checked, /- \[x\] Write report \(done 2026-10-01T10:00\)/);
  assert.match(T.toggle(checked, 2, false), /- \[ \] Write report\n/);
});

// ------------------------------------------------------------------ store
test('store persists atomically and survives a corrupt file', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lifebot-'));
  const file = path.join(dir, 'data.json');
  const s = createStore(file, { reminders: [], settings: { a: 1 } });
  s.update((d) => { d.reminders.push({ id: 'x' }); });
  assert.equal(createStore(file, { reminders: [], settings: {} }).get().reminders[0].id, 'x');
  assert.equal(fs.existsSync(`${file}.tmp`), false);
  fs.writeFileSync(file, '{ not json');
  const fresh = createStore(file, { reminders: [], settings: {} });
  assert.deepEqual(fresh.get().reminders, []);
  assert.ok(fs.readdirSync(dir).some((f) => f.includes('corrupt')));      // moved aside, not lost
});

// ------------------------------------------------------------------ ntfy
test('ntfy validates topics and strips non-ASCII from headers', async () => {
  assert.equal(ntfy.isValidTopic('my-topic_1'), true);
  for (const bad of ['', 'a/b', 'x', '../etc', null]) assert.equal(ntfy.isValidTopic(bad), false);
  assert.equal(ntfy.safeHeader('Focus done ✅ café'), 'Focus done  caf');
  assert.deepEqual(await ntfy.send('bad topic', 't', 'b'), { ok: false, error: 'invalid or missing ntfy topic' });
});

test('ntfy send reports http status and network errors without throwing', async () => {
  const { EventEmitter } = require('node:events');
  const fake = (status) => (opts, cb) => {
    const req = new EventEmitter();
    req.end = () => { const res = new EventEmitter(); res.statusCode = status; res.resume = () => {}; cb(res); };
    req.destroy = () => {};
    return req;
  };
  assert.deepEqual(await ntfy.send('abc123', 'Title', 'body', fake(200)), { ok: true });
  assert.match((await ntfy.send('abc123', 'Title', 'body', fake(429))).error, /429/);
  const failing = () => { const req = new EventEmitter(); req.end = () => req.emit('error', new Error('offline')); return req; };
  assert.deepEqual(await ntfy.send('abc123', 't', 'b', failing), { ok: false, error: 'offline' });
});

// ------------------------------------------------------------------ env
test('parseDotEnv handles comments, quotes and blanks', () => {
  const out = env.parseDotEnv('# c\nNTFY_TOPIC="my-topic"\n\nA = b=c\nBAD LINE\n');
  assert.deepEqual(out, { NTFY_TOPIC: 'my-topic', A: 'b=c' });
});

test('findRepoRoot walks up to the folder containing src/life_agent', () => {
  const exists = (p) => p.replace(/\\/g, '/').endsWith('/repo/src/life_agent/__init__.py');
  assert.equal(env.findRepoRoot(path.resolve('/repo/apps/lifebot'), exists), path.resolve('/repo'));
  assert.equal(env.findRepoRoot(path.resolve('/elsewhere'), () => false), null);
});

test('pickPython prefers the interpreter with the most modules and requires the core ones', async () => {
  const probes = {
    a: { ok: true, modules: ['requests', 'zoneinfo', 'google.genai'] },
    b: { ok: true, modules: ['requests', 'zoneinfo', 'google.genai', 'openai'] },
    c: { ok: true, modules: ['openai'] },
    d: { ok: false },
  };
  const probe = async (p) => probes[p];
  assert.equal((await env.pickPython(['d', 'c', 'a', 'b'], probe)).python, 'b');
  assert.deepEqual((await env.pickPython(['a'], probe)).missing, ['openai']);
  assert.equal(await env.pickPython(['c', 'd'], probe), null);
});


// ------------------------------------------------------------------ adjust the running timer
test('adjust adds or removes minutes from the running session', () => {
  const { state } = P.start(P.idle(), TASK, t0);
  const more = P.adjust(state, 5 * 60000, t0 + 60000);
  assert.equal(P.remainingMs(more.state, t0 + 60000), 29 * 60000);          // 25 + 5 - 1 elapsed
  const less = P.adjust(more.state, -10 * 60000, t0 + 60000);
  assert.equal(P.remainingMs(less.state, t0 + 60000), 19 * 60000);
  assert.deepEqual(more.events, []);
});

test('adjust never leaves less than a minute, never exceeds three hours, and ignores non-focus phases', () => {
  const { state } = P.start(P.idle(), TASK, t0);
  const floor = P.adjust(state, -999 * 60000, t0 + 20 * 60000);
  assert.equal(P.remainingMs(floor.state, t0 + 20 * 60000), 60000);
  const cap = P.adjust(state, 999 * 60000, t0);
  assert.equal(cap.state.durationMs, P.MAX_TOTAL_MS);
  assert.equal(P.adjust(P.idle(), 5 * 60000, t0).state.phase, 'idle');
  const brk = P.tick(state, t0 + 25 * 60000).state;
  assert.equal(P.adjust(brk, 5 * 60000, t0 + 25 * 60000).state.durationMs, brk.durationMs);
});

test('adjust while paused keeps the elapsed time and the longer session completes later', () => {
  let { state } = P.start(P.idle(), TASK, t0);
  state = P.pause(state, t0 + 10 * 60000).state;
  state = P.adjust(state, 5 * 60000, t0 + 99 * 60000).state;               // adjusting does not consume paused time
  assert.equal(P.remainingMs(state, t0 + 99 * 60000), 20 * 60000);
  state = P.resume(state, t0 + 20 * 60000).state;
  assert.deepEqual(P.tick(state, t0 + 39 * 60000).events, []);
  const done = P.tick(state, t0 + 40 * 60000);
  assert.equal(done.events[0].type, 'completed');
  assert.equal(done.events[0].durationSec, 30 * 60);                       // reports the adjusted length
});
