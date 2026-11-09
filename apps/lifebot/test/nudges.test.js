'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { decide, recordOutcome, WORDS } = require('../lib/nudges.js');

const H = 3600000, M = 60000;
const at = (h, m = 0, d = 5) => Date.UTC(2026, 9, d, h, m);
const T = (id, text, o = {}) => ({ id, text, checked: false, isToday: true, carried: false, date: '2026-10-05', ...o });
const mk = (o = {}) => ({
  now: at(10), tzOffsetMin: 0, settings: { nudges: true }, tasks: [T('a', 'Write report'), T('b', 'Email Sam')],
  currentTaskId: null, pomo: { phase: 'idle', running: false }, lastFocusEndedAt: null,
  log: { sent: [] }, snoozedUntil: null, ...o,
});
const sentAt = (kind, time, outcome = null, taskId = null) => ({ kind, at: time, taskId, outcome });

test('morning_pick: first prompt, one task, one action (R1, R5)', () => {
  const n = decide(mk());
  assert.equal(n.kind, 'morning_pick');
  assert.equal(n.action, 'pick');
  assert.equal(n.taskId, 'a');
  assert.ok(n.body.includes('Write report'));
  assert.ok(!n.body.includes('Email Sam'), 'never lists other tasks');
  assert.ok(n.title && n.body);
});

test('R5: prefers currentTaskId, else first open today task, ignores carried/checked', () => {
  assert.equal(decide(mk({ currentTaskId: 'b' })).taskId, 'b');
  const tasks = [T('x', 'Done', { checked: true }), T('c', 'Old', { carried: true, isToday: true }), T('d', 'Real one')];
  assert.equal(decide(mk({ tasks })).taskId, 'd');
  const onlyCarried = [T('c', 'Old', { carried: true, isToday: false, date: '2026-10-01' })];
  assert.equal(decide(mk({ tasks: onlyCarried })).kind, 'carried_over');
  // chosen task that is checked is not used
  assert.equal(decide(mk({ currentTaskId: 'x', tasks: [T('x', 'Done', { checked: true }), T('d', 'Real')] })).taskId, 'd');
});

test('idle_start: offers 5 minutes on target after morning prompt', () => {
  const log = { sent: [sentAt('morning_pick', at(9), 'snoozed', 'a')] };
  const n = decide(mk({ now: at(13), log, lastFocusEndedAt: at(10) }));
  assert.equal(n.kind, 'idle_start');
  assert.equal(n.action, 'start');
  assert.equal(n.minutes, 5);
  assert.equal(n.taskId, 'a');
  // recent focus => not idle yet
  assert.equal(decide(mk({ now: at(13), log, lastFocusEndedAt: at(12) })), null);
});

test('carried_over: one task, once a day, oldest/least-nudged first', () => {
  const tasks = [T('n', 'New', { isToday: false }), T('c1', 'Old one', { carried: true, isToday: false, date: '2026-10-01' }),
    T('c2', 'Older', { carried: true, isToday: false, date: '2026-09-28' })];
  const log = { sent: [sentAt('morning_pick', at(8, 30), 'dismissed')] };
  const n = decide(mk({ now: at(11), tasks, log }));
  assert.equal(n.kind, 'carried_over');
  assert.equal(n.action, 'triage');
  assert.equal(n.taskId, 'c2');
  assert.ok(!n.body.includes('Old one'));
  // already sent today => no second carried_over; falls through to nothing/idle only
  const log2 = { sent: [sentAt('carried_over', at(10), 'dismissed', 'c2')] };
  const n2 = decide(mk({ now: at(13), tasks, log: log2 }));
  assert.notEqual(n2 && n2.kind, 'carried_over');
  // next day rotates to the other task
  const n3 = decide(mk({ now: at(11, 0, 6), tasks, log: log2 }));
  assert.equal(n3.kind === 'carried_over' ? n3.taskId : 'c1', 'c1');
});

test('wrapup: evening only if something was done or started', () => {
  const log = { sent: [sentAt('morning_pick', at(9), 'started')] };
  const none = mk({ now: at(19), log });
  assert.equal(decide(none).kind, 'idle_start'); // nothing moved today => no wrapup
  const done = mk({ now: at(19), log, tasks: [T('a', 'Write report', { checked: true }), T('b', 'Email Sam')] });
  const n = decide(done);
  assert.equal(n.kind, 'wrapup');
  assert.equal(n.action, 'wrapup');
  assert.equal(n.taskId, 'a');
  assert.equal(decide(mk({ now: at(19), log, lastFocusEndedAt: at(15), tasks: [T('b', 'Email Sam')] })).kind, 'wrapup');
  assert.equal((decide(mk({ now: at(15), log, tasks: [T('a', 'x', { checked: true })] })) || {}).kind !== 'wrapup', true);
  const twice = { sent: [...log.sent, sentAt('wrapup', at(18), 'started')] };
  assert.notEqual((decide({ ...done, now: at(21), log: twice }) || {}).kind, 'wrapup');
});

