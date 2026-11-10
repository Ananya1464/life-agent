import xml.dom.minidom
from datetime import date, datetime, timezone

from life_agent.obsidian import dashboard, dashboard_images as di


def test_note_is_plain_markdown_with_image_embeds():
    note, files = di.build([], today=date(2026, 10, 3), now=datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))
    assert "<div" not in note and "<svg" not in note
    assert max(len(line) for line in note.splitlines()) < 200
    for name in files:
        assert f"![[{name}|{di.WIDTH}]]" in note


def test_every_image_is_well_formed_svg():
    _, files = di.build([], today=date(2026, 10, 3))
    assert len(files) == 7
    for name, svg in files.items():
        assert name.endswith(".svg")
        xml.dom.minidom.parseString(svg)          # raises if not well formed
        assert "var(--" not in svg and "<script" not in svg


def test_write_dashboard_writes_note_and_images_atomically(tmp_path):
    path = dashboard.write_dashboard(tmp_path, events=[], today=date(2026, 10, 3))
    assert path.exists()
    assert len(list(tmp_path.glob("la-*.svg"))) == 7
    assert not list(tmp_path.glob("*.tmp"))
    before = path.read_text(encoding="utf-8").splitlines()[5:]
    dashboard.write_dashboard(tmp_path, events=[], today=date(2026, 10, 3))
    assert path.read_text(encoding="utf-8").splitlines()[5:] == before
