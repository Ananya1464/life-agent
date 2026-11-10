"""Obsidian dashboard in a pixel-game style, rendered as inline SVG/HTML (no plugins required).

Reads the local event store (focus sessions and task outcomes), so it works offline. A fixed
"crystal cave" palette is used, so it looks the same in light and dark Obsidian themes.

    python -m life_agent.obsidian.dashboard [--out DIR]
"""
from __future__ import annotations

import argparse
import html
import math
import os
import sys
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from life_agent import dates, gamification
from life_agent.events import queries, store
from life_agent.pixel import pixel_svg

DEFAULT_DIR = Path.home() / "OneDrive" / "Desktop" / "ananya" / "ANANYA-OS" / "Dashboard"
NOTE_NAME = "Life Agent Dashboard.md"

# Warm avocado-and-typewriter palette (matches the app and the floating widgets)
BG, PANEL, EDGE, SHADOW = "#2a1b12", "#3a271a", "#8a5a2b", "#140c07"
INK, MUTED, GRIDC = "#F5EDE0", "#c9b9a3", "#5a3d2a"
CYAN, MAGENTA, GOLD, GREEN = "#a9e23d", "#ff6584", "#ffd23f", "#72bd27"
PURPLE, RED, ORANGE = "#c58bff", "#C1443C", "#c38a42"
HEAT = ["#3a271a", "#8a5a2b", "#c38a42", "#ff6584", "#ffd23f"]
PIXEL_FONT = "'Press Start 2P','Courier New',ui-monospace,monospace"
BODY_FONT = "Consolas,'Courier New',ui-monospace,monospace"

FOCUS_DAYS = 14
OUTCOME_DAYS = 30
TREND_DAYS = 28
HEAT_DAYS = 60

TASK_OUTCOMES = [
    ("task_completed", "Completed", GREEN),
    ("task_partial", "Partial", GOLD),
    ("task_not_now", "Not now", CYAN),
    ("task_skipped", "Skipped", MUTED),
    ("task_forgot", "Forgot", ORANGE),
    ("task_never_started", "Never started", RED),
    ("task_no_response", "No response", PURPLE),
]


def dashboard_dir() -> Path:
    return Path(os.environ.get("LIFE_AGENT_DASHBOARD_DIR") or DEFAULT_DIR)


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _svg(width: int, height: int, body: str, chart: str = "") -> str:
    tag = f' data-chart="{chart}"' if chart else ""
    return (f'<svg{tag} viewBox="0 0 {width} {height}" width="100%" shape-rendering="crispEdges" '
            f'style="max-width:{width}px;height:auto;font-family:{BODY_FONT}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">{body}</svg>')


def _empty(width: int, height: int, message: str, chart: str = "") -> str:
    return _svg(width, height, f'<text x="{width // 2}" y="{height // 2}" text-anchor="middle" '
                f'style="fill:{MUTED};font-size:13px">{_esc(message)}</text>', chart)


def _nice_max(value: float) -> float:
    if value <= 0:
        return 30.0
    for step in (30, 60, 90, 120, 180, 240, 360, 480):
        if value <= step:
            return float(step)
    return float(math.ceil(value / 120) * 120)


