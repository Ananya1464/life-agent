/* Retro sound effects synthesized with WebAudio (square waves). No audio files; mute-able. */
(function (root) {
  let ctx = null;
  let enabled = true;

  // [frequency Hz, start s, duration s]
  const SOUNDS = {
    click: [[880, 0, 0.04]],
    start: [[392, 0, 0.08], [523, 0.08, 0.14]],
    done: [[523, 0, 0.08], [659, 0.08, 0.08], [784, 0.16, 0.16]],
    diamond: [[988, 0, 0.07], [1319, 0.07, 0.16]],
    levelup: [[523, 0, 0.1], [659, 0.1, 0.1], [784, 0.2, 0.1], [1047, 0.3, 0.3]],
    end: [[784, 0, 0.1], [659, 0.1, 0.1], [523, 0.2, 0.22]],
  };

  function context() {
    if (!ctx) {
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function play(name) {
    if (!enabled || !SOUNDS[name]) return;
    const c = context();
    if (!c) return;
    const now = c.currentTime;
    for (const [freq, start, dur] of SOUNDS[name]) {
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = 'square';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + start);
      gain.gain.exponentialRampToValueAtTime(0.07, now + start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + start + dur);
      osc.connect(gain).connect(c.destination);
      osc.start(now + start);
      osc.stop(now + start + dur + 0.02);
    }
  }

  root.Sfx = { play, setEnabled: (v) => { enabled = !!v; }, isEnabled: () => enabled, NAMES: Object.keys(SOUNDS) };
}(typeof self !== 'undefined' ? self : this));
