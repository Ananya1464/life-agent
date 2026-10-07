/* Pixel sprites as crisp SVG. Grids/palettes mirror src/life_agent/pixel.py (a test keeps them equal). */
(function (root) {
  const GEM = [
    '...oooooo...',
    '..owllllmo..',
    '.owllllmmmo.',
    'olllllmmmmdo',
    'ommmmmmmmddo',
    '.ommmmmmddo.',
    '..ommmmddo..',
    '...ommddo...',
    '....omdo....',
    '.....oo.....',
  ];
  const FLAME = [
    '....oo....',
    '...ooyo...',
    '..ooyyoo..',
    '..oyyyyoo.',
    '.ooyyryyo.',
    '.oyyrrryo.',
    '.oyrrrrro.',
    '.oyrrwrro.',
    '..oyrwro..',
    '...oyyo...',
    '....oo....',
  ];
  const CHEST = [
    '.oooooooooo.',
    'obbbbbbbbbbo',
    'obddddddddbo',
    'oooooggooooo',
    'obbbbggbbbbo',
    'obddbggbddbo',
    'obbbbbbbbbbo',
    'oooooooooooo',
  ];
  const SPRITES = { gem: GEM, flame: FLAME, chest: CHEST };
  const PALETTES = {
    gem: { o: '#14451f', l: '#e8ffd0', m: '#72bd27', d: '#397d22', w: '#ffffff' },
    flame: { o: '#5a1200', y: '#ffd23f', r: '#ff7a1a', w: '#fff6c2' },
    chest: { o: '#3a1f0a', b: '#ffbf3f', d: '#c27d12', g: '#fff3b0' },
  };
  const NS = 'http://www.w3.org/2000/svg';

  /** Build an <svg> element for a sprite (merged horizontal runs, crisp edges). */
  function sprite(name, scale) {
    const grid = SPRITES[name];
    const palette = PALETTES[name];
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${grid[0].length} ${grid.length}`);
    svg.setAttribute('width', String(grid[0].length * (scale || 4)));
    svg.setAttribute('height', String(grid.length * (scale || 4)));
    svg.setAttribute('shape-rendering', 'crispEdges');
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('sprite');
    grid.forEach((row, y) => {
      let x = 0;
      while (x < row.length) {
        const ch = row[x];
        if (ch === '.') { x += 1; continue; }
        let run = x;
        while (run < row.length && row[run] === ch) run += 1;
        const r = document.createElementNS(NS, 'rect');
        r.setAttribute('x', String(x)); r.setAttribute('y', String(y));
        r.setAttribute('width', String(run - x)); r.setAttribute('height', '1');
        r.setAttribute('fill', palette[ch]);
        svg.appendChild(r);
        x = run;
      }
    });
    return svg;
  }

  root.Pixel = { sprite, SPRITES, PALETTES };
}(typeof self !== 'undefined' ? self : this));
