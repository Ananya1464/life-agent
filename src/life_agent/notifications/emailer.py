"""Send email to Ananya via Gmail SMTP (App Password). Fails loudly if delivery fails."""
from email.utils import make_msgid
import smtplib
from email.mime.text import MIMEText

from life_agent import config


def send_email(subject: str, body_markdown: str, debug: bool = False) -> str:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not configured")

    msg = MIMEText(body_markdown, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = config.GMAIL_ADDRESS
    
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        if debug:
            s.set_debuglevel(1)
        s.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        s.send_message(msg)
    print(f"[email] sent: {subject}")
    return msg_id


# Alias send to send_email so existing tasks fail loudly too
send = send_email