test('R2: never during focus/break, quiet hours, snooze, or when off', () => {
  assert.equal(decide(mk({ pomo: { phase: 'focus', running: true } })), null);
  assert.equal(decide(mk({ pomo: { phase: 'break', running: true } })), null);
  assert.equal(decide(mk({ pomo: { phase: 'focus', running: false } })), null);
  assert.equal(decide(mk({ settings: { nudges: false } })), null);
  for (const h of [22, 23, 0, 3, 7]) assert.equal(decide(mk({ now: at(h, 30) })), null, 'quiet at ' + h);
  assert.ok(decide(mk({ now: at(8) })));
  assert.equal(decide(mk({ snoozedUntil: at(10) + M })), null);
  assert.ok(decide(mk({ snoozedUntil: at(10) })));
  // custom quiet window (non-wrapping) and timezone handling
  assert.equal(decide(mk({ settings: { nudges: true, quietStart: '09:00', quietEnd: '11:00' } })), null);
  // 10:00 UTC with offset -330 (IST, UTC+5:30) is 15:30 local; 07:00 UTC is 12:30 local => fine, 03:00 UTC is 08:30 local
  assert.equal(decide(mk({ now: at(18, 30), tzOffsetMin: -330 })), null); // 00:00 local
  assert.ok(decide(mk({ now: at(3, 0), tzOffsetMin: -330 }))); // 08:30 local
});

test('R3: global gap, daily cap, per-kind cooldown', () => {
  const base = { sent: [sentAt('morning_pick', at(9), 'started', 'a')] };
  assert.equal(decide(mk({ now: at(9, 30), log: base })), null); // < 60 min gap
  assert.ok(decide(mk({ now: at(10, 30), log: base, lastFocusEndedAt: null })));
  const capped = { sent: [1, 2, 3].map((i) => sentAt('idle_start', at(8 + i), 'started', 'a')) };
  assert.equal(decide(mk({ now: at(14), log: capped, settings: { nudges: true, maxPerDay: 3 } })), null);
  assert.ok(decide(mk({ now: at(14), log: capped, settings: { nudges: true, maxPerDay: 4 } })));
  // idle_start cooldown 120 min
  const idle = { sent: [sentAt('morning_pick', at(8, 30), 'started'), sentAt('idle_start', at(11), 'snoozed', 'a')] };
  assert.equal(decide(mk({ now: at(12, 30), log: idle })), null);
  assert.equal(decide(mk({ now: at(13, 30), log: idle })).kind, 'idle_start');
  // morning_pick once per day
  const m = { sent: [sentAt('morning_pick', at(8), 'started')] };
  assert.notEqual((decide(mk({ now: at(11), log: m, lastFocusEndedAt: at(10, 30) })) || {}).kind, 'morning_pick');
});

test('R3: backs off when ignored or dismissed, resets on engagement, stops after streak', () => {
  const two = { sent: [sentAt('idle_start', at(10), 'ignored', 'a'), sentAt('idle_start', at(12), 'dismissed', 'a')] };
  assert.equal(decide(mk({ now: at(14, 30), log: two })), null); // 2.5h < 3h backoff
  assert.ok(decide(mk({ now: at(15, 30), log: two })));
  const one = { sent: [sentAt('morning_pick', at(9), 'started'), sentAt('idle_start', at(12), 'ignored', 'a')] };
  assert.ok(decide(mk({ now: at(14, 30), log: one }))); // single ignore: normal gap
  const reset = { sent: [sentAt('idle_start', at(8, 30), 'ignored'), sentAt('idle_start', at(10), 'ignored'), sentAt('idle_start', at(11), 'started')] };
  assert.ok(decide(mk({ now: at(13), log: reset })));
  const four = { sent: [8, 9, 11, 14].map((h) => sentAt('idle_start', at(h), 'ignored', 'a')) };
  assert.equal(decide(mk({ now: at(19), log: four })), null); // silent rest of the day
  assert.ok(decide(mk({ now: at(10, 0, 6), log: four }))); // fresh next day
  // unanswered nudge turns into "ignored" by itself
  const stale = { sent: [sentAt('idle_start', at(9), null), sentAt('idle_start', at(11), null)] };
  assert.equal(decide(mk({ now: at(13), log: stale })), null);
});

