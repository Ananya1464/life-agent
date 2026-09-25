import sys
import os
from pathlib import Path
from datetime import date

# Add repository root to PYTHONPATH
sys.path.insert(0, str(Path(os.getcwd()) / "src"))

from life_agent.obsidian.generator import generate_daily_note

def test_generate_daily_note():
    today = date.today().isoformat()
    markdown = generate_daily_note(today)
    
    # Assertions - loose checks to avoid markup issues
    assert "Daily Sessions" in markdown
    assert "Test Pomodoro Session" in markdown
    assert "Completed" in markdown
    assert "25 minutes" in markdown

if __name__ == "__main__":
    try:
        test_generate_daily_note()
        print("PHASE_2_PASSED")
    except Exception as e:
        print(f"Phase 2 generator test failed: {e}")
        sys.exit(1)
