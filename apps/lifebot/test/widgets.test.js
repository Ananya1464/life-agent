const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = (rel) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
const main = read('main.js');

test('widget preloads expose only narrow APIs and no Node primitives', () => {
  const tw = read('typewriter-preload.js');
  const av = read('avocado-preload.js');
  assert.deepEqual([...tw.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1]).sort(), ['collapse', 'get', 'hide', 'miniList', 'onChange', 'onMode', 'openApp', 'remove', 'select', 'start', 'stop', 'update']);
  assert.deepEqual([...av.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1]).sort(),
    ['abandon', 'ack', 'adjust', 'alarmAttention', 'collapse', 'getState', 'hide', 'managed', 'onCelebrate', 'onMode', 'onState', 'openApp', 'start']);
  for (const src of [tw, av]) {
    assert.ok(!/require\(['"](fs|child_process|path)['"]\)/.test(src));
    assert.ok(!/ipcRenderer\.send\(|exposeInMainWorld\('ipc/.test(src));            // no generic IPC pass-through
  }
});

test('both widget windows are sandboxed, isolated and always on top without stealing focus', () => {
  for (const win of ['avocado', 'typewriter']) {
    const start = main.indexOf(`function create${win[0].toUpperCase()}${win.slice(1)}()`);
    assert.ok(start > 0, win);
    const body = main.slice(start, start + 2600);
    for (const needle of ['contextIsolation: true', 'nodeIntegration: false', 'sandbox: true', "setAlwaysOnTop(true, 'floating')", 'showInactive()']) {
      assert.ok(body.includes(needle), `${win} missing ${needle}`);
    }
    assert.ok(!body.includes('setIgnoreMouseEvents'), `${win} must not be click-through`);
  }
});

test('widget IPC handlers validate their input', () => {
  assert.match(main, /ipcMain\.handle\('tw:update'[\s\S]{0,400}input\.id !== currentId/);          // only the current task is editable
  assert.match(main, /ipcMain\.handle\('tasks:setCurrent'[\s\S]{0,300}typeof id !== 'string'/);
  assert.match(main, /ipcMain\.handle\('avocado:start'[\s\S]{0,500}Math\.min\(Math\.max\(Math\.round\(input\.minutes\), 1\), 180\)/);
  assert.match(main, /ipcMain\.handle\('avocado:attention'[\s\S]{0,120}typeof on === 'boolean'/);
});

test('task text never reaches a cloud provider from the widgets path', () => {
  const twHandler = main.slice(main.indexOf("ipcMain.handle('tw:update'"), main.indexOf("ipcMain.handle('tasks:setCurrent'"));
  assert.ok(!/bridge\.request\('chat'|ntfy\.send|fetch\(|https\./.test(twHandler));
});


test('shared widget controls validate widget names and booleans', () => {
  assert.match(main, /ipcMain\.handle\('widget:collapse'[\s\S]{0,260}WIDGETS\.includes\(input\.widget\)[\s\S]{0,80}typeof input\.collapsed !== 'boolean'/);
  assert.match(main, /ipcMain\.handle\('widget:hide'[\s\S]{0,200}WIDGETS\.includes\(input\.widget\)/);
  assert.match(main, /ipcMain\.handle\('widget:openApp'[\s\S]{0,260}\['tasks', 'focus'\]\.includes\(input\.tab\)/);
  assert.match(main, /ipcMain\.handle\('avocado:ack'[\s\S]{0,200}\['stop', 'done', 'next'\]\.includes\(action\)/);
});

test('the renderer palette has no blue (it matches the widgets)', () => {
  const css = read('renderer/styles.css').toLowerCase();
  for (const blue of ['#38e8ff', '#0b0a24', '#15123d', '#3b34a8', '#2a2570', '#05041a']) assert.ok(!css.includes(blue), blue);
  for (const warm of ['#f5ede0', '#397d22', '#c1443c', '#57301f']) assert.ok(css.includes(warm), warm);
});

test('timer adjust and start lengths are validated in the main process', () => {
  assert.match(main, /function validMinutes\(v\)[\s\S]{0,160}Math\.min\(Math\.max\(Math\.round\(v\), 1\), 180\)/);
  assert.match(main, /function adjustTimer\(deltaMin\) \{\s*if \(!\[-5, 5\]\.includes\(deltaMin\)\) return;/);
  assert.match(main, /ipcMain\.handle\('tw:start', \(_e, input\)[\s\S]{0,900}validMinutes\(input && input\.minutes\)/);
  assert.match(main, /ipcMain\.handle\('pomodoro:start'[\s\S]{0,200}validMinutes\(task && task\.minutes\)/);
});

test('starting a session floats the widgets and the card follows the task', () => {
  const fn = main.slice(main.indexOf('function startFocus('), main.indexOf('function adjustTimer'));
  assert.ok(fn.includes('d.currentTaskId = known.id'));
  assert.ok(fn.includes('floatWidgets()'));
  assert.match(main, /ipcMain\.handle\('pomodoro:start'[\s\S]{0,400}win\.minimize\(\)/);
});

test('smoke/test mode can never touch real personal data (profile, tasks file, dashboard)', () => {
  // Without these defaults the smoke run wrote to the real Obsidian Tasks.md.
  assert.match(main, /SMOKE_DIR && !process\.env\.LIFEBOT_USER_DATA\) process\.env\.LIFEBOT_USER_DATA = path\.join\(SMOKE_DIR/);
  assert.match(main, /SMOKE_DIR && !process\.env\.LIFEBOT_TASKS_FILE\) process\.env\.LIFEBOT_TASKS_FILE = path\.join\(SMOKE_DIR/);
  assert.match(main, /LIFE_AGENT_DASHBOARD_DIR: path\.join\(sandbox/);
  // the tasks file is resolved only through tasksFile(), whose env override wins over the stored real path
  assert.match(main, /tasksFile = \(\) => process\.env\.LIFEBOT_TASKS_FILE \|\|/);
  assert.ok(!/ANANYA-OS/.test(main), 'no real vault path may be hard-coded in main.js');
});

test('typewriter card lists every task, starts a particular one, and the pill has a start list', () => {
  const tw = read('renderer/typewriter.js');
  assert.match(main, /const tasks = currentTasks\(\)\.filter\(\(x\) => x\.isToday\)\.map\(\(x\) => \(\{ id: x\.id, text: x\.text, checked: !!x\.checked \}\)\)/);   // state carries today's tasks
  assert.match(main, /ipcMain\.handle\('tw:start'[\s\S]{0,500}typeof input\.id !== 'string' \|\| !currentTasks\(\)\.some/);        // id validated against the file
  assert.match(main, /ipcMain\.handle\('tw:select'[\s\S]{0,200}typeof id !== 'string'/);
  assert.match(main, /ipcMain\.handle\('tw:miniList', \(_e, open\) => \{ if \(typeof open === 'boolean'\)/);
  assert.match(tw, /api\.start\(undefined, r\.id\)/);
  assert.match(tw, /tm\.t\.taskId/);                                  // the collapsed pill shows the RUNNING task
});

test('floating card lists today only and can remove tasks; removal is validated and refuses a running task', () => {
  assert.match(main, /currentTasks\(\)\.filter\(\(x\) => x\.isToday\)/);
  assert.match(main, /ipcMain\.handle\('tw:remove', \(_e, id\) => removeTaskById\(id\)\)/);
  assert.match(main, /ipcMain\.handle\('tasks:remove', \(_e, id\) => removeTaskById\(id\)\)/);
  const fn = main.slice(main.indexOf('function removeTaskById'), main.indexOf('function tasksPayload'));
  assert.match(fn, /typeof id !== 'string'/);
  assert.match(fn, /pomo\.phase === 'focus'/);
  assert.match(fn, /T\.removeTask\(/);
});

test('proactive nudges are wired to the pure engine, respect settings, never run in test mode and only act in-app', () => {
  assert.match(main, /const Nudges = require\('\.\/lib\/nudges\.js'\)/);
  assert.match(main, /nudges: true, briefings: true, focusMin/);                                  // on by default
  assert.match(main, /typeof patch\.nudges === 'boolean'/);                      // validated setting
  assert.match(main, /function runNudgeCheck[\s\S]{0,120}SMOKE_DIR/);              // never pops up in smoke tests
  assert.match(main, /setInterval\(runNudgeCheck, 60000\)/);
  assert.match(main, /Snooze prompts for 2 hours/);
  const act = main.slice(main.indexOf('function actOnNudge'), main.indexOf('function showNudge'));
  assert.ok(!/writeTasksMarkdown|removeTaskById|child_process|shell\./.test(act), 'a click may only start/select/navigate');
});

test('briefings: Lifebot runs only the fixed task list, never in test mode, with a timeout and no shell', () => {
  assert.match(main, /const Schedule = require\('\.\/lib\/schedule\.js'\)/);
  assert.match(main, /function checkBriefs\(\) \{\s*if \(!store \|\| SMOKE_DIR \|\| briefRunning \|\| settings\(\)\.briefings === false\) return;/);
  const run = main.slice(main.indexOf('function runBrief'), main.indexOf('/** Called every minute'));
  assert.match(run, /!Schedule\.TASKS\.includes\(task\)/);                           // allowlist
  assert.match(run, /\['-m', 'life_agent\.agent\.main', task\]/);                    // fixed argv
  assert.ok(!/shell:\s*true|exec\(|execSync/.test(run), 'no shell');
  assert.match(run, /BRIEF_TIMEOUT_MS/);
  assert.match(main, /ipcMain\.handle\('briefs:run'[\s\S]{0,200}!Schedule\.TASKS\.includes\(task\)/);
  assert.match(main, /ipcMain\.handle\('briefs:read'[\s\S]{0,200}!Schedule\.TASKS\.includes\(task\)/);
  assert.match(main, /typeof patch\.briefings === 'boolean'/);
});

test('preference questions: validated before saving, written next to the briefing notes, only choices from the allowlist', () => {
  assert.match(main, /ipcMain\.handle\('prefs:set', \(_e, input\) => \{\s*const clean = Schedule\.cleanPrefs\(input\)/);
  assert.match(main, /const prefsFile = \(\) => path\.join\(briefsDir\(\), '_preferences\.json'\)/);
  assert.match(read('preload.js'), /prefs: \{ get: invoke\('prefs:get'\), set: invoke\('prefs:set'\) \}/);
});

test('briefings tab never shows an older run\'s text under a newer run\'s label, and the date label follows the clock', () => {
  const app = read('renderer/app.js');
  assert.match(app, /const stampOf = \(b\) => `\$\{b\.note\}\|\$\{b\.at\}`/);
  assert.match(app, /noteStamp\.get\(b\.task\) !== stampOf\(b\)[\s\S]{0,200}api\.briefs\.read\(b\.task\)/);        // re-read when the run changed
  assert.match(app, /setInterval\(paintToday, 60000\)/);
});