test('R3/R4: never repeats wording back to back; positive, shame-free copy', () => {
  const banned = /haven'?t|didn'?t|still not|behind|failed|lazy|should|must|overdue|you forgot|only \d|again!/i;
  for (const kind of Object.keys(WORDS)) for (const [title, body] of WORDS[kind]) {
    assert.ok(!banned.test(title + ' ' + body), title + ' / ' + body);
    assert.ok(body.includes('{t}') || kind === 'wrapup');
  }
  let log = { sent: [] };
  const seen = [];
  for (let i = 0; i < 6; i++) {
    const now = at(8 + i * 2);
    const n = decide(mk({ now, log, tasks: [T('a', 'Write report'), T('b', 'x', { checked: true })], lastFocusEndedAt: null }));
    if (!n) continue;
    seen.push(n);
    log = recordOutcome(log, n, null, now);
    log = recordOutcome(log, n, 'snoozed', now + M);
  }
  assert.ok(seen.length >= 3);
  for (let i = 1; i < seen.length; i++) {
    if (seen[i].kind === seen[i - 1].kind) assert.notEqual(seen[i].body, seen[i - 1].body);
  }
  const idles = seen.filter((n) => n.kind === 'idle_start');
  for (let i = 1; i < idles.length; i++) assert.notEqual(idles[i].title + idles[i].body, idles[i - 1].title + idles[i - 1].body);
  assert.ok(decide(mk()).body.includes('5 minutes'));
});

test('recordOutcome: appends, resolves pending, is immutable', () => {
  const n = { kind: 'idle_start', taskId: 'a', v: 1 };
  const log0 = { sent: [] };
  const log1 = recordOutcome(log0, n, null, 1000);
  assert.deepEqual(log0, { sent: [] });
  assert.equal(log1.sent.length, 1);
  assert.equal(log1.sent[0].outcome, null);
  const log2 = recordOutcome(log1, n, 'started', 2000);
  assert.equal(log2.sent.length, 1);
  assert.equal(log2.sent[0].outcome, 'started');
  assert.equal(log1.sent[0].outcome, null);
  assert.equal(recordOutcome(log2, n, 'dismissed', 3000).sent.length, 2);
  let big = log0;
  for (let i = 0; i < 80; i++) big = recordOutcome(big, n, null, i);
  assert.ok(big.sent.length <= 50);
});

test('R6: deterministic and does not mutate input', () => {
  const input = mk({ now: at(11), log: { sent: [sentAt('morning_pick', at(9), 'snoozed', 'a')] } });
  const snap = JSON.stringify(input);
  const a = decide(input), b = decide(JSON.parse(snap));
  assert.deepEqual(a, b);
  assert.equal(JSON.stringify(input), snap);
  assert.equal(decide(mk({ tasks: [] })), null);
});

test('R1: nudge shape is single-task, single-action', () => {
  const kinds = new Set();
  const cases = [mk(), mk({ now: at(13), log: { sent: [sentAt('morning_pick', at(9), 'started')] } }),
    mk({ now: at(11), tasks: [T('c', 'Old', { carried: true, isToday: false })], log: { sent: [sentAt('morning_pick', at(9), 'started')] } }),
    mk({ now: at(19), tasks: [T('a', 'Won', { checked: true })], log: { sent: [sentAt('morning_pick', at(9), 'started')] } })];
  for (const c of cases) {
    const n = decide(c);
    kinds.add(n.kind);
    assert.ok(['start', 'pick', 'triage', 'wrapup'].includes(n.action));
    assert.ok(n.taskId === null || typeof n.taskId === 'string');
    assert.equal((n.body.match(/"/g) || []).length <= 2, true, 'at most one quoted task');
  }
  assert.equal(kinds.size, 4);
});

// ---- grafts from the arena: per-task rest for carried tasks, no-task wrapup wording
const D = { decide };
const IST2 = -330;
const atT = (h, m = 0, day = 5) => Date.UTC(2026, 9, day, h, m) + IST2 * 60000;
const base2 = (over = {}) => ({
  now: at(11), tzOffsetMin: IST2, settings: {}, currentTaskId: null, pomo: { phase: 'idle', running: false },
  lastFocusEndedAt: at(10, 30), log: { sent: [] }, snoozedUntil: null,
  tasks: [{ id: 'old', text: 'Old thing', checked: false, isToday: false, carried: true, date: '2026-10-01' }], ...over,
});

test('a carried task is not asked about again for 3 days, even on a new day', () => {
  const asked = { kind: 'carried_over', at: at(11, 0, 4), taskId: 'old', outcome: 'ignored', v: 0 };
  assert.equal(D.decide(base2({ log: { sent: [asked] } })), null);                                    // 1 day later: rests
  assert.equal(D.decide(base2({ now: at(11, 0, 8), log: { sent: [asked] } })).kind, 'carried_over');   // 4 days later: ok again
});

test('a wrap-up with no task to name uses the task-free wording', () => {
  const n = D.decide(base2({ now: atT(19), tasks: [], lastFocusEndedAt: atT(15), log: { sent: [] } }));
  assert.equal(n && n.kind, 'wrapup');
  assert.equal(n.taskId, null);
  assert.ok(!/""/.test(n.body) && !/undefined/.test(n.body) && !/your focus time/.test(n.body));
});
