import tkinter as tk
from tkinter import ttk
from datetime import date

from life_agent.events import event_model


class FocusTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.timer_seconds = 1500  # 25 minutes
        self.timer_running = False
        self.timer_after_id = None
        self.current_task = None
        self.current_task_id = None
        self.elapsed_seconds = 0

        # Task selection
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(top_frame, text="Select Task:").pack(anchor="w")
        self.task_var = tk.StringVar()
        self.task_combo = ttk.Combobox(top_frame, textvariable=self.task_var, state="readonly", width=50)
        self.task_combo.pack(fill="x", pady=(5, 10))
        self.task_combo.bind("<<ComboboxSelected>>", self.on_task_selected)

        # Timer display
        self.timer_label = ttk.Label(self, text="25:00", font=("Segoe UI", 48, "bold"))
        self.timer_label.pack(pady=20)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)

        self.start_btn = ttk.Button(btn_frame, text="▶ START", command=self.start_timer, width=12)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="■ STOP", command=self.stop_timer, width=12, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="Select a task and press START")
        ttk.Label(self, textvariable=self.status_var, foreground="gray").pack(pady=10)

        # Refresh task list when tab is shown or focused
        self.bind("<Visibility>", self.refresh_tasks)
        self.bind("<FocusIn>", self.refresh_tasks)
        # Also refresh after a short delay on init
        self.after(100, self.refresh_tasks)

    def refresh_tasks(self, event=None):
        """Update dropdown from shared app.tasks"""
        if not self.app.tasks:
            self.task_combo["values"] = []
            self.task_var.set("")
            return

        display_values = [f"{t['index']}. {t['task']}" for t in self.app.tasks]
        self.task_combo["values"] = display_values
        if not self.task_var.get() and display_values:
            self.task_combo.current(0)
            self.on_task_selected()

    def on_task_selected(self, event=None):
        selection = self.task_combo.current()
        if selection >= 0 and selection < len(self.app.tasks):
            task = self.app.tasks[selection]
            self.current_task = task["task"]
            self.current_task_id = task["task_id"]
            self.status_var.set(f"Ready: {self.current_task[:50]}...")

    def start_timer(self):
        if not self.current_task:
            self.status_var.set("Select a task first")
            return

        self.timer_running = True
        self.timer_seconds = 1500
        self.elapsed_seconds = 0
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.task_combo.config(state="disabled")
        self.status_var.set(f"Focus session started: {self.current_task[:40]}")

        # Record focus_started
        today_iso = date.today().isoformat()
        event_model.record_focus_started(
            date_iso=today_iso,
            task=self.current_task,
            intent_id=self.current_task_id,
            source="focus_tab"
        )

        self.tick()

    def tick(self):
        if not self.timer_running:
            return

        if self.timer_seconds > 0:
            self.timer_seconds -= 1
            self.elapsed_seconds += 1
            mins = self.timer_seconds // 60
            secs = self.timer_seconds % 60
            self.timer_label.config(text=f"{mins:02d}:{secs:02d}")
            self.timer_after_id = self.after(1000, self.tick)
        else:
            self.timer_complete()

    def timer_complete(self):
        self.timer_running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.task_combo.config(state="readonly")
        self.timer_label.config(text="25:00")

        # Record focus_completed
        today_iso = date.today().isoformat()
        event_model.record_focus_completed(
            date_iso=today_iso,
            task=self.current_task,
            duration_seconds=1500,
            intent_id=self.current_task_id,
            source="focus_tab"
        )
        self.status_var.set(f"Completed 25 min focus on: {self.current_task}")

    def stop_timer(self):
        if not self.timer_running:
            return

        self.timer_running = False
        if self.timer_after_id:
            self.after_cancel(self.timer_after_id)
            self.timer_after_id = None

        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.task_combo.config(state="readonly")
        self.timer_label.config(text="25:00")

        # Record focus_abandoned with elapsed time
        today_iso = date.today().isoformat()
        event_model.record_focus_abandoned(
            date_iso=today_iso,
            task=self.current_task,
            duration_seconds=self.elapsed_seconds,
            intent_id=self.current_task_id,
            source="focus_tab"
        )
        mins = self.elapsed_seconds // 60
        secs = self.elapsed_seconds % 60
        self.status_var.set(f"Abandoned after {mins}:{secs:02d}: {self.current_task}")