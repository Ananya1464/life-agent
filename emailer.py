"""Send email to Ananya via Gmail SMTP (App Password). Fails silently by design —
Notion is the source of truth; email is a convenience."""
import smtplib
from email.mime.text import MIMEText

import config


def send(subject: str, body_markdown: str) -> bool:
    if not config.GMAIL_APP_PASSWORD:
        print("[email] GMAIL_APP_PASSWORD not set — skipping email.")
        return False
    try:
        msg = MIMEText(body_markdown, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = config.GMAIL_ADDRESS
        msg["To"] = config.GMAIL_ADDRESS
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            s.send_message(msg)
        print(f"[email] sent: {subject}")
        return True
    except Exception as e:  # never let email failure kill a run
        print(f"[email] failed (continuing): {e}")
        return False
