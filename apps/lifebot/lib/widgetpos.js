/**
 * Placement helpers for the floating avocado window (pure; displays are passed in so it is testable).
 * A display is { workArea: { x, y, width, height } } as Electron's screen module reports it.
 */

const MIN_VISIBLE = 48;   // px of the window that must overlap a display to count as reachable

function isVisible(bounds, displays, minVisible = MIN_VISIBLE) {
  if (!bounds || !Number.isFinite(bounds.x) || !Number.isFinite(bounds.y)) return false;
  const w = bounds.width || 266;
  const h = bounds.height || 322;
  return displays.some(({ workArea: a }) => {
    const overlapX = Math.min(bounds.x + w, a.x + a.width) - Math.max(bounds.x, a.x);
    const overlapY = Math.min(bounds.y + h, a.y + a.height) - Math.max(bounds.y, a.y);
    return overlapX >= minVisible && overlapY >= minVisible;
  });
}

/** Default spot: bottom-right of the primary display's work area, with a margin. */
function defaultPosition(primary, size = { width: 266, height: 322 }, margin = 24) {
  const a = primary.workArea;
  return { x: a.x + a.width - size.width - margin, y: a.y + a.height - size.height - margin };
}

/** Saved position if it is still reachable on a connected display, otherwise the default. */
function resolvePosition(saved, displays, primary, size) {
  if (saved && isVisible({ ...saved, ...(size || {}) }, displays)) return { x: Math.round(saved.x), y: Math.round(saved.y) };
  return defaultPosition(primary, size);
}

module.exports = { isVisible, defaultPosition, resolvePosition, MIN_VISIBLE };
