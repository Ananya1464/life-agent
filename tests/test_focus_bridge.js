/**
 * Tests for focus_bridge.js - Node.js subprocess handling
 */

const { recordFocusEvent } = require('../apps/pomodoro/focus_bridge');
const path = require('path');
const fs = require('fs');
const os = require('os');

async function runTests() {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'focus-bridge-'));
  const repoRoot = path.resolve(__dirname, '..');
  const pythonExe = process.env.LIFE_AGENT_PYTHON || 'python';

  console.log(`Testing in: ${tempDir}`);

  let passed = 0;
  let failed = 0;

  // Test 1: Event lands in temp data/events.jsonl with correct content
  try {
    const result = await recordFocusEvent(
      {
        phase: 'started',
        date_iso: '2026-09-21',
        task: 'Test task',
        session_id: 'test-1'
      },
      {
        python: pythonExe,
        args: ['-m', 'life_agent.events.record_focus_cli'],
        cwd: tempDir,
        env: { ...process.env, PYTHONPATH: path.join(repoRoot, 'src') },
        timeoutMs: 5000
      }
    );

    const eventsFile = path.join(tempDir, 'data', 'events.jsonl');
    if (result.success && fs.existsSync(eventsFile)) {
      const content = fs.readFileSync(eventsFile, 'utf-8').trim();
      const event = JSON.parse(content);
      if (event.kind === 'focus_started' && event.task === 'Test task' && event.source === 'pomodoro_app') {
        console.log('✓ T1: Event written with correct content');
        passed++;
      } else {
        console.log('✗ T1: Event content incorrect');
        console.log('  Event:', event);
        failed++;
      }
    } else {
      console.log('✗ T1: Event not written');
      console.log('  Result code:', result.code);
      console.log('  Result stderr:', result.stderr);
      failed++;
    }
  } catch (err) {
    console.log('✗ T1: Exception -', err.message);
    failed++;
  }

  // Test 2: Non-zero exit -> {success: false}
  try {
    const result = await recordFocusEvent(
      { phase: 'invalid', date_iso: '2026-09-21', task: 'Test', session_id: 's1' },
      {
        python: pythonExe,
        args: ['-m', 'life_agent.events.record_focus_cli'],
        cwd: tempDir,
        env: { ...process.env, PYTHONPATH: path.join(repoRoot, 'src') },
        timeoutMs: 5000
      }
    );

    if (!result.success && result.code !== 0) {
      console.log('✓ T2: Non-zero exit handled correctly');
      passed++;
    } else {
      console.log('✗ T2: Non-zero exit not handled');
      console.log('  Result code:', result.code);
      console.log('  Result success:', result.success);
      failed++;
    }
  } catch (err) {
    console.log('✗ T2: Exception -', err.message);
    failed++;
  }

  // Test 3: Timeout handling
  try {
    const result = await recordFocusEvent(
      { phase: 'started', date_iso: '2026-09-21', task: 'Test', session_id: 's1' },
      {
        python: process.execPath,
        args: ['-e', 'setTimeout(()=>{},10000)'],
        cwd: tempDir,
        timeoutMs: 500
      }
    );

    if (!result.success && result.stderr === 'timeout') {
      console.log('✓ T3: Timeout handled correctly');
      passed++;
    } else {
      console.log('✗ T3: Timeout not handled');
      console.log('  Result code:', result.code);
      console.log('  Result stderr:', result.stderr);
      failed++;
    }
  } catch (err) {
    console.log('✗ T3: Exception -', err.message);
    failed++;
  }

  // Test 4: Special chars intact in event
  try {
    const specialTask = 'Test & | % " \' café ☕';
    const result = await recordFocusEvent(
      {
        phase: 'started',
        date_iso: '2026-09-21',
        task: specialTask,
        session_id: 'test-special'
      },
      {
        python: pythonExe,
        args: ['-m', 'life_agent.events.record_focus_cli'],
        cwd: tempDir,
        env: { ...process.env, PYTHONPATH: path.join(repoRoot, 'src') },
        timeoutMs: 5000
      }
    );

    const eventsFile = path.join(tempDir, 'data', 'events.jsonl');
    const lines = fs.readFileSync(eventsFile, 'utf-8').trim().split('\n');
    const lastEvent = JSON.parse(lines[lines.length - 1]);

    if (result.success && lastEvent.task === specialTask) {
      console.log('✓ T4: Special chars intact in event');
      passed++;
    } else {
      console.log('✗ T4: Special chars not preserved');
      console.log('  Result code:', result.code);
      console.log('  Result stderr:', result.stderr);
      console.log('  Expected task:', specialTask);
      console.log('  Got task:', lastEvent.task);
      failed++;
    }
  } catch (err) {
    console.log('✗ T4: Exception -', err.message);
    failed++;
  }

  console.log(`\nResults: ${passed} PASSED, ${failed} FAILED`);

  // Cleanup
  fs.rmSync(tempDir, { recursive: true });

  return failed === 0;
}

// Run tests
runTests().then(success => process.exit(success ? 0 : 1));
