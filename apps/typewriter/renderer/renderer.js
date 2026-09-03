// Typewriter Renderer - Checkpoint 2.2: Interactive Checklist DOM Rendering & Live Counter

const SAMPLE_MARKDOWN = `Some notes before any phase starts — this is preamble text, not a checklist item.

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

// DOM Elements
const checklistView = document.getElementById('checklist-view');
const dropZone = document.getElementById('drop-zone');
const doneCounter = document.getElementById('done-counter');
const btnAddLeft = document.getElementById('btn-add-left');

// In-Memory Document State (Checkpoint 2.2 only: strictly in-memory)
let parsedPlan = null;

// Format current timestamp (YYYY-MM-DDTHH:mm)
function getCurrentTimestamp() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${d}T${hh}:${mm}`;
}

// Update the live header counter
function updateLiveCounter() {
  if (!parsedPlan) return;
  const completed = parsedPlan.tasks.filter(t => t.checked).length;
  const total = parsedPlan.tasks.length;
  doneCounter.textContent = `${completed}/${total} done`;
  return { completed, total };
}

// Render the checklist from parsed document model
function renderChecklist(plan) {
  parsedPlan = plan;
  checklistView.innerHTML = '';
  checklistView.style.display = 'flex';
  dropZone.style.display = 'none';

  updateLiveCounter();

  plan.phases.forEach((phase) => {
    const phaseGroup = document.createElement('div');
    phaseGroup.className = 'phase-group';

    const header = document.createElement('div');
    header.className = 'phase-header';
    header.textContent = phase.title.toUpperCase();
    phaseGroup.appendChild(header);

    phase.tasks.forEach((task) => {
      const item = document.createElement('div');
      item.className = 'checklist-item' + (task.checked ? ' checked' : '');
      item.dataset.taskId = task.id;

      if (task.indent > 0) {
        item.style.paddingLeft = `${task.indent * 7 + 4}px`;
      }

      // Checkbox element
      const checkbox = document.createElement('div');
      checkbox.className = 'task-checkbox';
      checkbox.textContent = task.checked ? 'X' : '';
      item.appendChild(checkbox);

      // Task label text
      const label = document.createElement('span');
      label.className = 'task-label';
      // Empty task placeholder: renders blank space without breaking
      label.textContent = task.text || '\u00A0';

      // Inline done timestamp if checked
      if (task.checked && task.doneTimestamp) {
        const tsSpan = document.createElement('span');
        tsSpan.className = 'done-timestamp';
        tsSpan.textContent = ` (done ${task.doneTimestamp})`;
        label.appendChild(tsSpan);
      }
      item.appendChild(label);

      // Click handler: in-memory state toggle & live counter update
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleTask(task, item, checkbox, label);
      });

      phaseGroup.appendChild(item);
    });

    checklistView.appendChild(phaseGroup);
  });
}

// Handle checkbox toggle
function toggleTask(task, itemEl, checkboxEl, labelEl) {
  task.checked = !task.checked;

  if (task.checked) {
    task.doneTimestamp = getCurrentTimestamp();
    itemEl.classList.add('checked');
    checkboxEl.textContent = 'X';

    // Remove existing timestamp span if present
    const existingTs = labelEl.querySelector('.done-timestamp');
    if (existingTs) existingTs.remove();

    const tsSpan = document.createElement('span');
    tsSpan.className = 'done-timestamp';
    tsSpan.textContent = ` (done ${task.doneTimestamp})`;
    labelEl.appendChild(tsSpan);
  } else {
    task.doneTimestamp = null;
    itemEl.classList.remove('checked');
    checkboxEl.textContent = '';

    const existingTs = labelEl.querySelector('.done-timestamp');
    if (existingTs) existingTs.remove();
  }

  const { completed, total } = updateLiveCounter();
  console.log(`[CHECKLIST TOGGLE] Task "${task.id}" ("${task.text || '<empty>'}") -> checked: ${task.checked}, live counter: ${completed}/${total} done`);
}

// Switch back to new plan / drop zone
btnAddLeft.addEventListener('click', () => {
  checklistView.style.display = 'none';
  dropZone.style.display = 'flex';
  doneCounter.textContent = '0/0 done';
});

// Initialize on DOM ready with sample plan
window.addEventListener('DOMContentLoaded', () => {
  if (window.TypewriterParser && window.TypewriterParser.parseMarkdown) {
    const plan = window.TypewriterParser.parseMarkdown(SAMPLE_MARKDOWN);
    renderChecklist(plan);
    console.log('[TYPEWRITER INIT] Loaded plan:', plan.stats.summary);
  }
});
