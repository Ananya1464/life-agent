/**
 * Pure helpers for the avocado timer (no DOM, no Electron): time maths, the log line, and the
 * confetti particle simulation. Kept separate so they can be unit tested.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PomoLogic = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  const pad2 = (n) => String(n).padStart(2, '0');

  /** MM:SS from milliseconds (floors; never negative). */
  function formatMMSS(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    return `${pad2(Math.floor(total / 60))}:${pad2(total % 60)}`;
  }

  /** Minutes input -> an integer in [1, 180]; anything unusable becomes 25. */
  function clampMinutes(value) {
    const n = parseInt(value, 10);
    if (Number.isNaN(n) || n < 1) return 25;
    return Math.min(n, 180);
  }

  /** Remaining time from wall-clock timestamps, so sleep or throttled timers never cause drift. */
  function remainingMs(endTime, now) {
    return endTime - now;
  }

  function formatTimestamp(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  /** Same markdown line the app has always written. */
  function buildLogLine({ date, plannedMinutes, result, elapsedMs, task }) {
    const elapsed = result === 'completed' ? `${plannedMinutes}:00` : formatMMSS(elapsedMs);
    const mark = result === 'completed' ? '[x]' : '[ ]';
    return `- ${mark} ${formatTimestamp(date)} — ${plannedMinutes} min planned, ${elapsed} elapsed — "${task || '(no task)'}" — ${result}`;
  }

  // ---------------------------------------------------------------- confetti
  const CONFETTI_COLORS = ['#ff6584', '#ffd23f', '#72bd27', '#a9e23d', '#ff9f43', '#c58bff', '#ffffff'];
  const GRAVITY = 520;          // px / s^2
  const MAX_PARTICLES = 220;    // hard cap so a long alarm can never grow without bound

  /** One pixel-square particle. `rand` is injectable (tests pass a deterministic one). */
  function makeParticle(rand, width, burst) {
    const size = 4 + Math.floor(rand() * 3) * 2;                      // 4, 6 or 8 px: crisp pixel squares
    return {
      x: burst ? width / 2 + (rand() - 0.5) * 60 : rand() * width,
      y: burst ? 150 : -10,
      vx: burst ? (rand() - 0.5) * 420 : (rand() - 0.5) * 60,
      vy: burst ? -(180 + rand() * 360) : 40 + rand() * 90,
      size,
      color: CONFETTI_COLORS[Math.floor(rand() * CONFETTI_COLORS.length)],
      spin: (rand() - 0.5) * 6,
      angle: rand() * Math.PI,
    };
  }

  /** Advance particles by dt ms; drops the ones that fell below `height`. */
  function stepParticles(list, dtMs, height) {
    const dt = Math.min(dtMs, 64) / 1000;                              // clamp: a stalled frame must not teleport them
    const out = [];
    for (const p of list) {
      const vy = p.vy + GRAVITY * dt;
      const next = { ...p, x: p.x + p.vx * dt, y: p.y + vy * dt, vy, angle: p.angle + p.spin * dt, vx: p.vx * (1 - 0.6 * dt) };
      if (next.y - next.size < height) out.push(next);
    }
    return out;
  }

  return { formatMMSS, clampMinutes, remainingMs, formatTimestamp, buildLogLine, makeParticle, stepParticles, CONFETTI_COLORS, MAX_PARTICLES };
}));
