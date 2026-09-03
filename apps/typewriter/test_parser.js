const parser = require('./renderer/parser.js');

const sampleMarkdown = `Some notes before any phase starts — this is preamble text, not a checklist item.

## Phase 1: Setup

- [ ] Install dependencies
- [x] Initialize git repo (done 2026-08-20T09:15)
- [x] Set up ESLint config

## Phase 2: Core Feature

- [ ] Build parser module
-   [X]   Draft data model (done 2026-08-21T14:02)
  - [ ] sub-task under a nested indent
- [] Broken checkbox with no space
- [y] Invalid marker character

## Phase 3

- [ ]
- [x] Done but marked unchecked-looking (done 2026-08-22T08:00)
Just a stray paragraph line someone typed here by mistake.`;

const parsed = parser.parseMarkdown(sampleMarkdown);

console.log('=== PARSED STATS ===');
console.log(JSON.stringify(parsed.stats, null, 2));

console.log('\n=== PARSED PHASES & TASKS ===');
console.log(JSON.stringify(parsed.phases, null, 2));

console.log('\n=== ALL FLATTENED TASKS ===');
console.log(JSON.stringify(parsed.tasks, null, 2));

console.log('\n=== ROUND-TRIP UPDATE TEST ===');
// 1. Check task-0 (Install dependencies)
let updatedMd = parser.updateTaskInMarkdown(sampleMarkdown, 4, true, '2026-09-02T21:45');
// 2. Uncheck task-1 (Initialize git repo)
updatedMd = parser.updateTaskInMarkdown(updatedMd, 5, false);

console.log(updatedMd);
