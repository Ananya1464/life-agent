import sys
import os
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


def safe_print(text):
    """Print text safely handling Unicode encoding issues on Windows."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode())


class LifeAgentDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Life Agent")
        self.geometry("500x550")
        self.configure(bg="#1a1a2e")

        # Shared state: today's tasks (populated by Plan tab)
        self.tasks = []  # list of dicts: {task_id, task, life_area}

        notebook = ttk.Notebook(self)

        from .plan_tab import PlanTab
        from .focus_tab import FocusTab
        from .typewriter_tab import TypewriterTab

        self.plan_tab = PlanTab(notebook, self)
        self.focus_tab = FocusTab(notebook, self)
        self.typewriter_tab = TypewriterTab(notebook, self)

        notebook.add(self.plan_tab, text="📋 Plan")
        notebook.add(self.focus_tab, text="⏱️ Focus")
        notebook.add(self.typewriter_tab, text="✅ Typewriter")
        notebook.pack(expand=True, fill="both", padx=10, pady=10)


if __name__ == "__main__":
    LifeAgentDesktop().mainloop()