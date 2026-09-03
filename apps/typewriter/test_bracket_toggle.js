const parser = require('./renderer/parser.js');

const testLine = '- [ ] Add support for [x] and [ ] inside task descriptions';

// Check matched groups directly using TASK_REGEX logic
const lines = [testLine];
const match = testLine.match(/^(\s*)-\s+\[([ xX])\]\s*(.*)$/);

console.log('=== INITIAL MATCH GROUPS ===');
console.log('Group 0 (Full match):', JSON.stringify(match[0]));
console.log('Group 1 (Indent):    ', JSON.stringify(match[1]));
console.log('Group 2 (Marker):    ', JSON.stringify(match[2]));
console.log('Group 3 (Content):   ', JSON.stringify(match[3]));

console.log('\n=== TOGGLE CHECKED ===');
const checkedResult = parser.updateTaskInMarkdown(testLine, 0, true, '2026-09-03T12:45');
console.log('Resulting line:');
console.log(checkedResult);

const checkedMatch = checkedResult.match(/^(\s*)-\s+\[([ xX])\]\s*(.*)$/);
console.log('\nChecked match groups:');
console.log('Group 1 (Indent): ', JSON.stringify(checkedMatch[1]));
console.log('Group 2 (Marker): ', JSON.stringify(checkedMatch[2]));
console.log('Group 3 (Content):', JSON.stringify(checkedMatch[3]));

console.log('\n=== TOGGLE UNCHECKED ===');
const uncheckedResult = parser.updateTaskInMarkdown(checkedResult, 0, false);
console.log('Resulting line:');
console.log(uncheckedResult);

const uncheckedMatch = uncheckedResult.match(/^(\s*)-\s+\[([ xX])\]\s*(.*)$/);
console.log('\nUnchecked match groups:');
console.log('Group 1 (Indent): ', JSON.stringify(uncheckedMatch[1]));
console.log('Group 2 (Marker): ', JSON.stringify(uncheckedMatch[2]));
console.log('Group 3 (Content):', JSON.stringify(uncheckedMatch[3]));