# ----------------------------------------------------------------------------- charts
def stacked_bars(days: list[dict], width: int = 640, height: int = 230) -> str:
    """days: [{date, completed_min, stopped_min}] drawn as square-edged blocks."""
    if not any(d["completed_min"] + d["stopped_min"] for d in days):
        return _empty(width, 120, "No focus sessions in this period yet", "focus")
    left, right, top, bottom = 40, 8, 12, 30
    pw, ph = width - left - right, height - top - bottom
    ymax = _nice_max(max(d["completed_min"] + d["stopped_min"] for d in days))
    slot = pw / len(days)
    bw = max(4, int(slot * 0.66))
    parts = []
    for frac in (0, 0.5, 1):
        y = round(top + ph - ph * frac)
        parts.append(f'<line x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" '
                     f'style="stroke:{GRIDC};stroke-width:2;stroke-dasharray:4 4"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 4}" text-anchor="end" style="fill:{MUTED};font-size:10px">'
                     f'{round(ymax * frac)}m</text>')
    for i, d in enumerate(days):
        x = round(left + i * slot + (slot - bw) / 2)
        c_h, s_h = round(ph * d["completed_min"] / ymax), round(ph * d["stopped_min"] / ymax)
        title = (f'{d["date"].strftime("%b %d")}: {round(d["completed_min"])} min completed, '
                 f'{round(d["stopped_min"])} min stopped early')
        parts.append(f'<g><title>{_esc(title)}</title>')
        if c_h:
            parts.append(f'<rect x="{x}" y="{top + ph - c_h}" width="{bw}" height="{c_h}" '
                         f'style="fill:{GREEN};stroke:{SHADOW};stroke-width:2"/>')
        if s_h:
            parts.append(f'<rect x="{x}" y="{top + ph - c_h - s_h}" width="{bw}" height="{s_h}" '
                         f'style="fill:{ORANGE};stroke:{SHADOW};stroke-width:2"/>')
        parts.append('</g>')
        if i % 2 == 0 or len(days) <= 8:
            parts.append(f'<text x="{x + bw // 2}" y="{height - 10}" text-anchor="middle" '
                         f'style="fill:{MUTED};font-size:10px">{d["date"].strftime("%m-%d")}</text>')
    return _svg(width, height, "".join(parts), "focus")


def _pie_svg(items: list[tuple[str, float, str]], center_label: str, chart: str = "", n: int = 23, cell: int = 8) -> str:
    """The pixel donut alone, as an <svg> string. items must already be filtered to value > 0."""
    total = sum(v for _, v, _ in items)
    radius, hole = n / 2, n / 2 * 0.46
    bounds, acc = [], 0.0
    for _, value, _ in items:
        acc += value / total
        bounds.append(acc)
    cells = defaultdict(list)       # segment index -> [(x, y)]
    for y in range(n):
        for x in range(n):
            dx, dy = x + 0.5 - radius, y + 0.5 - radius
            dist = math.hypot(dx, dy)
            if dist > radius or dist < hole:
                continue
            frac = (math.atan2(dx, -dy) % (2 * math.pi)) / (2 * math.pi)   # clockwise from the top
            seg = next((i for i, b in enumerate(bounds) if frac < b), len(items) - 1)
            cells[seg].append((x, y))
    parts = []
    for i, (label, value, colour) in enumerate(items):
        rects = "".join(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}"/>' for x, y in cells[i])
        parts.append(f'<g style="fill:{colour}"><title>{_esc(label)}: {int(value)} ({round(100 * value / total)}%)'
                     f'</title>{rects}</g>')
    size = n * cell
    parts.append(f'<text x="{size // 2}" y="{size // 2 + 2}" text-anchor="middle" style="fill:{INK};'
                 f'font-size:22px;font-weight:700;font-family:{PIXEL_FONT}">{int(total)}</text>')
    parts.append(f'<text x="{size // 2}" y="{size // 2 + 20}" text-anchor="middle" style="fill:{MUTED};'
                 f'font-size:10px">{_esc(center_label)}</text>')
    return _svg(size, size, "".join(parts), chart)


def pixel_pie(items: list[tuple[str, float, str]], center_label: str = "total", chart: str = "",
              n: int = 23, cell: int = 8) -> str:
    """A donut drawn as a grid of square cells, plus a legend. items: [(label, value, colour)]."""
    items = [(label, value, colour) for label, value, colour in items if value > 0]
    total = sum(v for _, v, _ in items)
    if not total:
        return _empty(260, 120, "No data in this period yet", chart)
    size = n * cell
    legend = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:5px 0;font-size:13px;color:{INK}">'
        f'<span style="width:12px;height:12px;background:{colour};display:inline-block;border:2px solid {SHADOW}">'
        f'</span><span>{_esc(label)}</span><span style="color:{MUTED};margin-left:auto">{int(value)}</span></div>'
        for label, value, colour in items)
    return (f'<div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">'
            f'<div style="width:{size}px;flex:0 0 auto">{_pie_svg(items, center_label, chart, n, cell)}</div>'
            f'<div style="flex:1 1 130px;min-width:130px">{legend}</div></div>')


