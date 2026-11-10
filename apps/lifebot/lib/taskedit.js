/**
 * Safe editing of one task line in the Typewriter markdown (pure; no I/O).
 * The widget edits the SAME checklist file Lifebot uses; this module guards against bad input
 * and against overwriting a task that changed elsewhere in the meantime.
 */
const Tasks = require('./tasks.js');

const MAX_TASK_CHARS = 200;

/** Validate user text without altering it (never silently truncates). */
function validateText(text) {
  if (typeof text !== 'string') return { ok: false, code: 'invalid', error: 'Task text must be text' };
  if (/[\r\n]/.test(text)) return { ok: false, code: 'invalid', error: 'A task must be a single line' };
  const clean = text.trim();
  if (!clean) return { ok: false, code: 'invalid', error: 'A task cannot be empty' };
  if (clean.length > MAX_TASK_CHARS) {
    return { ok: false, code: 'invalid', error: `Too long: ${clean.length}/${MAX_TASK_CHARS} characters (nothing was saved)` };
  }
  return { ok: true, text: clean };
}

/**
 * Apply an edit to task `id`.
 * Returns { ok: true, markdown, id, text } or { ok: false, code, error, currentText? } where code is
 * 'invalid' | 'not_found' | 'conflict'. `oldText` is what the widget believed the task said; if the
 * file now says something else, the edit is refused and the current text is reported back.
 */
function applyEdit({ markdown, dateIso, id, oldText, newText }) {
  const v = validateText(newText);
  if (!v.ok) return v;
  if (typeof id !== 'string' || typeof oldText !== 'string') {
    return { ok: false, code: 'invalid', error: 'Missing task reference' };
  }
  const task = Tasks.listTasks(markdown, dateIso).find((t) => t.id === id);
  if (!task) return { ok: false, code: 'not_found', error: 'That task no longer exists' };
  if (task.text !== oldText.trim()) {
    return { ok: false, code: 'conflict', error: 'This task was changed elsewhere. Reloaded the latest text.', currentText: task.text };
  }
  if (v.text === task.text) return { ok: true, markdown, id, text: task.text };          // nothing to change
  const updated = Tasks.setTaskText(markdown, task.lineIndex, v.text);
  if (updated === null) return { ok: false, code: 'not_found', error: 'That task line could not be edited' };
  const next = Tasks.listTasks(updated, dateIso).find((t) => t.lineIndex === task.lineIndex);
  return { ok: true, markdown: updated, id: next ? next.id : id, text: v.text };
}

module.exports = { validateText, applyEdit, MAX_TASK_CHARS };
