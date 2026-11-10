const test = require('node:test');
const assert = require('node:assert/strict');
const W = require('../lib/widgetpos.js');

const primary = { workArea: { x: 0, y: 0, width: 1920, height: 1040 } };
const second = { workArea: { x: 1920, y: 0, width: 1280, height: 1024 } };

test('a window on a connected display is visible', () => {
  assert.equal(W.isVisible({ x: 100, y: 100, width: 266, height: 322 }, [primary]), true);
  assert.equal(W.isVisible({ x: 2000, y: 50, width: 266, height: 322 }, [primary, second]), true);
});

test('off-screen, barely-overlapping and invalid positions are not visible', () => {
  assert.equal(W.isVisible({ x: 5000, y: 100 }, [primary]), false);
  assert.equal(W.isVisible({ x: -250, y: 100, width: 266, height: 322 }, [primary]), false);   // only 16px on screen
  assert.equal(W.isVisible({ x: 100, y: 1030, width: 266, height: 322 }, [primary]), false);   // only 10px on screen
  assert.equal(W.isVisible(null, [primary]), false);
  assert.equal(W.isVisible({ x: NaN, y: 0 }, [primary]), false);
});

test('a position saved on a disconnected monitor falls back to the primary display', () => {
  const saved = { x: 2200, y: 100 };
  assert.deepEqual(W.resolvePosition(saved, [primary, second], primary), { x: 2200, y: 100 });
  const recovered = W.resolvePosition(saved, [primary], primary);                 // second monitor unplugged
  assert.deepEqual(recovered, W.defaultPosition(primary));
  assert.equal(W.isVisible({ ...recovered, width: 266, height: 322 }, [primary]), true);
});

test('no saved position uses the bottom-right default inside the work area', () => {
  const pos = W.resolvePosition(null, [primary], primary);
  assert.deepEqual(pos, { x: 1920 - 266 - 24, y: 1040 - 322 - 24 });
});

test('saved coordinates are rounded to whole pixels', () => {
  assert.deepEqual(W.resolvePosition({ x: 10.6, y: 20.2 }, [primary], primary), { x: 11, y: 20 });
});
