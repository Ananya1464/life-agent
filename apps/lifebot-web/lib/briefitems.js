'use strict';
// Turn a saved briefing note into task suggestions, each tied to the line it came from so the UI can put an
// "+ Add to today" button right on that line ("Review opportunity: ...", "Read paper: ...", "Meal: Lunch ...").
// Pure: text in, suggestions out. The user decides which ones to add; nothing here touches the task file.

const MAX_TASK_CHARS = 180;
const MAX_SUGGESTIONS = 16;

/** What kind of task each briefing section produces. Matched against the lowercased heading text. */
const SECTION_VERBS = [
  [/opportunit/, 'Review opportunity'],
  [/research|news|paper/, 'Read paper'],
  [/reading|study|course/, 'Study'],
  [/skill/, 'Build skill'],
  [/leverage|idea/, 'Try idea'],
];
const STEP_SECTION = /(small steps|three steps|next steps)/;
const MEAL_HEADING = /^(breakfast|lunch|snack|dinner|pre-?workout|post-?workout|supper|brunch)\b/i;
const BOLD_SECTION = /^\s*\*\*[^*]*(reading list|skills|opportunit|small steps|three steps|next steps|research|news|leverage|market|global)[^*]*\*\*\s*$/i;
const NO_DEADLINE = /(none|not stated|unknown|closed|passed|may have passed|n\/a)/i;

const clean = (s) => String(s).replace(/\*\*|__|`/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/\s+/g, ' ').trim();
const clip = (s, n = MAX_TASK_CHARS) => (s.length > n ? `${s.slice(0, n - 1).trim()}…` : s);

function verbFor(heading) {
  const h = heading.toLowerCase();
  for (const [re, verb] of SECTION_VERBS) if (re.test(h)) return verb;
  return null;
}

/** Title of a bold item line such as "**Algoverse Fellowship** (Org) — https://..." or "1. **Title**". */
function itemTitle(line) {
  const m = /^\s*(?:\d+[.)]\s*|[-*]\s+)?\*\*([^*]{3,140})\*\*/.exec(line);
  return m ? clean(m[1]).replace(/[:.\s]+$/, '') : null;
}

/** Returns [{ text, kind, line }], line = 0-based index of the note line the idea belongs to. */
function suggestTasks(markdown) {
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
  const out = [];
  const seen = new Set();
  let heading = '';
  let current = null;                                   // the opportunity/paper being read (to attach its deadline)

  const push = (text, kind, line) => {
    const t = clip(clean(text));
    const key = t.toLowerCase();
    if (t.length < 8 || seen.has(key) || out.length >= MAX_SUGGESTIONS) return null;
    seen.add(key);
    const item = { text: t, kind, line };
    out.push(item);
    return item;
  };

  lines.forEach((raw, i) => {
    // a section can be a '## heading' or a line that is only a bold section label like '**Reading list (this week)**'
    const h = /^#{1,3}\s+(.*)$/.exec(raw) || (BOLD_SECTION.test(raw) ? /^\s*\*\*([^*]+)\*\*\s*$/.exec(raw) : null);
    if (h) {
      heading = clean(h[1]);
      current = null;
      if (MEAL_HEADING.test(heading)) push(`Meal: ${heading}`, 'Meal', i);      // "### Lunch - Rajma curry" -> a task for that meal
      return;
    }

    if (STEP_SECTION.test(heading.toLowerCase())) {
      const step = /^\s*(?:\d+[.)]|[-*])\s+(.*)$/.exec(raw);
      if (step && clean(step[1]).length >= 8) push(clean(step[1]), 'Step', i);
      return;
    }

    const verb = verbFor(heading);
    if (!verb) return;
    const title = itemTitle(raw);
    if (title) {
      current = verb === 'Try idea' ? null : push(`${verb}: ${title}`, verb, i);
      return;
    }
    if (verb === 'Try idea' && !current && clean(raw).length > 30 && !/^\s*[-=_]{3,}\s*$/.test(raw)) {
      current = push(`Try: ${clean(raw).split(/(?<=[.!?])\s/)[0]}`, verb, i);       // the first sentence of the idea
      return;
    }
    const d = /^\s*Deadline:\s*(.+)$/i.exec(clean(raw).replace(/^-\s*/, ''));
    if (current && d && !NO_DEADLINE.test(d[1])) {
      current.text = clip(`${current.text} (deadline ${clean(d[1]).replace(/\.$/, '')})`);
      current = null;
    }
  });
  return out;
}

module.exports = { suggestTasks, MAX_TASK_CHARS, MAX_SUGGESTIONS };
