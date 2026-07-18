"""~9:30 PM IST — weight-loss habit accountability nudge (email)."""
import dates
import emailer
import llm
import prompt_loader


def run():
    d = dates.today()
    prompt = prompt_loader.load("evening_checkin", TODAY_LABEL=dates.day_label(d))
    nudge = llm.generate(prompt, temperature=0.9)  # higher temp → varied wording
    print(nudge)
    emailer.send(f"Evening check-in — {dates.day_label(d)} 🌙", nudge)
