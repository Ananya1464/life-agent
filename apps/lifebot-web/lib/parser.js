/**
 * Typewriter Markdown Parser
 * Parses checklist markdown files according to Typewriter spec.
 * Supports Node.js environment and browser script loading.
 */

(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.TypewriterParser = factory();
  }
}(typeof self !== 'undefined' ? self : this, function() {

  // Regex for Phase Header: ## Phase ... or ## Header ...
  const PHASE_REGEX = /^##\s+(.+)$/;

  // Regex for Task item: - [ ] or - [x] or - [X] with flexible spacing
  // Captures: 1: indent, 2: marker (space or x/X), 3: content
  const TASK_REGEX = /^(\s*)-\s+\[([ xX])\]\s*(.*)$/;

  // Regex for extracting trailing done timestamp: (done YYYY-MM-DDTHH:mm...) or (done YYYY-MM-DD HH:mm...)
  const DONE_TIMESTAMP_REGEX = /\s*\(done\s+([^\)]+)\)\s*$/i;

  /**
   * Parses markdown text into structured phases, tasks, and raw line records.
   * @param {string} markdownText 
   * @returns {object} Parsed document model
   */
  function parseMarkdown(markdownText) {
    if (typeof markdownText !== 'string') {
      markdownText = '';
    }

    const lines = markdownText.split(/\r?\n/);
    const phases = [];
    const tasks = [];
    const rawLines = [];

    let currentPhase = null;
    let phaseCount = 0;
    let taskCount = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      rawLines.push(line);

      // Check for Phase header (## ...)
      const phaseMatch = line.match(PHASE_REGEX);
      if (phaseMatch) {
        currentPhase = {
          id: `phase-${phaseCount++}`,
          title: phaseMatch[1].trim(),
          lineIndex: i,
          tasks: []
        };
        phases.push(currentPhase);
        continue;
      }

      // Check for checklist task (- [ ] or - [x])
      const taskMatch = line.match(TASK_REGEX);
      if (taskMatch) {
        const indent = taskMatch[1] || '';
        const marker = taskMatch[2];
        const rawContent = taskMatch[3] || '';
        const checked = (marker === 'x' || marker === 'X');

        // Extract (done <timestamp>) if present
        let cleanText = rawContent;
        let doneTimestamp = null;
        const doneMatch = rawContent.match(DONE_TIMESTAMP_REGEX);
        if (doneMatch) {
          doneTimestamp = doneMatch[1].trim();
          cleanText = rawContent.replace(DONE_TIMESTAMP_REGEX, '').trim();
        } else {
          cleanText = rawContent.trim();
        }

        const taskItem = {
          id: `task-${taskCount++}`,
          lineIndex: i,
          indent: indent.length,
          checked: checked,
          text: cleanText,
          rawContent: rawContent,
          doneTimestamp: doneTimestamp,
          phaseId: currentPhase ? currentPhase.id : null,
          phaseTitle: currentPhase ? currentPhase.title : null
        };

        tasks.push(taskItem);
        if (currentPhase) {
          currentPhase.tasks.push(taskItem);
        }
        continue;
      }

      // Other lines: preamble, stray paragraphs, invalid checkboxes, blanks
      // These are preserved in rawLines and do not count toward task stats
    }

    const completedCount = tasks.filter(t => t.checked).length;
    const totalCount = tasks.length;

    return {
      stats: {
        totalTasks: totalCount,
        completedTasks: completedCount,
        summary: `${completedCount}/${totalCount} done`
      },
      phases: phases,
      tasks: tasks,
      rawLineCount: lines.length
    };
  }

  /**
   * Updates a single task item in raw markdown while strictly preserving
   * all surrounding whitespace, indentation, comments, preambles, and stray lines.
   * @param {string} markdownText
   * @param {number} lineIndex Line index of the task to update
   * @param {boolean} checked New checked state
   * @param {string|null} timestamp Optional ISO timestamp string (e.g. 2026-09-02T21:45)
   * @returns {string} Updated markdown text
   */
  function updateTaskInMarkdown(markdownText, lineIndex, checked, timestamp) {
    const lines = markdownText.split(/\r?\n/);
    if (lineIndex < 0 || lineIndex >= lines.length) {
      return markdownText;
    }

    const line = lines[lineIndex];
    const match = line.match(TASK_REGEX);
    if (!match) {
      return markdownText;
    }

    const indent = match[1] || '';
    const rawContent = match[3] || '';

    // Strip any existing (done ...)
    const baseContent = rawContent.replace(DONE_TIMESTAMP_REGEX, '').trim();

    const newMarker = checked ? 'x' : ' ';
    let updatedLine = `${indent}- [${newMarker}]`;

    if (checked) {
      const ts = timestamp || new Date().toISOString().slice(0, 16);
      updatedLine += baseContent ? ` ${baseContent} (done ${ts})` : ` (done ${ts})`;
    } else {
      updatedLine += baseContent ? ` ${baseContent}` : '';
    }

    lines[lineIndex] = updatedLine;
    return lines.join('\n');
  }

  return {
    parseMarkdown: parseMarkdown,
    updateTaskInMarkdown: updateTaskInMarkdown
  };
}));
