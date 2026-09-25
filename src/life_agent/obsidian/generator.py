"""
Obsidian daily session note generator.
"""
from datetime import datetime
from life_agent.events.queries import get_focus_sessions

def generate_daily_note(date_iso: str) -> str:
    """Generate Markdown for a daily session note."""
    sessions = [s for s in get_focus_sessions(date_iso) if s["status"] != "unfinished"]
    
    lines = [
        f"# Daily Sessions — {date_iso}",
        "",
        "⚠ Auto-generated. Do not hand-edit.",
        ""
    ]
    
    if not sessions:
        lines.append("No focus sessions recorded.")
        return "\n".join(lines)
        
    lines.append(f"## Focus Sessions ({len(sessions)})")
    lines.append("")
    
    total_duration = 0
    completed_count = 0
    
    for i, session in enumerate(sessions, 1):
        lines.append(f"### Session {i}: {session['task']}")
        lines.append(f"- **Status:** {session['status'].capitalize()}")
        
        duration = session['duration_seconds'] or 0
        total_duration += duration
        if session['status'] == 'completed':
            completed_count += 1
            
        lines.append(f"- **Duration:** {duration // 60} min ({duration} seconds)")
        
        # Time format (naive conversion)
        start_time = session['start']
        end_time = session['end']
        time_str = "N/A"
        if start_time:
            # Simple slice of ISO string for time
            start_fmt = start_time.split('T')[1][:5]
            time_str = f"{start_fmt}"
            if end_time:
                end_fmt = end_time.split('T')[1][:5]
                time_str += f"–{end_fmt}"
        
        lines.append(f"- **Time:** {time_str} UTC")
        lines.append(f"- **Source:** {session['source']}")
        lines.append("")
        
    lines.append("## Summary")
    lines.append(f"- Total focus time: {total_duration // 60} minutes")
    lines.append(f"- Sessions completed: {completed_count} / {len(sessions)}")
    
    return "\n".join(lines)
