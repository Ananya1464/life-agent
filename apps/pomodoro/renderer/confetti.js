/** Pixel confetti on a full-window canvas. Bursts once, then rains gently while active. */
(function (root) {
  const L = root.PomoLogic;
  let canvas = null;
  let ctx = null;
  let particles = [];
  let active = false;
  let raf = null;
  let last = 0;
  let spawnCarry = 0;

  function frame(now) {
    const dt = last ? now - last : 16;
    last = now;
    if (active) {
      spawnCarry += dt * 0.045;                                  // ~45 pieces per second
      while (spawnCarry >= 1 && particles.length < L.MAX_PARTICLES) {
        particles.push(L.makeParticle(Math.random, canvas.width, false));
        spawnCarry -= 1;
      }
      spawnCarry = Math.min(spawnCarry, 1);
    }
    particles = L.stepParticles(particles, dt, canvas.height);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of particles) {
      ctx.save();
      ctx.translate(Math.round(p.x), Math.round(p.y));
      ctx.rotate(Math.round(p.angle * 4) / 4);                   // coarse steps keep the pixel-art feel
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
      ctx.restore();
    }
    if (active || particles.length) raf = requestAnimationFrame(frame);
    else { raf = null; last = 0; }
  }

  function start() {
    canvas = canvas || document.getElementById('confetti-canvas');
    ctx = ctx || canvas.getContext('2d');
    if (active) return;
    active = true;
    for (let i = 0; i < 90 && particles.length < L.MAX_PARTICLES; i++) particles.push(L.makeParticle(Math.random, canvas.width, true));
    if (!raf) raf = requestAnimationFrame(frame);
  }

  /** Stop spawning; existing pieces finish falling, then the animation loop ends by itself. */
  function stop() { active = false; }

  root.Confetti = { start, stop, count: () => particles.length, isActive: () => active };
}(typeof self !== 'undefined' ? self : this));
