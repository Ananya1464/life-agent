const test = require('node:test');
const assert = require('node:assert/strict');
const T = require('../lib/tasks.js');
const D = require('../lib/taskdays.js');

const MD = '## Today\n- [x] finished (done 2026-10-03T10:00)\n- [ ] old open\n- [ ] new open\n';

test('tasks first seen before today and still open are carried over; new ones are today', () => {
  const tasks = T.listTasks(MD, '2026-10-05');
  const r = D.annotate(tasks, { 'old-open': '2026-10-03' }, '2026-10-05');
  const by = Object.fromEntries(r.tasks.map((t) => [t.text, t]));
  assert.deepEqual([by['old open'].carried, by['old open'].isToday], [true, false]);
  assert.deepEqual([by['new open'].carried, by['new open'].isToday, by['new open'].date], [false, true, '2026-10-05']);
  assert.deepEqual([by['finished'].carried, by['finished'].date], [false, '2026-10-03']);   // done marker gives its day; finished is never carried
  assert.equal(r.firstSeen['new-open'], '2026-10-05');
});

test('the memory is never wiped by an empty or unreadable file', () => {
  const known = { 'old-open': '2026-10-03' };
  const r = D.annotate([], known, '2026-10-05');
  assert.deepEqual(r.firstSeen, known);
  assert.equal(r.changed, false);
});

test('ids keep their text part when re-pointed at another day', () => {
  assert.equal(D.keyOf('2026-10-04:lifebot:write-report#2'), 'write-report#2');
  assert.equal(D.idForDay('2026-10-04:lifebot:write-report', '2026-10-05'), '2026-10-05:lifebot:write-report');
});

test('removeTask deletes only task lines and keeps the file otherwise intact', () => {
  assert.equal(T.removeTask(MD, 2), '## Today\n- [x] finished (done 2026-10-03T10:00)\n- [ ] new open\n');
  assert.equal(T.removeTask(MD, 0), null);          // a heading is not a task
  assert.equal(T.removeTask(MD, 99), null);
  assert.equal(T.removeTask('- [ ] a\r\n- [ ] b\r\n', 0), '- [ ] b\r\n');   // keeps CRLF
});
