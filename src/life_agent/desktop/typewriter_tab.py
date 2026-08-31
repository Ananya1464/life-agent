import tkinter as tk
from tkinter import ttk
from datetime import date

from life_agent.events import event_model


class TypewriterTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.checkbox_vars = {}
        self.checkbox_widgets = {}

        # Header
        ttk.Label(self, text="Today's Tasks", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        ttk.Label(self, text="Click to mark complete — no confirmation, no undo", foreground="gray").pack(anchor="w", padx=10, pady=(0, 10))

        # Scrollable frame for checkboxes
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        scrollbar.pack(side="right", fill="y", pady=(0, 10), padx=(0, 10))

        # Bind mousewheel
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self.status_var = tk.StringVar(value="No tasks loaded — switch to Plan tab first")
        ttk.Label(self, textvariable=self.status_var, foreground="gray").pack(pady=(0, 10))

        # Refresh when tab gets focus
        self.bind("<Visibility>", self.refresh_tasks)
        self.bind("<FocusIn>", self.refresh_tasks)
        self.after(100, self.refresh_tasks)

    def refresh_tasks(self, event=None):
        """Rebuild checkboxes from shared app.tasks"""
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.checkbox_vars.clear()
        self.checkbox_widgets.clear()

        if not self.app.tasks:
            self.status_var.set("No tasks loaded — switch to Plan tab first")
            return

        for task in self.app.tasks:
            task_id = task["task_id"]
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(
                self.scroll_frame,
                text=f"{task['index']}. {task['task']} [{task['life_area']}]",
                variable=var,
                command=lambda tid=task_id, t=task["task"], v=var: self.on_check(tid, t, v)
            )
            cb.pack(anchor="w", padx=5, pady=3)
            self.checkbox_vars[task_id] = var
            self.checkbox_widgets[task_id] = cb

        self.status_var.set(f"{len(self.app.tasks)} tasks — click to complete")

    def on_check(self, task_id: str, task_name: str, var: tk.BooleanVar):
        if var.get():
            # Immediately record completion
            today_iso = date.today().isoformat()
            event_model.record_task_completed(
                task_name,
                date_iso=today_iso,
                source="typewriter",
                intent_id=task_id
            )
            # Disable checkbox (immutable event)
            if task_id in self.checkbox_widgets:
                self.checkbox_widgets[task_id].config(state="disabled")
            self.status_var.set(f"Completed: {task_name[:50]}")