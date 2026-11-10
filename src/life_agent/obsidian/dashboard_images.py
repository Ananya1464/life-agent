"""Obsidian dashboard as standalone SVG images embedded in a tiny markdown note.

Why images: one giant HTML block (tens of thousands of characters on a single line) does not render
reliably in Obsidian's editor modes. An image embed (`![[file.svg]]`) renders the same in Live Preview,
Reading view and Source-less previews, and the note itself stays small and readable.

Each image is self-contained: fixed colours, system fonts, no CSS variables, no scripts.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from life_agent import dates
from life_agent.obsidian import dashboard as d
from life_agent.pixel import pixel_svg

WIDTH = 760
FONT = "'Courier New',Consolas,monospace"
PREFIX = "la-"


# ----------------------------------------------------------------------------- helpers
def _viewbox(svg: str) -> tuple[int, int]:
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    return int(m.group(1)), int(m.group(2))


def _place(svg: str, x: int, y: int) -> str:
    """Make a chart <svg> (width=100%) a fixed-size nested element at (x, y)."""
    w, h = _viewbox(svg)
    svg = re.sub(r' width="100%"', f' x="{x}" y="{y}" width="{w}" height="{h}"', svg, count=1)
    return re.sub(r"max-width:\d+px;height:auto;", "", svg)


def _sprite(name: str, scale: int, x: int, y: int) -> str:
    return pixel_svg(name, scale).replace("<svg ", f'<svg x="{x}" y="{y}" ', 1)


def _text(x: int, y: int, text: str, size: int, fill: str, anchor: str = "start", bold: bool = True) -> str:
    weight = ' font-weight="700"' if bold else ""
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" fill="{fill}"{weight}>'
            f"{d._esc(text)}</text>")


def _panel(w: int, h: int, border: str = d.EDGE) -> str:
    """Chunky bevelled panel: hard drop shadow, thick border, thin inner line."""
    return (f'<rect x="8" y="8" width="{w - 10}" height="{h - 10}" fill="{d.SHADOW}"/>'
            f'<rect x="2" y="2" width="{w - 10}" height="{h - 10}" fill="{d.PANEL}" stroke="{border}" stroke-width="4"/>'
            f'<rect x="8" y="8" width="{w - 22}" height="{h - 22}" fill="none" stroke="{d.BG}" stroke-width="2"/>')


def _doc(w: int, h: int, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'shape-rendering="crispEdges" font-family="{FONT}"><rect width="{w}" height="{h}" fill="{d.BG}"/>{body}</svg>')


def _card(title: str, subtitle: str, inner: str, inner_h: int, inner_w: int = 640) -> str:
    h = 70 + inner_h + 26
    x = (WIDTH - inner_w) // 2
    body = (_panel(WIDTH, h) + _sprite("gem", 2, 20, 14)
            + _text(52, 33, title.upper(), 13, d.CYAN) + _text(22, 56, subtitle, 11, d.MUTED, bold=False)
            + _place(inner, x, 70))
    return _doc(WIDTH, h, body)


# ----------------------------------------------------------------------------- images
def hud_image(game: dict) -> str:
    h = 176
    streak = game["streak"]
    body = [_panel(WIDTH, h, border=d.GOLD)]
    body += [_sprite("gem", 5, 28, 22), _text(100, 46, str(game["total"]), 22, d.CYAN),
             _text(100, 66, f"DIAMONDS  (+{game['today']} today)", 11, d.MUTED, bold=False)]
    body += [_text(300, 40, f"LV {game['level']}  {game['title'].upper()}", 15, d.GOLD)]
    filled = round(20 * game["xp_pct"] / 100)
    for i in range(20):
        body.append(f'<rect x="{300 + i * 20}" y="52" width="16" height="18" fill="{d.CYAN if i < filled else d.GRIDC}" '
                    f'stroke="{d.SHADOW}" stroke-width="2"/>')
    body += [_text(300, 92, f"{game['xp']} / {game['xp_needed']} diamonds to level {game['level'] + 1}", 11, d.MUTED, bold=False)]
    body += [_sprite("flame", 5, 28, 100), _text(100, 128, f"{streak} DAY" + ("" if streak == 1 else "S"), 20, d.ORANGE),
             _text(100, 146, "STREAK", 11, d.MUTED, bold=False)]
    body += [_sprite("chest", 5, 300, 108), _text(380, 128, str(game["chests_today"]), 20, d.GOLD),
             _text(380, 146, "CHESTS TODAY", 11, d.MUTED, bold=False)]
    return _doc(WIDTH, h, "".join(body))


def stats_image(k: dict) -> str:
    rate = f"{round(100 * k['week_sessions'] / k['week_finished'])}%" if k["week_finished"] else "-"
    tasks = f"{k['tasks_today']}/{k['planned_today']}" if k["planned_today"] else str(k["tasks_today"])
    tiles = [
        ("FOCUS TODAY", d._hm(k["today_min"]), "incl. stopped early", d.GREEN),
        ("FOCUS THIS WEEK", d._hm(k["week_min"]), f"{k['week_sessions']} sessions finished", d.CYAN),
        ("COMPLETION", rate, "sessions, last 7 days", d.MAGENTA),
        ("TASKS TODAY", tasks, "completed / planned", d.GOLD),
    ]
    h, tw, gap = 120, 172, 14
    body = []
    for i, (label, value, hint, colour) in enumerate(tiles):
        x = 6 + i * (tw + gap)
        body.append(f'<rect x="{x + 6}" y="10" width="{tw}" height="{h - 18}" fill="{d.SHADOW}"/>'
                    f'<rect x="{x}" y="4" width="{tw}" height="{h - 18}" fill="{d.PANEL}" stroke="{d.EDGE}" stroke-width="4"/>'
                    f'<rect x="{x}" y="4" width="10" height="{h - 18}" fill="{colour}"/>')
        body += [_text(x + 22, 30, label, 10, d.MUTED), _text(x + 22, 66, value, 20, colour), _text(x + 22, 88, hint, 10, d.MUTED, bold=False)]
    return _doc(WIDTH, h, "".join(body))


def pie_image(title: str, subtitle: str, items: list[tuple[str, float, str]], centre: str, chart: str) -> str:
    items = [(a, b, c) for a, b, c in items if b > 0]
    if not items:
        return _card(title, subtitle, d._empty(640, 90, "No data in this period yet", chart), 90)
    pie = d._pie_svg(items, centre, chart)
    total = sum(v for _, v, _ in items)
    h = max(70 + 184 + 26, 70 + len(items) * 28 + 26)
    body = [_panel(WIDTH, h), _sprite("gem", 2, 20, 14), _text(52, 33, title.upper(), 13, d.CYAN),
            _text(22, 56, subtitle, 11, d.MUTED, bold=False), _place(pie, 40, 70)]
    for i, (label, value, colour) in enumerate(items):
        y = 96 + i * 28
        body += [f'<rect x="270" y="{y - 12}" width="14" height="14" fill="{colour}" stroke="{d.SHADOW}" stroke-width="2"/>',
                 _text(294, y, label, 13, d.INK, bold=False),
                 _text(720, y, f"{int(value)}  ({round(100 * value / total)}%)", 13, d.MUTED, anchor="end", bold=False)]
    return _doc(WIDTH, h, "".join(body))


def build(events: list[dict], today: date | None = None, now: datetime | None = None) -> tuple[str, dict[str, str]]:
    """Returns (markdown note, {filename: svg}) for the whole dashboard."""
    today = today or dates.today()
    now = now or datetime.now(dates.TZ)
    data = d.collect(events, today)
    files = {
        f"{PREFIX}hud.svg": hud_image(data["game"]),
        f"{PREFIX}stats.svg": stats_image(data["kpi"]),
        f"{PREFIX}focus.svg": _card("Focus time per day",
                                    f"Last {d.FOCUS_DAYS} days, minutes (green completed, orange stopped early)",
                                    d.stacked_bars(data["focus_days"]), 230),
        f"{PREFIX}sessions.svg": pie_image("Focus sessions", f"Last {d.OUTCOME_DAYS} days", [
            ("Completed", data["session_counts"].get("completed", 0), d.GREEN),
            ("Stopped early", data["session_counts"].get("abandoned", 0), d.ORANGE),
            ("Unfinished", data["session_counts"].get("unfinished", 0), d.MUTED)], "sessions", "sessions"),
        f"{PREFIX}tasks.svg": pie_image("Task outcomes", f"Check-ins and the typewriter, last {d.OUTCOME_DAYS} days", [
            (label, data["task_counts"].get(kind, 0), colour) for kind, label, colour in d.TASK_OUTCOMES], "outcomes", "tasks"),
        f"{PREFIX}trend.svg": _card("Task completion trend",
                                    f"Completed / planned per day, last {d.TREND_DAYS} days (gold dashed = 7-day average)",
                                    d.line_chart(data["trend"]), 210),
    }
    heat = d.heatmap(data["heat"])
    files[f"{PREFIX}heat.svg"] = _card("When you focus", f"Minutes by weekday and hour, last {d.HEAT_DAYS} days (local time, brighter = more)",
                                       heat, _viewbox(heat)[1])
    order = ["hud", "stats", "focus", "sessions", "tasks", "trend", "heat"]
    embeds = "\n\n".join(f"![[{PREFIX}{name}.svg|{WIDTH}]]" for name in order)
    note = "\n".join([
        "---",
        "tags: [dashboard, auto-generated]",
        f"updated: {now.isoformat(timespec='seconds')}",
        "---",
        "# Life Agent Dashboard",
        f"*Auto-generated {now.strftime('%a %d %b %Y, %H:%M')}. Do not hand-edit - changes are overwritten.*",
        "",
        embeds,
        "",
    ])
    return note, files


def focus_log(events: list[dict], today: date | None = None, days: int = 60, now: datetime | None = None) -> str:
    """Plain-markdown history of focus sessions, newest day first. Readable on a phone, no plugins needed."""
    today = today or dates.today()
    now = now or datetime.now(dates.TZ)
    sessions = d._all_sessions(events, today - timedelta(days=days - 1), today)
    by_day: dict[str, list[dict]] = {}
    for s in sessions:
        by_day.setdefault(s["date"], []).append(s)
    icons = {"completed": "done", "abandoned": "stopped early", "unfinished": "unfinished"}
    lines = ["---", "tags: [focus-log, auto-generated]", f"updated: {now.isoformat(timespec='seconds')}", "---",
             "# Focus Log",
             f"*Auto-generated {now.strftime('%a %d %b %Y, %H:%M')}. Last {days} days, newest first. Do not hand-edit.*", ""]
    if not by_day:
        lines.append("No focus sessions yet.")
    for day in sorted(by_day, reverse=True):
        rows = sorted(by_day[day], key=lambda s: s.get("start") or "")
        total = sum((s.get("duration_seconds") or 0) for s in rows if s["status"] == "completed") / 60
        lines += [f"## {day}  ({d._hm(total)} completed)", "", "| Start | Task | Minutes | Result |", "|---|---|---|---|"]
        for s in rows:
            start = d._local_dt(s.get("start"))
            minutes = round((s.get("duration_seconds") or 0) / 60) if s.get("duration_seconds") is not None else "-"
            task = str(s.get("task", "")).replace("|", "/").replace("\n", " ")
            lines.append(f"| {start.strftime('%H:%M') if start else '-'} | {task} | {minutes} | {icons[s['status']]} |")
        lines.append("")
    return "\n".join(lines)
