/**
 * Client for the Python bridge (life_agent.lifebot.bridge): newline-delimited JSON over stdio.
 * Starts the process lazily, matches responses to requests by id, times requests out, and
 * restarts after a crash on the next request. `spawnFn` is injectable for tests.
 */
const { spawn } = require('node:child_process');
const { EventEmitter } = require('node:events');
const readline = require('node:readline');

const RESTART_BACKOFF_MS = 1500;

class PyBridge extends EventEmitter {
  constructor({ python, cwd, env, args = ['-m', 'life_agent.lifebot.bridge'], spawnFn = spawn }) {
    super();
    this.opts = { python, cwd, env, args, spawnFn };
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.lastStart = 0;
  }

  get online() { return this.proc !== null; }

  start() {
    if (this.proc) return;
    const { python, cwd, env, args, spawnFn } = this.opts;
    this.lastStart = Date.now();
    const proc = spawnFn(python, args, { cwd, env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    this.proc = proc;

    readline.createInterface({ input: proc.stdout }).on('line', (line) => this._onLine(line));
    readline.createInterface({ input: proc.stderr }).on('line', (line) => this.emit('log', line));
    proc.stdin.on('error', () => { /* surfaced through exit/error below */ });
    proc.on('error', (err) => this._onDown(err));
    proc.on('exit', (code) => this._onDown(new Error(`Python bridge exited (code ${code})`)));
    this.emit('status', 'online');
  }

  _onDown(err) {
    if (!this.proc) return;
    this.proc = null;
    for (const [, p] of this.pending) { clearTimeout(p.timer); p.reject(err); }
    this.pending.clear();
    this.emit('status', 'offline');
  }

  _onLine(line) {
    let msg;
    try { msg = JSON.parse(line); } catch (_) { this.emit('log', `non-protocol output: ${line}`); return; }
    const p = this.pending.get(msg.id);
    if (!p) return;
    this.pending.delete(msg.id);
    clearTimeout(p.timer);
    if (msg.error) p.reject(new Error(msg.error));
    else p.resolve(msg.result);
  }

  request(method, params = {}, timeoutMs = 30000) {
    if (!this.proc) {
      const since = Date.now() - this.lastStart;
      if (since < RESTART_BACKOFF_MS) {
        return Promise.reject(new Error('Python bridge is restarting, try again in a moment'));
      }
      this.start();
    }
    return new Promise((resolve, reject) => {
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Python bridge timed out on '${method}'`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.proc.stdin.write(JSON.stringify({ id, method, params }) + '\n');
      } catch (err) {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(err);
      }
    });
  }

  stop() {
    const proc = this.proc;
    if (!proc) return;
    try { proc.stdin.end(); } catch (_) { /* ignore */ }
    try { proc.kill(); } catch (_) { /* ignore */ }
  }
}

module.exports = { PyBridge };
