/**
 * Pomodoro state machine (pure). The caller owns the clock: every function takes `now` (ms).
 * Time is measured from timestamps, so throttled timers or sleep never make the timer drift.
 *
 * phases: idle | focus | break.   focus/break can be paused (`runningSince === null`).
 * Functions return { state, events }; events: started | completed | abandoned | break_done.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Pomodoro = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  const DEFAULTS = { focusMin: 25, breakMin: 5 };

  const idle = () => ({ phase: 'idle', task: null, runId: null, durationMs: 0, elapsedMs: 0, runningSince: null });

  function elapsed(s, now) {
    return s.elapsedMs + (s.runningSince !== null ? Math.max(0, now - s.runningSince) : 0);
  }

  function remainingMs(s, now) {
    return s.phase === 'idle' ? 0 : Math.max(0, s.durationMs - elapsed(s, now));
  }

  function abandonEvent(s, now) {
    return { type: 'abandoned', task: s.task, runId: s.runId, durationSec: Math.round(elapsed(s, now) / 1000) };
  }

  function start(s, task, now, cfg) {
    const c = { ...DEFAULTS, ...(cfg || {}) };
    const events = [];
    if (s.phase === 'focus') events.push(abandonEvent(s, now)); // starting another task ends the current run
    const next = {
      phase: 'focus', task: task ? { id: task.id, text: task.text } : null,
      runId: String(now), durationMs: c.focusMin * 60000, elapsedMs: 0, runningSince: now,
    };
    events.push({ type: 'started', task: next.task, runId: next.runId });
    return { state: next, events };
  }

  function pause(s, now) {
    if (s.phase === 'idle' || s.runningSince === null) return { state: s, events: [] };
    return { state: { ...s, elapsedMs: elapsed(s, now), runningSince: null }, events: [] };
  }

  function resume(s, now) {
    if (s.phase === 'idle' || s.runningSince !== null) return { state: s, events: [] };
    return { state: { ...s, runningSince: now }, events: [] };
  }

  /** Stop: abandons a focus run (recording elapsed time); just ends a break. */
  function stop(s, now) {
    if (s.phase === 'focus') return { state: idle(), events: [abandonEvent(s, now)] };
    return { state: idle(), events: [] };
  }

  /** Advance the clock: finishes focus (-> break) or break (-> idle) when time is up. */
  function tick(s, now, cfg) {
    const c = { ...DEFAULTS, ...(cfg || {}) };
    if (s.phase === 'idle' || s.runningSince === null || remainingMs(s, now) > 0) return { state: s, events: [] };
    if (s.phase === 'focus') {
      const done = { type: 'completed', task: s.task, runId: s.runId, durationSec: Math.round(s.durationMs / 1000) };
      return {
        state: { phase: 'break', task: s.task, runId: s.runId, durationMs: c.breakMin * 60000, elapsedMs: 0, runningSince: now },
        events: [done],
      };
    }
    return { state: idle(), events: [{ type: 'break_done', task: s.task, runId: s.runId }] };
  }

  const MAX_TOTAL_MS = 180 * 60000;   // a session can never be stretched past 3 hours
  const MIN_LEFT_MS = 60000;          // shortening always leaves at least a minute

  /** Change the length of the running focus session by deltaMs (works while paused too). */
  function adjust(s, deltaMs, now) {
    if (s.phase !== 'focus') return { state: s, events: [] };
    const next = Math.min(MAX_TOTAL_MS, Math.max(elapsed(s, now) + MIN_LEFT_MS, s.durationMs + deltaMs));
    return { state: { ...s, durationMs: next }, events: [] };
  }

  /** Snapshot for the UI. */
  function view(s, now) {
    return {
      phase: s.phase, task: s.task, running: s.runningSince !== null && s.phase !== 'idle',
      remainingMs: remainingMs(s, now), durationMs: s.durationMs, runId: s.runId,
    };
  }

  function format(ms) {
    const total = Math.ceil(ms / 1000);
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  }

  return { DEFAULTS, idle, start, pause, resume, stop, tick, adjust, view, remainingMs, format, MAX_TOTAL_MS };
}));
