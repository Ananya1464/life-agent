const test = require('node:test');
const assert = require('node:assert/strict');
const { suggestTasks, MAX_TASK_CHARS } = require('../lib/briefitems.js');

const NOTE = `# AI Edge: opportunities and research: 2026-10-06

# Your AI Edge — Tue, Oct 6

## 1. Opportunities to apply to

**Algoverse AI Safety Fellowship** (Algoverse) — https://algoverseairesearch.org/ai-safety-fellowship
Fit: **High** — interpretability.
Deadline: Sunday, October 18 @ 11:59pm PT (early deadline).
Next action: apply.

**CBAI Fall Fellowship** (CBAI) — https://www.cbai.ai/x
Deadline: closed on September 6.

**Junior LLM Engineer** (junbrain) — https://junbrain.com/x
Deadline: September 2026 (from listing title — may have passed)

## 2. AI research + news in your field

**Base Models Can Reason By Taking a Cue** (arXiv:2610.06851) — fixing tokens.

## 3. One leverage idea

Extend your prompt-injection repo into a red-team benchmark with 200 adversarial prompts. Then compare models.

## 4. Market note

No verified market data.
`;

test('suggests a task per opportunity and paper, with the deadline only when it is a real future-looking one', () => {
  const s = suggestTasks(NOTE);
  const texts = s.map((x) => x.text);
  assert.ok(texts.includes('Review opportunity: Algoverse AI Safety Fellowship (deadline Sunday, October 18 @ 11:59pm PT (early deadline))'));
  assert.ok(texts.includes('Review opportunity: CBAI Fall Fellowship'));                // closed: no deadline attached
  assert.ok(texts.includes('Review opportunity: Junior LLM Engineer'));                 // "may have passed": no deadline attached
  assert.ok(texts.includes('Read paper: Base Models Can Reason By Taking a Cue'));
  assert.ok(texts.some((t) => t.startsWith('Try: Extend your prompt-injection repo')));
  assert.ok(!texts.some((t) => /market/i.test(t)));                                      // the market note is not a task
});

test('career prep: reading items become Study tasks and the small steps become tasks as written', () => {
  const note = `# Global career prep

## 1. Reading list (this week)

1. **Attention Is All You Need** — https://arxiv.org/abs/1706.03762 — 45 min

## 2. Skills to build

**Evaluation harnesses** — build a small one for your RAG repo.

## 4. Three small steps for the week

1. Read the first two sections of the attention paper.
2. Draft a one-page research statement.
`;
  const texts = suggestTasks(note).map((x) => x.text);
  assert.deepEqual(texts, ['Study: Attention Is All You Need', 'Build skill: Evaluation harnesses',
    'Read the first two sections of the attention paper.', 'Draft a one-page research statement.']);
});

test('suggestions are short, de-duplicated, capped, and empty for notes with nothing actionable', () => {
  const long = `## Opportunities\n\n**${'A very long program name '.repeat(8)}**\n`;
  assert.ok(suggestTasks(long).every((x) => x.text.length <= MAX_TASK_CHARS));
  assert.equal(suggestTasks('## Opportunities\n\n**Same Program**\n\n**Same Program**\n').length, 1);
  assert.deepEqual(suggestTasks('# Notes\n\n### Totals\n- oats\n'), []);
  assert.deepEqual(suggestTasks('# Meal plan\n\n### Breakfast\n- oats\n').map((x) => x.text), ['Meal: Breakfast']);
  assert.deepEqual(suggestTasks(''), []);
  const many = '## Opportunities\n\n' + Array.from({ length: 30 }, (_, i) => `**Program number ${i}**\n`).join('\n');
  assert.equal(suggestTasks(many).length, 16);
});

test('a bold section label (no ## heading) also starts a section, as in the career prep note', () => {
  const note = `# Global career prep

**Reading list (this week)**

1. **Single-Pass Uncertainty Heads** — Ghassabi et al., 2026
   http://arxiv.org/abs/2610.03482v1

---

**Skills to build**

1. **Uncertainty quantification in language models.** An active, hirable area.

---

**Three small steps for the week**

1. Read the uncertainty heads paper and write three bullet points.
`;
  assert.deepEqual(suggestTasks(note).map((x) => x.text), ['Study: Single-Pass Uncertainty Heads',
    'Build skill: Uncertainty quantification in language models', 'Read the uncertainty heads paper and write three bullet points.']);
});

test('each idea knows its line, and meal plans get one task per meal', () => {
  const note = `# Meal plan: 2026-10-06

### Breakfast — Overnight Oats

- Rolled oats: 50 g

### Lunch — Rajma Chawal

- Rajma curry
`;
  const s = suggestTasks(note);
  assert.deepEqual(s.map((x) => [x.text, x.line]), [['Meal: Breakfast — Overnight Oats', 2], ['Meal: Lunch — Rajma Chawal', 6]]);
  const lines = note.split('\n');
  assert.ok(s.every((x) => lines[x.line].includes(x.text.replace('Meal: ', ''))));          // the button goes on the right line
  const opp = suggestTasks('## Opportunities\n\n**Test Fellowship** (Org)\nDeadline: October 30\n');
  assert.deepEqual(opp.map((x) => x.line), [2]);
});
