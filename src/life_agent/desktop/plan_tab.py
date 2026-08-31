import tkinter as tk
from tkinter import ttk
from datetime import date
import re
import threading

from life_agent.integrations import notion_api
from life_agent.events import event_model
from life_agent.events.event_model import slugify
from life_agent.desktop import sync


SECTION_PRIORITIES = "Tomorrow's 3 priorities"


def _strip_emoji(text: str) -> str:
    return re.sub(r'^[^\w]*\s*', '', text)


def _safe_text(text: str) -> str:
    """Safely encode text for display on Windows."""
    try:
        return text
    except UnicodeEncodeError:
        return text.encode('ascii', 'replace').decode()


class PlanTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._loaded_date = None

        # UI
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(top_frame, text="Today's Tasks", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top_frame, text="🔄 Refresh", command=self.load_today).pack(side="right", padx=(5, 0))
        self.sync_btn = ttk.Button(top_frame, text="☁ Sync", command=self.sync_events)
        self.sync_btn.pack(side="right")

        self.task_listbox = tk.Listbox(self, font=("Segoe UI", 10), height=15)
        self.task_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_var = tk.StringVar(value="Click Refresh to load today's tasks")
        ttk.Label(self, textvariable=self.status_var, foreground="gray").pack(pady=(0, 10))

        # Load on init
        self.load_today()

    def load_today(self):
        today_iso = date.today().isoformat()

        # Guard: don't re-record if already loaded for today
        if self._loaded_date == today_iso and self.app.tasks:
            self.status_var.set(f"Already loaded for {today_iso}")
            return

        self.task_listbox.delete(0, tk.END)
        self.status_var.set("Loading...")

        try:
            page = notion_api.find_entry_by_date(today_iso)
            if not page:
                self.status_var.set(f"No Daily Log page found for {today_iso}")
                return

            page_id = page["id"]
            blocks = notion_api._children(page_id)
            if not blocks:
                self.status_var.set(f"Page empty for {today_iso}")
                return

            # Parse priorities section (same logic as migrate_notion.py)
            priorities_items = []
            current_section = None

            for block in blocks:
                btype = block.get("type", "")
                if btype in ("heading_2", "heading_3"):
                    heading = "".join(x.get("plain_text", "") for x in block.get(btype, {}).get("rich_text", []))
                    clean_heading = _strip_emoji(heading)
                    if SECTION_PRIORITIES in clean_heading:
                        current_section = "priorities"
                    else:
                        current_section = None
                    continue

                if current_section != "priorities":
                    continue

                text = "".join(x.get("plain_text", "") for x in block.get(btype, {}).get("rich_text", [])).strip()
                if not text:
                    continue

                if btype in ("numbered_list_item", "bulleted_list_item"):
                    priorities_items.append(text)

            if not priorities_items:
                self.status_var.set(f"No 'Tomorrow's 3 priorities' items found for {today_iso}")
                return

            # Build task dicts with task_id
            tasks = []
            for index, item in enumerate(priorities_items, start=1):
                task_id = f"{today_iso}:morning:{index}:{slugify(item)}"
                life_area = "learning" if "learn" in item.lower() or "study" in item.lower() else \
                            "career" if "email" in item.lower() or "application" in item.lower() or "professor" in item.lower() else \
                            "health" if "workout" in item.lower() or "exercise" in item.lower() else \
                            "general"
                tasks.append({
                    "task_id": task_id,
                    "task": item,
                    "life_area": life_area,
                    "index": index,
                })

            # Update shared state
            self.app.tasks = tasks

            # Render in listbox
            for task in tasks:
                self.task_listbox.insert(tk.END, f"{task['index']}. {_safe_text(task['task'])} [{task['life_area']}]")

            # Record planned intentions (once per day)
            intentions = [{"task": t["task"], "life_area": t["life_area"]} for t in tasks]
            event_model.record_planned_intentions(today_iso, "morning", intentions)

            self._loaded_date = today_iso
            self.status_var.set(f"Loaded {len(tasks)} tasks for {today_iso}")

        except Exception as e:
            self.status_var.set(f"Error: {e}")

    def sync_events(self):
        """Sync local events to cloud (non-blocking)."""
        self.sync_btn.config(state="disabled")
        self.status_var.set("Syncing...")

        def run_sync():
            try:
                result = sync.sync_events()
                if result.get("skipped_empty"):
                    msg = "Synced: nothing new"
                else:
                    pushed = result.get("pushed", 0)
                    failed = result.get("failed", 0)
                    msg = f"Synced {pushed} event(s)" + (f", {failed} failed" if failed else "")
                self.after(0, lambda: self._sync_done(msg))
            except Exception as e:
                self.after(0, lambda: self._sync_done(f"Sync failed: {e}"))

        threading.Thread(target=run_sync, daemon=True).start()

    def _sync_done(self, msg: str):
        self.sync_btn.config(state="normal")
        self.status_var.set(msg)