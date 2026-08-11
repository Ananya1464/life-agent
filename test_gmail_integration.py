import sys
import emailer

def run():
    print("Sending manual integration test email via Gmail...")
    try:
        msg_id = emailer.send_email(
            "Test Email from Life Agent",
            "This is a manual integration test to verify Gmail connectivity.\n\n---\nJust reply to this email in your own words. No format needed.",
            debug=True
        )
        print(f"Success! Message-ID: {msg_id}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run()
