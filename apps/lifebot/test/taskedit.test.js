const test = require('node:test');
const assert = require('node:assert/strict');

const Tasks = require('../lib/tasks.js');
const E = require('../lib/taskedit.js');

const DAY = '2026-10-02';
const MD = '## Today\n\n- [ ] Write the report\n- [x] Email prof (done 2026-10-01T09:00)\n  - [ ] nested step\n- [ ] Study Python\n';
const idOf = (text) => Tasks.listTasks(MD, DAY).find((t) => t.text === text).id;

test('setTaskText keeps indent, checkbox and done marker, and the file line endings', () => {
  assert.equal(Tasks.setTaskText(MD, 2, 'Write the final report'), MD.replace('Write the report', 'Write the final report'));
  assert.match(Tasks.setTaskText(MD, 3, 'Email Prof. Rao'), /- \[x\] Email Prof\. Rao \(done 2026-10-01T09:00\)/);
  assert.match(Tasks.setTaskText(MD, 4, 'nested!'), /\n  - \[ \] nested!\n/);
  const crlf = MD.replace(/\n/g, '\r\n');
  assert.ok(Tasks.setTaskText(crlf, 2, 'x').includes('\r\n') && !/[^\r]\n/.test(Tasks.setTaskText(crlf, 2, 'x')));
  assert.equal(Tasks.setTaskText(MD, 0, 'x'), null);                         // a heading is not a task
  assert.equal(Tasks.setTaskText(MD, 99, 'x'), null);
});

test('validateText rejects empty, multi-line, non-text and over-long input without truncating', () => {
  assert.deepEqual(E.validateText('  ok  '), { ok: true, text: 'ok' });
  for (const bad of ['', '   ', 'a\nb', 'a\r\nb', null, 42, undefined]) assert.equal(E.validateText(bad).ok, false);
  const long = 'x'.repeat(E.MAX_TASK_CHARS + 1);
  const r = E.validateText(long);
  assert.equal(r.ok, false);
  assert.match(r.error, /201\/200/);
  assert.match(r.error, /nothing was saved/);
  assert.equal(E.validateText('x'.repeat(E.MAX_TASK_CHARS)).ok, true);        // exactly at the limit is fine
});

test('a normal edit updates only that line and returns the task id for the new text', () => {
  const r = E.applyEdit({ markdown: MD, dateIso: DAY, id: idOf('Write the report'), oldText: 'Write the report', newText: 'Write the final report' });
  assert.equal(r.ok, true);
  assert.equal(r.text, 'Write the final report');
  assert.equal(r.id, `${DAY}:lifebot:write-the-final-report`);
  assert.equal(r.markdown, MD.replace('Write the report', 'Write the final report'));
});

test('an unchanged edit is a no-op success', () => {
  const r = E.applyEdit({ markdown: MD, dateIso: DAY, id: idOf('Study Python'), oldText: 'Study Python', newText: ' Study Python ' });
  assert.equal(r.ok, true);
  assert.equal(r.markdown, MD);
});

test('stale edits are refused with the current text instead of overwriting newer data', () => {
  const changedElsewhere = MD.replace('Write the report', 'Write the REVISED report');
  const r = E.applyEdit({ markdown: changedElsewhere, dateIso: DAY, id: idOf('Write the report'), oldText: 'Write the report', newText: 'My edit' });
  assert.equal(r.ok, false);
  assert.equal(r.code, 'not_found');                                          // id is derived from text, so the task "moved"
  const sameId = E.applyEdit({ markdown: MD.replace('- [ ] Study Python', '- [ ] Study Python'), dateIso: DAY, id: idOf('Study Python'), oldText: 'Something older', newText: 'x' });
  assert.equal(sameId.code, 'conflict');
  assert.equal(sameId.currentText, 'Study Python');
});

test('deleted tasks and malformed references are rejected cleanly', () => {
  assert.equal(E.applyEdit({ markdown: MD, dateIso: DAY, id: `${DAY}:lifebot:gone`, oldText: 'gone', newText: 'x' }).code, 'not_found');
  assert.equal(E.applyEdit({ markdown: MD, dateIso: DAY, id: 5, oldText: 'x', newText: 'y' }).code, 'invalid');
  assert.equal(E.applyEdit({ markdown: MD, dateIso: DAY, id: idOf('Study Python'), oldText: null, newText: 'y' }).code, 'invalid');
  assert.equal(E.applyEdit({ markdown: MD, dateIso: DAY, id: idOf('Study Python'), oldText: 'Study Python', newText: '' }).code, 'invalid');
});

test('editing one of two identical tasks edits the right line', () => {
  const dup = '- [ ] Same\n- [ ] Same\n';
  const second = Tasks.listTasks(dup, DAY)[1];
  const r = E.applyEdit({ markdown: dup, dateIso: DAY, id: second.id, oldText: 'Same', newText: 'Different' });
  assert.equal(r.markdown, '- [ ] Same\n- [ ] Different\n');
});


test('nextOpen picks the next unchecked task after the finished one, wrapping around', () => {
  const tasks = [{ id: 'a', checked: false }, { id: 'b', checked: true }, { id: 'c', checked: false }, { id: 'd', checked: false }];
  assert.equal(Tasks.nextOpen(tasks, 'a').id, 'c');            // skips the done one
  assert.equal(Tasks.nextOpen(tasks, 'c').id, 'd');
  assert.equal(Tasks.nextOpen(tasks, 'd').id, 'a');            // wraps to the start
  assert.equal(Tasks.nextOpen(tasks, null).id, 'a');           // free focus finished: first open task
  assert.equal(Tasks.nextOpen(tasks, 'zzz').id, 'a');
  assert.equal(Tasks.nextOpen([{ id: 'x', checked: true }], 'x'), null);
  assert.equal(Tasks.nextOpen([], 'x'), null);
});
