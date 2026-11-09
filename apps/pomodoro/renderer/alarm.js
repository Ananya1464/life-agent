/**
 * Cheerful repeating alarm synthesized with WebAudio (no audio files). It plays until stopped
 * (with a safety cap) and keeps playing when the window is not focused.
 */
(function (root) {
  // [frequency Hz, start s, length s] - a bouncy rising arpeggio followed by a little "yum" pair
  const PHRASE = [
    [523.25, 0.00, 0.14], [659.25, 0.16, 0.14], [783.99, 0.32, 0.14], [1046.5, 0.48, 0.28],
    [783.99, 0.90, 0.12], [1046.5, 1.04, 0.34],
  ];
  const PHRASE_LENGTH_MS = 1700;
  const MAX_PLAY_MS = 120000;       // never ring forever if she walks away

  let ctx = null;
  let loop = null;
  let capTimer = null;
  let phrasesPlayed = 0;

  function context() {
    if (!ctx) {
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function playPhrase() {
    const c = context();
    if (!c) return;
    const now = c.currentTime + 0.02;
    for (const [freq, start, len] of PHRASE) {
      for (const [type, vol] of [['triangle', 0.22], ['square', 0.05]]) {
        const osc = c.createOscillator();
        const gain = c.createGain();
        osc.type = type;
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, now + start);
        gain.gain.exponentialRampToValueAtTime(vol, now + start + 0.015);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + start + len);
        osc.connect(gain).connect(c.destination);
        osc.start(now + start);
        osc.stop(now + start + len + 0.03);
      }
    }
    phrasesPlayed += 1;
  }

  function start() {
    if (loop) return;                 // never stack two alarms
    phrasesPlayed = 0;
    playPhrase();
    loop = setInterval(playPhrase, PHRASE_LENGTH_MS);
    capTimer = setTimeout(stop, MAX_PLAY_MS);
  }

  function stop() {
    if (loop) { clearInterval(loop); loop = null; }
    if (capTimer) { clearTimeout(capTimer); capTimer = null; }
  }

  root.Alarm = {
    start, stop,
    isPlaying: () => loop !== null,
    debug: () => ({ playing: loop !== null, phrasesPlayed, audioState: ctx ? ctx.state : 'none' }),
  };
}(typeof self !== 'undefined' ? self : this));
