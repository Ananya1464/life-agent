const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../lib/schedule.js');

const IST = -330;
const at = (h, m = 0, day = 5) => Date.UTC(2026, 9, day, h, m) + IST * 60000;   // local IST wall clock -> epoch (Mon 5 Oct 2026)
const names = (x) => x.map((s) => s.task);

test('nothing is due before the first slot; then slots become due in time order', () => {
  assert.deepEqual(names(S.due({ now: at(6, 59), tzOffsetMin: IST })), []);
  assert.deepEqual(names(S.due({ now: at(8, 30), tzOffsetMin: IST })), ['meal_plan', 'ai_edge']);
});

test('missed slots catch up when the app starts late, and weekly tasks respect their day', () => {
  const late = names(S.due({ now: at(22, 30), tzOffsetMin: IST }));              // Monday 22:30
  assert.deepEqual(late, ['meal_plan', 'ai_edge', 'career_prep', 'evening_checkin', 'goal_planner', 'tomorrow_planner']);
  assert.ok(!late.includes('weekly_review'));                                        // Sunday only
  assert.ok(names(S.due({ now: at(21, 0, 4), tzOffsetMin: IST })).includes('weekly_review'));   // Sunday 4 Oct
});

test('a task that succeeded today is not due again, and a running one is skipped', () => {
  let runs = S.started({}, 'meal_plan', at(7, 1), IST);
  assert.ok(!names(S.due({ now: at(7, 5), tzOffsetMin: IST, runs })).includes('meal_plan'));     // running
  runs = S.finished(runs, 'meal_plan', true, at(7, 3));
  assert.ok(!names(S.due({ now: at(9, 0), tzOffsetMin: IST, runs })).includes('meal_plan'));
  assert.ok(names(S.due({ now: at(7, 5, 6), tzOffsetMin: IST, runs })).includes('meal_plan'));   // next day
});

test('failures retry after 30 minutes, at most twice a day', () => {
  let runs = S.finished(S.started({}, 'ai_edge', at(8, 0), IST), 'ai_edge', false, at(8, 1), 'boom');
  assert.ok(!names(S.due({ now: at(8, 20), tzOffsetMin: IST, runs })).includes('ai_edge'));      // too soon
  assert.ok(names(S.due({ now: at(8, 40), tzOffsetMin: IST, runs })).includes('ai_edge'));
  runs = S.finished(S.started(runs, 'ai_edge', at(8, 40), IST), 'ai_edge', false, at(8, 41), 'boom');
  assert.equal(runs.ai_edge.attempts, 2);
  assert.ok(!names(S.due({ now: at(12, 0), tzOffsetMin: IST, runs })).includes('ai_edge'));      // capped for today
});

test('the runner only ever names tasks from the fixed schedule', () => {
  assert.deepEqual(S.TASKS.slice().sort(), ['ai_edge', 'career_prep', 'evening_checkin', 'goal_planner', 'meal_plan', 'tomorrow_planner', 'weekly_review']);
});
