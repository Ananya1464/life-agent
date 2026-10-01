/**
 * Electron bridge for recording focus events via child_process.
 * Exports recordFocusEvent(payload, opts) for use in main process.
 */

const { spawn } = require('child_process');
const path = require('path');

function recordFocusEvent(payload, opts) {
  /**
   * Record a focus event by spawning the CLI tool.
   *
   * payload: {phase, date_iso, task, duration_seconds, session_id}
   * opts: {python, args, cwd, env, timeoutMs}
   *
   * Returns Promise that resolves to {success, code, stderr}.
   * Never rejects. On timeout, kills process and resolves with success=false.
   */
  return new Promise((resolve) => {
    opts = opts || {};

    const pythonExe = opts.python || process.env.LIFE_AGENT_PYTHON || 'python';
    const args = opts.args || ['-m', 'life_agent.events.record_focus_cli'];
    const cwd = opts.cwd;
    const env = opts.env;
    const timeoutMs = opts.timeoutMs || 5000;

    const jsonInput = JSON.stringify(payload);

    let timedOut = false;
    const proc = spawn(pythonExe, args, {
      cwd,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: false
    });

    let stderrOutput = '';

    proc.stderr.on('data', (data) => {
      stderrOutput += data.toString('utf-8');
    });

    const timer = setTimeout(() => {
      timedOut = true;
      try {
        proc.kill();
      } catch (e) {
        // Already terminated
      }
    }, timeoutMs);

    proc.on('close', (code) => {
      clearTimeout(timer);

      if (timedOut) {
        resolve({
          success: false,
          code: -1,
          stderr: 'timeout'
        });
      } else {
        resolve({
          success: code === 0,
          code: code,
          stderr: stderrOutput
        });
      }
    });

    proc.on('error', (err) => {
      clearTimeout(timer);
      resolve({
        success: false,
        code: -1,
        stderr: err.message
      });
    });

    try {
      proc.stdin.write(jsonInput);
      proc.stdin.end();
    } catch (err) {
      clearTimeout(timer);
      resolve({
        success: false,
        code: -1,
        stderr: err.message
      });
    }

    proc.stdin.on('error', (err) => {
      if (!timedOut) {
        clearTimeout(timer);
        resolve({
          success: false,
          code: -1,
          stderr: err.message
        });
      }
    });
  });
}

module.exports = { recordFocusEvent };
