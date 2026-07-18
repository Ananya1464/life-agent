"""Setup verification — run this once after filling .env:  python check_setup.py

Checks, in order:
  1. .env loads and required keys are present
  2. Notion token works and can see the Daily Log data source + Weight Loss page
  3. Gemini key works with the configured model
"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load_env():
    env_file = HERE / ".env"
    if not env_file.exists():
        print("[FAIL] .env file not found next to check_setup.py")
        sys.exit(1)
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())
    print("[ OK ] .env loaded")


def check_keys():
    ok = True
    if not os.environ.get("NOTION_TOKEN", "").startswith("ntn_"):
        print("[FAIL] NOTION_TOKEN missing or malformed")
        ok = False
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        print("[FAIL] Need GEMINI_API_KEY or ANTHROPIC_API_KEY")
        ok = False
    if not ok:
        sys.exit(1)
    print("[ OK ] Required keys present")


def check_notion():
    import requests

    headers = {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json",
    }
    ds = os.environ.get("DAILY_LOG_DATA_SOURCE_ID", "c4764f6a-59f1-466d-843f-eb798eb3b033")
    r = requests.post(
        f"https://api.notion.com/v1/data_sources/{ds}/query",
        headers=headers, json={"page_size": 1}, timeout=30,
    )
    if r.status_code == 401:
        print("[FAIL] Notion token invalid (401). Re-copy it from notion.so/my-integrations")
        sys.exit(1)
    if r.status_code == 404:
        print("[FAIL] Notion 404: the integration can't see the Daily Log.")
        print("       Open '🌱 Daily Life Tracker' in Notion → ⋯ → Connections → add your integration.")
        sys.exit(1)
    r.raise_for_status()
    n = len(r.json().get("results", []))
    print(f"[ OK ] Notion: Daily Log data source reachable ({'has entries' if n else 'empty'})")

    wl = os.environ.get("WEIGHT_LOSS_PAGE_ID", "37ade9d3d9b781a9bfcbecdf326bf6b9")
    r = requests.get(f"https://api.notion.com/v1/pages/{wl}", headers=headers, timeout=30)
    if r.status_code == 404:
        print("[WARN] Weight Loss page not visible to the integration.")
        print("       Open 'Weight Loss Plan' page → ⋯ → Connections → add your integration.")
        print("       (meal_plan task will fail until fixed; other tasks fine)")
    else:
        r.raise_for_status()
        print("[ OK ] Notion: Weight Loss page reachable")


def check_llm():
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("[INFO] ANTHROPIC_API_KEY set — Claude backend will be used.")
        return
    from google import genai

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    try:
        resp = client.models.generate_content(model=model, contents="Reply with exactly: OK")
        print(f"[ OK ] Gemini ({model}) responded: {(resp.text or '').strip()[:40]}")
    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            print(f"[WARN] Gemini {model} rate-limited on free tier.")
            print("       Add this line to .env:  GEMINI_MODEL=gemini-2.5-flash")
        elif "API key" in msg or "401" in msg or "403" in msg:
            print("[FAIL] Gemini API key rejected. Re-create it at aistudio.google.com/apikey")
            sys.exit(1)
        else:
            print(f"[FAIL] Gemini error: {msg[:300]}")
            sys.exit(1)


if __name__ == "__main__":
    load_env()
    check_keys()
    check_notion()
    check_llm()
    print("\nAll checks done. Next:  python main.py evening_checkin")
