/**
 * Typewriter task helpers on top of the markdown checklist parser.
 * Task ids are derived from the day and the text, so they stay stable when lines move.
 */
const Parser = require('./parser.js');

const DEFAULT_MARKDOWN = '## Today\n\n';

function slug(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'task';
}

function taskId(dateIso, text, occurrence = 1) {
  return `${dateIso}:lifebot:${slug(text)}${occurrence > 1 ? `#${occurrence}` : ''}`;
}

/** Parsed tasks with stable ids (blank checkboxes skipped; duplicate texts get #2, #3...). */
function listTasks(markdown, dateIso) {
  const seen = {};
  return Parser.parseMarkdown(markdown).tasks
    .filter((t) => t.text)
    .map((t) => {
      const key = slug(t.text);
      seen[key] = (seen[key] || 0) + 1;
      return {
        id: taskId(dateIso, t.text, seen[key]), text: t.text, checked: t.checked,
        lineIndex: t.lineIndex, phase: t.phaseTitle, doneTimestamp: t.doneTimestamp,
      };
    });
}

/** Append `- [ ] text` after the last task (or heading); creates "## Today" when the file is empty. */
function addTask(markdown, text) {
  const clean = String(text).replace(/\s+/g, ' ').trim();
  if (!clean) throw new Error('Task text is required');
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
  let lastIdx = -1;
  lines.forEach((l, i) => { if (/^\s*-\s+\[[ xX]\]/.test(l) || /^##\s+/.test(l)) lastIdx = i; });
  if (lastIdx === -1) {
    const base = String(markdown || '').trimEnd();
    return `${base ? base + '\n\n' : ''}## Today\n\n- [ ] ${clean}\n`;
  }
  lines.splice(lastIdx + 1, 0, `- [ ] ${clean}`);
  const out = lines.join('\n');
  return out.endsWith('\n') ? out : out + '\n';
}

function toggle(markdown, lineIndex, checked, timestamp) {
  return Parser.updateTaskInMarkdown(markdown, lineIndex, checked, timestamp);
}

module.exports = { DEFAULT_MARKDOWN, slug, taskId, listTasks, addTask, toggle };