def line_chart(points: list[tuple[date, float | None]], width: int = 640, height: int = 210,
               ymax: float = 100.0, unit: str = "%") -> str:
    """Stepped line (retro look) with square markers and a dashed 7-point moving average."""
    present = [(i, v) for i, (_, v) in enumerate(points) if v is not None]
    if len(present) < 2:
        return _empty(width, 120, "Need at least 2 days of data for a trend", "trend")
    left, right, top, bottom = 40, 12, 12, 28
    pw, ph = width - left - right, height - top - bottom
    n = len(points)
    xs = lambda i: round(left + (pw * i / (n - 1) if n > 1 else pw / 2))
    ys = lambda v: round(top + ph - ph * min(max(v, 0), ymax) / ymax)
    parts = []
    for frac in (0, 0.5, 1):
        y = round(top + ph - ph * frac)
        parts.append(f'<line x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" '
                     f'style="stroke:{GRIDC};stroke-width:2;stroke-dasharray:4 4"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 4}" text-anchor="end" style="fill:{MUTED};font-size:10px">'
                     f'{round(ymax * frac)}{unit}</text>')
    segments, current = [], []
    for i, (_, v) in enumerate(points):
        if v is None:
            if current:
                segments.append(current)
            current = []
        else:
            current.append((xs(i), ys(v)))
    if current:
        segments.append(current)
    for seg in segments:
        if len(seg) > 1:
            path = [f"M{seg[0][0]},{seg[0][1]}"]
            for (x0, y0), (x1, y1) in zip(seg, seg[1:]):
                path.append(f"H{x1}V{y1}")                         # step: horizontal then vertical
            parts.append(f'<path d="{"".join(path)}" fill="none" style="stroke:{CYAN};stroke-width:3"/>')
    avg = []
    for k in range(len(present)):
        window = [v for _, v in present[max(0, k - 6):k + 1]]
        avg.append(f"{xs(present[k][0])},{ys(sum(window) / len(window))}")
    parts.append(f'<polyline points="{" ".join(avg)}" fill="none" '
                 f'style="stroke:{GOLD};stroke-width:2;stroke-dasharray:6 4"/>')
    for i, v in present:
        parts.append(f'<rect x="{xs(i) - 4}" y="{ys(v) - 4}" width="8" height="8" style="fill:{MAGENTA};'
                     f'stroke:{SHADOW};stroke-width:2"><title>{points[i][0].strftime("%b %d")}: {round(v)}{unit}</title></rect>')
    for i in range(0, n, max(1, n // 7)):
        parts.append(f'<text x="{xs(i)}" y="{height - 8}" text-anchor="middle" '
                     f'style="fill:{MUTED};font-size:10px">{points[i][0].strftime("%m-%d")}</text>')
    return _svg(width, height, "".join(parts), "trend")


def _heat_colour(minutes: float, peak: float) -> str:
    if not minutes:
        return HEAT[0]
    level = 1 + min(3, int(4 * (minutes / peak - 1e-9)))              # 4 discrete levels above "none"
    return HEAT[level]


def heatmap(matrix: list[list[float]], width: int = 640) -> str:
    """matrix[weekday 0=Mon][hour] -> focus minutes, in five discrete colour levels."""
    peak = max((v for row in matrix for v in row), default=0)
    if not peak:
        return _empty(width, 120, "No focus time recorded yet", "heat")
    left, top, gap = 36, 18, 2
    cell = int((width - left) / 24 - gap)
    height = top + 7 * (cell + gap) + 4
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    parts = []
    for h in range(0, 24, 3):
        parts.append(f'<text x="{left + h * (cell + gap) + cell // 2}" y="11" text-anchor="middle" '
                     f'style="fill:{MUTED};font-size:10px">{h:02d}</text>')
    for d, row in enumerate(matrix):
        y = top + d * (cell + gap)
        parts.append(f'<text x="{left - 6}" y="{y + cell // 2 + 4}" text-anchor="end" '
                     f'style="fill:{MUTED};font-size:10px">{names[d]}</text>')
        for h, minutes in enumerate(row):
            x = left + h * (cell + gap)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                         f'style="fill:{_heat_colour(minutes, peak)}"><title>{names[d]} {h:02d}:00 - '
                         f'{round(minutes)} min</title></rect>')
    return _svg(width, int(height), "".join(parts), "heat")


# ----------------------------------------------------------------------------- data
def _all_sessions(events: list[dict], start: date, end: date) -> list[dict]:
    sessions, day = [], start
    while day <= end:
        sessions.extend(queries.sessions_from_events(events, day.isoformat()))
        day += timedelta(days=1)
    return sessions


def _local_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(dates.TZ)
    except ValueError:
        return None


def collect(events: list[dict], today: date) -> dict:
    """All numbers the dashboard needs, computed from raw events."""
    focus_start = today - timedelta(days=FOCUS_DAYS - 1)
    sessions = _all_sessions(events, today - timedelta(days=max(OUTCOME_DAYS, HEAT_DAYS) - 1), today)

    per_day = defaultdict(lambda: {"completed_min": 0.0, "stopped_min": 0.0, "completed": 0, "finished": 0})
    for s in sessions:
        if s["status"] not in ("completed", "abandoned"):
            continue
        row = per_day[s["date"]]
        minutes = (s.get("duration_seconds") or 0) / 60
        row["finished"] += 1
        if s["status"] == "completed":
            row["completed_min"] += minutes
            row["completed"] += 1
        else:
            row["stopped_min"] += minutes

    focus_days = [{"date": focus_start + timedelta(days=i),
                   **per_day[(focus_start + timedelta(days=i)).isoformat()]}
                  for i in range(FOCUS_DAYS)]

    outcome_start = (today - timedelta(days=OUTCOME_DAYS - 1)).isoformat()
    session_counts = Counter(s["status"] for s in sessions if s["date"] >= outcome_start)
    task_counts = Counter(e["kind"] for e in events
                          if e.get("kind") in {k for k, _, _ in TASK_OUTCOMES}
                          and outcome_start <= (e.get("date") or "") <= today.isoformat())

    planned, done = Counter(), Counter()
    for e in events:
        d = e.get("date") or ""
        if e.get("kind") == "task_planned":
            planned[d] += 1
        elif e.get("kind") == "task_completed":
            done[d] += 1
    trend = []
    for i in range(TREND_DAYS):
        day = today - timedelta(days=TREND_DAYS - 1 - i)
        iso = day.isoformat()
        trend.append((day, min(100.0, 100.0 * done[iso] / planned[iso]) if planned[iso] else None))

    heat = [[0.0] * 24 for _ in range(7)]
    heat_start = (today - timedelta(days=HEAT_DAYS - 1)).isoformat()
    for s in sessions:
        dt = _local_dt(s.get("start"))
        if dt and s["status"] in ("completed", "abandoned") and s["date"] >= heat_start:
            heat[dt.weekday()][dt.hour] += (s.get("duration_seconds") or 0) / 60

    week_rows = [per_day[(today - timedelta(days=i)).isoformat()] for i in range(7)]
    game = gamification.compute(events, today)
    return {
        "today": today,
        "focus_days": focus_days,
        "session_counts": session_counts,
        "task_counts": task_counts,
        "trend": trend,
        "heat": heat,
        "game": game,
        "kpi": {
            "today_min": round(per_day[today.isoformat()]["completed_min"] + per_day[today.isoformat()]["stopped_min"]),
            "week_min": round(sum(r["completed_min"] + r["stopped_min"] for r in week_rows)),
            "week_sessions": sum(r["completed"] for r in week_rows),
            "week_finished": sum(r["finished"] for r in week_rows),
            "streak": game["streak"],
            "tasks_today": done[today.isoformat()],
            "planned_today": planned[today.isoformat()],
        },
    }


# ----------------------------------------------------------------------------- note
def _frame(inner: str, extra: str = "") -> str:
    """Chunky bevelled panel: thick border, inner dark line, hard drop shadow."""
    return (f'<div style="background:{PANEL};border:4px solid {EDGE};border-radius:0;'
            f'box-shadow:inset 0 0 0 2px {BG},6px 6px 0 {SHADOW};padding:14px 16px;{extra}">{inner}</div>')


def _card(title: str, body: str, subtitle: str = "") -> str:
    sub = f'<div style="color:{MUTED};font-size:12px;margin:2px 0 10px">{_esc(subtitle)}</div>' if subtitle else ""
    head = (f'<div style="font-family:{PIXEL_FONT};font-size:11px;letter-spacing:.04em;color:{CYAN};'
            f'text-transform:uppercase;margin-bottom:4px">{pixel_svg("gem", 2)} {_esc(title)}</div>')
    return _frame(head + sub + body)


def _stat(label: str, value: str, hint: str, colour: str) -> str:
    return _frame(
        f'<div style="font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.06em">{_esc(label)}</div>'
        f'<div style="font-family:{PIXEL_FONT};font-size:20px;color:{colour};margin:8px 0 6px">{_esc(value)}</div>'
        f'<div style="font-size:11px;color:{MUTED}">{_esc(hint)}</div>',
        f"border-left:8px solid {colour};padding:12px 14px;")


def _xp_bar(pct: int, blocks: int = 20) -> str:
    filled = round(blocks * pct / 100)
    cells = "".join(
        f'<span style="display:inline-block;width:12px;height:16px;margin-right:2px;'
        f'background:{CYAN if i < filled else GRIDC};border:2px solid {SHADOW}"></span>' for i in range(blocks))
    return f'<div style="white-space:nowrap;line-height:0">{cells}</div>'


def _hud(game: dict) -> str:
    def block(icon: str, big: str, small: str, colour: str) -> str:
        return (f'<div style="display:flex;align-items:center;gap:12px">{icon}<div>'
                f'<div style="font-family:{PIXEL_FONT};font-size:18px;color:{colour}">{_esc(big)}</div>'
                f'<div style="font-size:11px;color:{MUTED};margin-top:6px">{_esc(small)}</div></div></div>')

    streak = game["streak"]
    streak_label = f"{streak} DAY" + ("" if streak == 1 else "S")
    diamonds_note = "DIAMONDS  (+" + str(game["today"]) + " today)"
    next_level = game["level"] + 1
    xp_note = f'{game["xp"]} / {game["xp_needed"]} diamonds to level {next_level}'
    title = _esc(game["title"].upper())
    level = (
        f'<div style="min-width:240px"><div style="font-family:{PIXEL_FONT};font-size:12px;color:{GOLD}">'
        f'LV {game["level"]} <span style="color:{INK}">{title}</span></div>'
        f'<div style="margin:8px 0 4px">{_xp_bar(game["xp_pct"])}</div>'
        f'<div style="font-size:11px;color:{MUTED}">{xp_note}</div></div>')
    inner = (
        '<div style="display:flex;flex-wrap:wrap;gap:22px 34px;align-items:center;justify-content:space-between">'
        + block(pixel_svg("gem", 5, "diamonds"), str(game["total"]), diamonds_note, CYAN)
        + level
        + block(pixel_svg("flame", 5, "streak"), streak_label, "STREAK", ORANGE)
        + block(pixel_svg("chest", 5, "chests"), str(game["chests_today"]), "CHESTS TODAY", GOLD)
        + '</div>')
    return _frame(inner, f"border-color:{GOLD};")


def _hm(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def render_note(events: list[dict], today: date | None = None, now: datetime | None = None) -> str:
    today = today or dates.today()
    now = now or datetime.now(dates.TZ)
    d = collect(events, today)
    k = d["kpi"]
    rate = f"{round(100 * k['week_sessions'] / k['week_finished'])}%" if k["week_finished"] else "-"

    stats = "".join([
        _stat("Focus today", _hm(k["today_min"]), "incl. stopped early", GREEN),
        _stat("Focus this week", _hm(k["week_min"]), f"{k['week_sessions']} sessions finished", CYAN),
        _stat("Completion", rate, "sessions, last 7 days", MAGENTA),
        _stat("Tasks today", f"{k['tasks_today']}/{k['planned_today']}" if k["planned_today"] else str(k["tasks_today"]),
              "completed / planned", GOLD),
    ])
    sessions_pie = pixel_pie([("Completed", d["session_counts"].get("completed", 0), GREEN),
                              ("Stopped early", d["session_counts"].get("abandoned", 0), ORANGE),
                              ("Unfinished", d["session_counts"].get("unfinished", 0), MUTED)],
                             "sessions", chart="sessions")
    tasks_pie = pixel_pie([(label, d["task_counts"].get(kind, 0), colour) for kind, label, colour in TASK_OUTCOMES],
                          "outcomes", chart="tasks")

    grid2 = "display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;margin:22px 0"
    rows = [
        f'<div style="background:{BG};padding:18px;border:4px solid {SHADOW}">',
        f'<div style="margin:0 0 22px">{_hud(d["game"])}</div>',
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:18px;margin:0 0 22px">{stats}</div>',
        f'<div style="margin:22px 0">{_card("Focus time per day", stacked_bars(d["focus_days"]), f"Last {FOCUS_DAYS} days, minutes (green completed, orange stopped early)")}</div>',
        f'<div style="{grid2}">{_card("Focus sessions", sessions_pie, f"Last {OUTCOME_DAYS} days")}'
        f'{_card("Task outcomes", tasks_pie, f"Check-ins and the typewriter, last {OUTCOME_DAYS} days")}</div>',
        f'<div style="margin:22px 0">{_card("Task completion trend", line_chart(d["trend"]), f"Completed / planned per day, last {TREND_DAYS} days (gold dashed = 7-day average)")}</div>',
        f'<div style="margin:22px 0 0">{_card("When you focus", heatmap(d["heat"]), f"Minutes by weekday and hour, last {HEAT_DAYS} days (local time, brighter = more)")}</div>',
        '</div>',
    ]
    return "\n".join([
        "---",
        "tags: [dashboard, auto-generated]",
        f"updated: {now.isoformat(timespec='seconds')}",
        "---",
        "# Life Agent Dashboard",
        f"*Auto-generated {now.strftime('%a %d %b %Y, %H:%M')}. Do not hand-edit - changes are overwritten.*",
        "",
        *rows,
        "",
    ])


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # atomic: Obsidian never sees a half-written file


def write_dashboard(out_dir: Path | str | None = None, events: list[dict] | None = None,
                    today: date | None = None) -> Path:
    """Write the dashboard note plus its SVG images; returns the note path."""
    from life_agent.obsidian import dashboard_images
    out = Path(out_dir) if out_dir else dashboard_dir()
    out.mkdir(parents=True, exist_ok=True)
    events = store.load_all() if events is None else events
    note, files = dashboard_images.build(events, today=today)
    for name, svg in files.items():
        _atomic_write(out / name, svg)          # images first, so the note never points at a missing file
    _atomic_write(out / "Focus Log.md", dashboard_images.focus_log(events, today=today))
    path = out / NOTE_NAME
    _atomic_write(path, note)
    return path


_refresh_lock = threading.Lock()


def refresh_in_background(out_dir: Path | str | None = None, on_done=None) -> threading.Thread | None:
    """Regenerate the dashboard on a daemon thread; never raises. Skips if one is already running."""
    if not _refresh_lock.acquire(blocking=False):
        return None

    def _run():
        path, error = None, None
        try:
            path = write_dashboard(out_dir)
        except Exception as exc:
            error = exc
            print(f"[dashboard] refresh failed: {exc}")
        finally:
            _refresh_lock.release()
        if on_done:
            try:
                on_done(path, error)
            except Exception as exc:
                print(f"[dashboard] on_done failed: {exc}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the Obsidian dashboard note.")
    parser.add_argument("--out", help="Output folder (default: LIFE_AGENT_DASHBOARD_DIR or the vault)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(write_dashboard(args.out))
        return 0
    except Exception as exc:
        print(f"Dashboard failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
